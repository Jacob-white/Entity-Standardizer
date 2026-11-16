"""Unit tests for the 6 wealth/distribution MDM standardization & matching enhancements."""

from __future__ import annotations

from entity_standardizer import (
    AdvisorGroupComparisonResult,
    IdentifierComparisonResult,
    RepEntityClass,
    StandardizedAdvisorGroup,
    StandardizedIdentifier,
    classify_rep_entity,
    cluster_contact_records,
    compare_addresses,
    compare_advisor_groups,
    compare_companies,
    compare_contacts,
    compare_external_ids,
    compare_persons,
    deduplicate_addresses,
    deduplicate_persons,
    is_organization_name,
    split_compound_persons,
    standardize_address,
    standardize_advisor_group,
    standardize_company,
    standardize_contact,
    standardize_crd,
    standardize_external_id,
    standardize_person,
    standardize_phone,
)
from entity_standardizer.person import _build_person_alt_keys


def test_address_postal_keys_vanity_cities_and_street_canonicalization() -> None:
    # 1. Vanity municipality vs USPS primary ZIP5 city (75205 -> DALLAS)
    addr_vanity = standardize_address(
        street1="8201 Preston Rd",
        street2="Suite 500",
        city="University Park",
        state="TX",
        postal_code="75205",
        country="US",
    )
    addr_usps = standardize_address(
        street1="8201 Preston Road",
        street2="Ste 500",
        city="Dallas",
        state="TX",
        postal_code="75205",
        country="US",
    )
    assert addr_vanity.postal_city == "DALLAS"
    assert addr_usps.postal_city == "DALLAS"
    assert addr_vanity.normalized_address_key != addr_usps.normalized_address_key
    assert addr_vanity.postal_address_key == addr_usps.postal_address_key
    assert addr_vanity.postal_building_key == addr_usps.postal_building_key
    as_d = addr_vanity.as_dict()
    assert as_d["postal_city"] == "DALLAS"
    assert as_d["postal_address_key"] == addr_vanity.postal_address_key
    assert as_d["postal_building_key"] == addr_vanity.postal_building_key

    cmp_pak = compare_addresses(addr_vanity, addr_usps)
    assert cmp_pak.is_match is True
    assert cmp_pak.match_type == "POSTAL_ADDRESS_KEY_MATCH"
    assert cmp_pak.score == 0.98

    # Postal building key match (one has suite, one does not, vanity city vs USPS city)
    addr_no_suite = standardize_address(
        street1="8201 Preston Rd",
        city="Dallas",
        state="TX",
        postal_code="75205",
        country="US",
    )
    cmp_pbk = compare_addresses(addr_vanity, addr_no_suite)
    assert cmp_pbk.is_match is True
    assert cmp_pbk.match_type == "POSTAL_BUILDING_KEY_MATCH"
    assert cmp_pbk.score == 0.93

    # Different unit in same building across vanity city -> DIFFERENT_UNIT_SAME_BUILDING
    addr_diff_suite = standardize_address(
        street1="8201 Preston Rd",
        street2="Suite 600",
        city="Dallas",
        state="TX",
        postal_code="75205",
        country="US",
    )
    cmp_diff_unit = compare_addresses(addr_vanity, addr_diff_suite)
    assert cmp_diff_unit.is_match is False
    assert cmp_diff_unit.match_type == "DIFFERENT_UNIT_SAME_BUILDING"

    # Deduplicate addresses merges vanity city via pak/pbk buckets
    clusters = deduplicate_addresses([addr_vanity, addr_usps, addr_no_suite])
    assert len(clusters) == 1
    assert len(clusters[0].members) == 3

    # 2. US city prefix canonicalization (SAINT -> ST, SAINTE -> STE, FORT -> FT, MOUNT -> MT)
    addr_st1 = standardize_address(
        street1="880 Carillon Pkwy",
        city="Saint Petersburg",
        state="FL",
        postal_code="33716",
        country="US",
    )
    addr_st2 = standardize_address(
        street1="880 Carillon Pkwy",
        city="St. Petersburg",
        state="FL",
        postal_code="33716",
        country="US",
    )
    assert addr_st1.city == "ST PETERSBURG"
    assert addr_st1.normalized_address_key == addr_st2.normalized_address_key

    # 3. Interior CTR -> CENTER & spaced initialisms (1 A D P BLVD -> 1 ADP BLVD)
    addr_ctr1 = standardize_address(
        street1="800 Corporate Ctr Dr",
        city="Raleigh",
        state="NC",
        postal_code="27607",
        country="US",
    )
    addr_ctr2 = standardize_address(
        street1="800 Corporate Center Drive",
        city="Raleigh",
        state="NC",
        postal_code="27607",
        country="US",
    )
    assert addr_ctr1.normalized_address_key == addr_ctr2.normalized_address_key

    addr_adp1 = standardize_address(
        street1="1 A D P Blvd",
        city="Roseland",
        state="NJ",
        postal_code="07068",
        country="US",
    )
    addr_adp2 = standardize_address(
        street1="1 ADP Boulevard",
        city="Roseland",
        state="NJ",
        postal_code="07068",
        country="US",
    )
    assert addr_adp1.normalized_address_key == addr_adp2.normalized_address_key

    # 4. compare_contacts postal_address_key and postal_building_key branches
    c_vanity = standardize_contact(
        person_name="Scott Simpson",
        street1="8201 Preston Rd",
        street2="Suite 500",
        city="University Park",
        state="TX",
        postal_code="75205",
        country="US",
    )
    c_usps = standardize_contact(
        person_name="Scott Simpson",
        street1="8201 Preston Rd",
        street2="Ste 500",
        city="Dallas",
        state="TX",
        postal_code="75205",
        country="US",
    )
    cc_pak = compare_contacts(c_vanity, c_usps)
    assert cc_pak.is_match is True
    assert cc_pak.pillar_scores["address"] == 0.98

    c_no_ste = standardize_contact(
        person_name="Scott Simpson",
        street1="8201 Preston Rd",
        city="Dallas",
        state="TX",
        postal_code="75205",
        country="US",
    )
    cc_pbk = compare_contacts(c_vanity, c_no_ste)
    assert cc_pbk.is_match is True
    assert cc_pbk.pillar_scores["address"] == 0.90

    c_diff_ste = standardize_contact(
        person_name="Scott Simpson",
        street1="8201 Preston Rd",
        street2="Suite 600",
        city="Dallas",
        state="TX",
        postal_code="75205",
        country="US",
    )
    cc_diff_ste = compare_contacts(c_vanity, c_diff_ste)
    assert cc_diff_ste.pillar_scores["address"] == 0.0


def test_company_wealth_abbreviations_html_entities_and_crm_hierarchy() -> None:
    # HTML entity decoding
    c_html = standardize_company("Waddell &amp; Reed Financial Srvs Inc.")
    assert "HTML_ENTITIES_DECODED" in c_html.healing_actions
    assert "TOKEN_ABBREVIATION_EXPANDED" in c_html.healing_actions
    assert c_html.base_name == "WADDELL AND REED FINANCIAL SERVICES"
    assert c_html.brand_key == "WADDELL" or c_html.brand_key == "WADDELL AND REED"
    assert c_html.brand_key == "WADDELL AND REED"

    # Non-HTML entity ampersand token (e.g. "&notanentity;" stays unchanged, numeric "&#38;" decodes)
    c_non_ent = standardize_company("Smith &notanentity; Co")
    assert "HTML_ENTITIES_DECODED" not in c_non_ent.healing_actions
    c_num_ent = standardize_company("Smith &#38; Jones LLC")
    assert "HTML_ENTITIES_DECODED" in c_num_ent.healing_actions
    assert c_num_ent.base_name == "SMITH AND JONES"

    # CRM hierarchy tail stripping
    c_ult = standardize_company("Blue Owl Capital Ultimate Parent")
    assert c_ult.base_name == "BLUE OWL CAPITAL"
    assert c_ult.branch_unit == "ULTIMATE PARENT"
    assert "CRM_HIERARCHY_SUFFIX_STRIPPED" in c_ult.healing_actions

    c_parent = standardize_company("Blue Owl Capital Parent")
    assert c_parent.base_name == "BLUE OWL CAPITAL"
    assert "CRM_HIERARCHY_SUFFIX_STRIPPED" in c_parent.healing_actions

    # Single-word prefix before "Parent" should NOT strip "Parent"
    c_single_parent = standardize_company("Grand Parent")
    assert "CRM_HIERARCHY_SUFFIX_STRIPPED" not in c_single_parent.healing_actions
    assert c_single_parent.base_name == "GRAND PARENT"

    # Empty head_part before CRM hierarchy tag should NOT strip
    c_only_tag = standardize_company("Ultimate Parent")
    assert "CRM_HIERARCHY_SUFFIX_STRIPPED" not in c_only_tag.healing_actions

    c_snl = standardize_company("Jackson National - SNL Life Group")
    assert c_snl.base_name == "JACKSON NATIONAL"
    assert c_snl.brand_key == "JACKSON NATIONAL"

    # Wealth brand_key convergence across broker-dealer affiliates
    rj1 = standardize_company("Raymond James Financial Services Advisors, Inc.")
    rj2 = standardize_company("Raymond James & Associates, Inc.")
    assert rj1.brand_key == "RAYMOND JAMES"
    assert rj2.brand_key == "RAYMOND JAMES"
    cmp_rj = compare_companies(rj1, rj2)
    assert cmp_rj.is_match is True


def test_person_alt_keys_html_entities_and_middle_gobys() -> None:
    # Direct helper edge cases
    assert _build_person_alt_keys(None, None, None, "SMITH", "SMITH") == []
    assert _build_person_alt_keys("JOHN", "JOHN", "M", "SMITH", "SMITH|JOHN") == []

    # Middle-name go-by: "W. Scott Simpson" <-> "Scott Simpson" <-> "William Scott Simpson"
    p_init_mid = standardize_person("W. Scott Simpson")
    p_goby = standardize_person("Scott Simpson")
    p_full_mid = standardize_person("William Scott Simpson")

    assert "SIMPSON|W|SCOTT" in p_init_mid.person_alt_keys
    assert "SIMPSON|SCOTT" in p_init_mid.person_alt_keys
    assert p_init_mid.to_dict()["person_alt_keys"] == p_init_mid.person_alt_keys

    cmp1 = compare_persons(p_init_mid, p_goby)
    assert cmp1.is_match is True
    assert cmp1.match_type == "ALT_NAME_KEY_MATCH"
    assert cmp1.score == 0.93

    cmp2 = compare_persons(p_goby, p_init_mid)
    assert cmp2.is_match is True
    assert cmp2.match_type == "ALT_NAME_KEY_MATCH"

    cmp3 = compare_persons(p_init_mid, p_full_mid)
    assert cmp3.is_match is True
    assert cmp3.match_type == "ALT_NAME_KEY_MATCH"

    # Guard against merging two different full-first+middle names ("John Michael Smith" vs "Michael Paul Smith")
    p_jm = standardize_person("John Michael Smith")
    p_mp = standardize_person("Michael Paul Smith")
    cmp_conflict = compare_persons(p_jm, p_mp)
    assert cmp_conflict.is_match is False

    # Curly apostrophe + HTML entity decoding + apostrophe-folded surname alt key
    p_apos1 = standardize_person("Patrick O\u2019Malley &amp; CFP")
    p_apos2 = standardize_person("Patrick OMalley")
    assert "HTML_ENTITIES_DECODED" in p_apos1.healing_actions
    assert "OMALLEY|PATRICK" in p_apos1.person_alt_keys
    assert compare_persons(p_apos1, p_apos2).is_match is True

    # Non-entity ampersand in person
    p_non_ent = standardize_person("John &notentity; Smith")
    assert "HTML_ENTITIES_DECODED" not in p_non_ent.healing_actions

    # Hyphenated and space-separated non-particle compound surnames
    p_hyph = standardize_person("Maria Garcia-Lopez")
    p_part = standardize_person("Maria Lopez")
    assert "GARCIA LOPEZ|MARIA" in p_hyph.person_alt_keys
    assert "LOPEZ|MARIA" in p_hyph.person_alt_keys
    assert compare_persons(p_hyph, p_part).match_type == "ALT_NAME_KEY_MATCH"

    # Comma-formatted space-separated compound surname ("Garcia Lopez, Maria")
    p_space_ln = standardize_person("Garcia Lopez, Maria")
    assert "GARCIA-LOPEZ|MARIA" in p_space_ln.person_alt_keys
    assert "LOPEZ|MARIA" in p_space_ln.person_alt_keys
    assert compare_persons(p_space_ln, p_part).match_type == "ALT_NAME_KEY_MATCH"

    # Hyphenated surname with single 1-char segment ("A-Smith" -> len(parts) < 2 branch)
    p_short_hyph = standardize_person("A-Smith, Maria")
    assert p_short_hyph.is_valid is True

    # Particle surname ("Van Der Beek, James") should NOT split particle parts into alt keys
    p_particle = standardize_person("Van Der Beek, James")
    assert p_particle.person_alt_keys == []

    # Deduplicate persons links middle-name go-by via PRK:{alt_key}
    p_clusters = deduplicate_persons(["W. Scott Simpson", "Scott Simpson", "William Scott Simpson"])
    assert len(p_clusters) == 1
    assert len(p_clusters[0].members) == 3

    # HTML entities in is_organization_name and split_compound_persons
    assert is_organization_name("Waddell &amp; Reed LLC") is True
    split_res = split_compound_persons("John &amp; Jane Smith")
    assert len(split_res) == 2
    assert split_res[0].first_name == "JOHN"
    assert split_res[1].first_name == "JANE"


def test_advisor_group_classification_standardization_and_comparison() -> None:
    assert classify_rep_entity(None) == RepEntityClass.INDIVIDUAL.value
    assert classify_rep_entity("   ") == RepEntityClass.INDIVIDUAL.value
    assert classify_rep_entity("A12 - House Account") == RepEntityClass.HOUSE_ACCOUNT.value
    assert classify_rep_entity("The Venezia Wealth Management Team") == RepEntityClass.TEAM.value
    assert classify_rep_entity("Smith &amp; Jones") == RepEntityClass.PARTNERSHIP.value
    assert classify_rep_entity("Scott Simpson") == RepEntityClass.INDIVIDUAL.value

    assert standardize_advisor_group(None).is_valid is False
    assert standardize_advisor_group("   ").is_valid is False
    assert standardize_advisor_group("---").is_valid is False

    # House account standardization
    g_house = standardize_advisor_group("B99 - Orphan / House Account")
    assert g_house.is_valid is True
    assert g_house.entity_class == RepEntityClass.HOUSE_ACCOUNT.value
    assert g_house.entity_key is not None and g_house.entity_key.startswith("HOUSE|")
    assert "REP_CODE_PREFIX_STRIPPED" in g_house.healing_actions
    assert g_house.to_dict()["entity_class"] == "HOUSE_ACCOUNT"

    # Diacritics + HTML entities + serial comma roster vs slash roster
    g_serial = standardize_advisor_group("The Vénézia, Koenig &amp; Cuozzo Wealth Advisors")
    g_slash = standardize_advisor_group("Cuozzo / Koenig / Venezia")
    assert "HTML_ENTITIES_DECODED" in g_serial.healing_actions
    assert "DIACRITICS_FOLDED" in g_serial.healing_actions
    assert g_serial.member_surname_key == "CUOZZO|KOENIG|VENEZIA"
    assert g_slash.member_surname_key == "CUOZZO|KOENIG|VENEZIA"

    # Non-HTML-entity ampersand branch ("&notentity;")
    g_non_ent = standardize_advisor_group("Smith &notentity; Jones Group")
    assert "HTML_ENTITIES_DECODED" not in g_non_ent.healing_actions

    # All conj_parts contain comma ("Smith, John & Doe, Jane") + multi-token person segment
    g_full_names = standardize_advisor_group("John Smith & Jane Doe Partnership")
    assert g_full_names.member_surname_key == "DOE|SMITH"

    g_comma_pairs = standardize_advisor_group("Smith, John & Doe, Jane")
    assert g_comma_pairs.member_surname_key == "DOE|SMITH"

    # Segment with only noise words or invalid person segment (e.g. org words or numbers)
    g_only_noise = standardize_advisor_group("Wealth Management Group")
    assert g_only_noise.is_valid is True
    assert g_only_noise.member_surname_key is None
    assert g_only_noise.confidence == 0.88

    g_numeric_seg = standardize_advisor_group("12345 / 67890 Partnership")
    assert g_numeric_seg.member_surname_key is None

    g_org_seg = standardize_advisor_group("Acme Capital Holdings / John Smith")
    assert g_org_seg.member_surname_key == "SMITH"

    # Empty sub-item in comma+conjunction split ("Venezia, , & Koenig")
    g_empty_sub = standardize_advisor_group("Venezia, , & Koenig")
    assert g_empty_sub.member_surname_key == "KOENIG|VENEZIA"

    # Comparisons
    cmp_inv = compare_advisor_groups(None, g_serial)
    assert isinstance(cmp_inv, AdvisorGroupComparisonResult)
    assert cmp_inv.match_type == "INVALID_INPUT"
    assert cmp_inv.to_dict()["match_type"] == "INVALID_INPUT"

    cmp_house = compare_advisor_groups(g_house, g_serial)
    assert cmp_house.is_match is False
    assert cmp_house.match_type == "HOUSE_ACCOUNT_MISMATCH"

    cmp_exact = compare_advisor_groups("Smith & Jones Group", "SMITH AND JONES GROUP")
    assert cmp_exact.is_match is True
    assert cmp_exact.match_type == "EXACT_GROUP_NAME"

    cmp_set = compare_advisor_groups(g_serial, g_slash)
    assert cmp_set.is_match is True
    assert cmp_set.match_type == "MEMBER_SURNAME_SET_MATCH"

    # Partial surname overlap >= 0.6 (3 of 4 shared -> 0.75) vs < 0.6 (2 of 4 shared -> 0.50)
    g_four = standardize_advisor_group("Cuozzo / Koenig / Venezia / Adams")
    cmp_partial_ok = compare_advisor_groups(g_serial, g_four)
    assert cmp_partial_ok.is_match is True
    assert cmp_partial_ok.match_type == "PARTIAL_MEMBER_SURNAME_OVERLAP"

    g_low_jaccard = standardize_advisor_group("Cuozzo / Koenig / Baker / Clark")
    cmp_partial_low = compare_advisor_groups(g_serial, g_low_jaccard)
    assert cmp_partial_low.is_match is False
    assert cmp_partial_low.match_type == "NO_MATCH"

    cmp_disjoint = compare_advisor_groups("Alpha / Beta", "Gamma / Delta")
    assert cmp_disjoint.is_match is False
    assert cmp_disjoint.match_type == "NO_MATCH"

    assert isinstance(g_serial, StandardizedAdvisorGroup)


def test_phone_toll_free_flag_and_switchboard_guardrails() -> None:
    p_tf = standardize_phone("1-800-555-1212", default_country="US")
    p_geo = standardize_phone("(212) 555-2671", default_country="US")
    assert p_tf.is_toll_free is True
    assert p_tf.to_dict()["is_toll_free"] is True
    assert p_geo.is_toll_free is False
    assert p_geo.to_dict()["is_toll_free"] is False

    # compare_contacts: two different advisors sharing firm 800 number -> SHARED_TOLL_FREE_SWITCHBOARD
    c1 = standardize_contact(
        person_name="Alice Walker",
        organization="Morgan Stanley",
        phone="800-869-3326",
        default_country="US",
    )
    c2 = standardize_contact(
        person_name="Robert Miller",
        organization="Wells Fargo Clearing Services",
        phone="800-869-3326",
        default_country="US",
    )
    cmp_tf = compare_contacts(c1, c2)
    assert cmp_tf.is_match is False
    assert cmp_tf.match_type == "SHARED_TOLL_FREE_SWITCHBOARD"

    # Same advisor + same 800 number -> MULTI_PILLAR_MATCH (allowed!)
    c1_dup = standardize_contact(
        person_name="Alice Walker",
        phone="800-869-3326",
        default_country="US",
    )
    cmp_same = compare_contacts(c1, c1_dup)
    assert cmp_same.is_match is True
    assert cmp_same.match_type == "MULTI_PILLAR_MATCH"

    # cluster_contact_records: exact toll-free + fuzzy toll-free blocked across distinct persons/orgs,
    # allowed when identity_tags match or are absent
    clusters = cluster_contact_records(
        [
            {"id": "1", "name": "Alice Walker", "phone": "800-869-3326"},
            {"id": "2", "name": "Robert Miller", "phone": "800-869-3326"},
            {"id": "3", "name": "Robert Miller", "phone": "800-869-3327"},  # 1-digit keypad/fuzzy vs Alice
            {"id": "4", "company": "Alpha Advisors LLC", "phone": "888-444-2222"},
            {"id": "5", "company": "Beta Capital Corp", "phone": "888-444-2222"},
            {"id": "6", "phone": "877-333-4444"},
            {"id": "7", "phone": "877-333-4444"},
        ],
        fuzzy_threshold=0.80,
    )
    by_members = [set(c.record_ids) for c in clusters]
    assert {"1"} in by_members
    assert {"2", "3"} in by_members
    assert {"4"} in by_members
    assert {"5"} in by_members
    assert {"6", "7"} in by_members


def test_external_identifiers_and_crd_hygiene() -> None:
    assert standardize_external_id(None).is_valid is False
    assert standardize_external_id("   ").is_valid is False

    # NaN / Inf / Scientific float corruption
    id_nan = standardize_external_id(float("nan"))
    assert id_nan.is_valid is False
    assert id_nan.is_placeholder is True
    assert "NAN_OR_INF_FLOAT" in id_nan.risk_flags

    id_flt_big = standardize_external_id(1.2345678901234568e19)
    assert id_flt_big.is_valid is False
    assert id_flt_big.is_corrupted_float is True

    id_str_sci = standardize_external_id("1.23457E+19")
    assert id_str_sci.is_valid is False
    assert id_str_sci.is_corrupted_float is True

    # Small float with .0 tail ("12345.0" or float 12345.0) vs fractional float ("123.45")
    id_flt_ok = standardize_external_id(12345.0)
    assert id_flt_ok.is_valid is True
    assert id_flt_ok.canonical_id == "12345"
    assert "FLOAT_DECIMAL_ZERO_STRIPPED" in id_flt_ok.healing_actions
    assert id_flt_ok.to_dict()["canonical_id"] == "12345"

    id_frac = standardize_external_id("123.45")
    assert id_frac.is_valid is False
    assert "INVALID_FRACTIONAL_ID" in id_frac.risk_flags

    # Placeholders & sentinels
    assert standardize_external_id("N/A").is_placeholder is True
    assert standardize_external_id("000000").is_placeholder is True
    assert standardize_external_id("9999999").is_placeholder is True

    # Leading zeros + pad_width + alphanumeric handling
    id_padded = standardize_external_id("004567", pad_width=8)
    assert id_padded.is_valid is True
    assert id_padded.canonical_id == "4567"
    assert id_padded.padded_id == "00004567"
    assert "LEADING_ZEROS_NORMALIZED" in id_padded.healing_actions

    id_alpha_ok = standardize_external_id("001A2B", pad_width=8, allow_alpha=True)
    assert id_alpha_ok.is_valid is True
    assert id_alpha_ok.canonical_id == "001A2B"
    assert id_alpha_ok.padded_id == "00001A2B"

    id_alpha_no = standardize_external_id("001A2B", allow_alpha=False)
    assert id_alpha_no.is_valid is False
    assert "NON_NUMERIC_CHARACTERS" in id_alpha_no.risk_flags

    # CRD hygiene
    crd_ok = standardize_crd("CRD# 00123456.0")
    assert isinstance(crd_ok, StandardizedIdentifier)
    assert crd_ok.is_valid is True
    assert crd_ok.canonical_id == "123456"
    assert "ID_PREFIX_STRIPPED" in crd_ok.healing_actions

    crd_too_long = standardize_crd("123456789")
    assert crd_too_long.is_valid is False
    assert "CRD_OUT_OF_RANGE" in crd_too_long.risk_flags

    # compare_external_ids across all outcomes
    cmp_corrupt = compare_external_ids("1.23457E+19", "1.23457E+19")
    assert isinstance(cmp_corrupt, IdentifierComparisonResult)
    assert cmp_corrupt.is_match is False
    assert cmp_corrupt.match_type == "CORRUPTED_FLOAT_ID"
    assert cmp_corrupt.to_dict()["match_type"] == "CORRUPTED_FLOAT_ID"

    cmp_inv = compare_external_ids("N/A", "12345")
    assert cmp_inv.is_match is False
    assert cmp_inv.match_type == "INVALID_INPUT"

    cmp_match = compare_external_ids("00123456", "123456.0", id_type="CRD")
    assert cmp_match.is_match is True
    assert cmp_match.match_type == "EXACT_CANONICAL_ID"

    cmp_dist = compare_external_ids(crd_ok, standardize_crd("654321"), id_type="CRD")
    assert cmp_dist.is_match is False
    assert cmp_dist.match_type == "DISTINCT_ID"
