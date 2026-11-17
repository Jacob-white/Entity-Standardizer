"""Unit tests for multi-signal partial-match scoring, M&A brand lineage, company acronyms, multi-root diminutives, roster scoring, and street core keys."""

from __future__ import annotations

from entity_standardizer import (
    EntityScoringProfile,
    MatchDisposition,
    RosterComparisonResult,
    ScoredEntityMatch,
    SignalEvidence,
    are_affiliated_brands,
    are_swapped_person_names,
    canonicalize_surname_variants,
    classify_company_role,
    compact_company_key,
    compare_companies,
    compare_persons,
    deduplicate_persons,
    explain_and_score_entities,
    extract_company_acronym,
    extract_street_core_key,
    is_generic_institution_name,
    is_synthetic_or_test_record,
    prepare_matching_arrow,
    prepare_matching_polars,
    resolve_brand_lineage,
    resolve_given_name_roots,
    score_member_rosters,
    split_glued_house_unit,
    standardize_address,
    standardize_company,
    standardize_contact,
    standardize_crd,
    standardize_email,
    standardize_person,
    stream_standardize_csv,
    synthesize_domain_match,
    synthesize_scored_match,
)


def test_address_glued_units_word_numbers_and_street_core_keys() -> None:
    assert split_glued_house_unit("") == ("", "")
    assert split_glued_house_unit("PO") == ("PO", "")
    assert split_glued_house_unit("ONE ORANGE WAY") == ("1 ORANGE WAY", "")
    assert split_glued_house_unit("3402A TRENT RD") == ("3402 TRENT RD", "STE A")
    assert split_glued_house_unit("100 MAIN ST") == ("100 MAIN ST", "")

    a_glued = standardize_address(street1="3402A Trent Rd", city="New Bern", state="NC", postal_code="28562", country="US")
    a_split = standardize_address(street1="3402 Trent Rd", street2="Ste A", city="New Bern", state="NC", postal_code="28562", country="US")
    assert a_glued.postal_building_key == a_split.postal_building_key

    a_word = standardize_address(street1="One Orange Way", city="Windsor", state="CT", postal_code="06095", country="US")
    a_num = standardize_address(street1="1 Orange Way", city="Windsor", state="CT", postal_code="06095", country="US")
    assert a_word.postal_address_key == a_num.postal_address_key

    assert extract_street_core_key(None) is None
    assert extract_street_core_key("   ") is None
    assert extract_street_core_key("PO BOX") is None
    assert extract_street_core_key("123") is None
    assert extract_street_core_key("302 W Main Ave") == "302|MAIN AVE"
    assert extract_street_core_key("302 Main Ave") == "302|MAIN AVE"
    assert extract_street_core_key("S Oak Ave Oakwood Tower Bldg 231 Fl 14") == "231|OAK AVE"
    assert extract_street_core_key("231 S Oak Ave Fl 14") == "231|OAK AVE"
    assert extract_street_core_key("500 BROADWAY") == "500|BROADWAY"
    assert extract_street_core_key("100 MAIN ST PLAZA") == "100|MAIN ST"
    assert extract_street_core_key("100 N OAK AVE S") == "100|OAK AVE"
    assert extract_street_core_key("231 OAK AVE OAK ST") == "231|OAK AVE"

    from entity_standardizer.address.models import canonicalize_us_street_for_postal_key
    from entity_standardizer.address.us_street_parser import _rule_based_us_street_parse

    assert canonicalize_us_street_for_postal_key("") == ""
    assert "NW" in _rule_based_us_street_parse("100 A D P BLVD NW")[0]
    assert "CENTER" in _rule_based_us_street_parse("800 COMMERCE CTR DR")[0]


def test_person_expanded_nicknames_multi_root_diminutives_and_edit1() -> None:
    assert resolve_given_name_roots(None) == ()
    assert resolve_given_name_roots("123") == ()
    assert resolve_given_name_roots("Jerry") == ("GERALD", "JEROME", "JEREMIAH")
    assert resolve_given_name_roots("Mitch") == ("MITCHELL", "MITCH")
    assert resolve_given_name_roots("Hrach") == ("HRACH",)

    p_mitch = standardize_person("Mitch H. Mercer")
    p_mitchell = standardize_person("Mitchell Hilton Mercer")
    cmp_mitch = compare_persons(p_mitch, p_mitchell)
    assert cmp_mitch.is_match is True
    assert cmp_mitch.match_type == "ROOT_NAME_MATCH"

    p_gabe = standardize_person("Gabe Bell")
    p_gabriel = standardize_person("Gabriel William Bell")
    assert compare_persons(p_gabe, p_gabriel).is_match is True

    p_jerry = standardize_person("Jerry Vance")
    p_jerome = standardize_person("Jerome Edward Vance")
    assert "VANCE|JEROME" in p_jerry.person_alt_keys
    cmp_jerry = compare_persons(p_jerry, p_jerome)
    assert cmp_jerry.is_match is True
    assert cmp_jerry.match_type == "MULTI_ROOT_DIMINUTIVE_MATCH"

    # Edit-1 given-name typo ('JABIER' <-> 'JAVIER') matches safely
    cmp_edit1 = compare_persons("Jabier Reyes", "Javier R. Reyes")
    assert cmp_edit1.is_match is True
    assert cmp_edit1.match_type == "GIVEN_NAME_EDIT1_MATCH"
    assert cmp_edit1.score == 0.89

    # Gender-pair suffixes ('MARIO' vs 'MARIA', 'PAUL' vs 'PAULA', 'ERIC' vs 'ERICA') must NOT false-positive
    assert compare_persons("Mario Rossi", "Maria Rossi").is_match is False
    assert compare_persons("Paul Smith", "Paula Smith").is_match is False
    assert compare_persons("Eric Jones", "Erica Jones").is_match is False
    assert compare_persons("Ian Bell", "Dan Bell").is_match is False


def test_company_abbreviations_acronyms_and_brand_lineage() -> None:
    # Multi-token B AND T -> BANK AND TRUST & SERVIES -> SERVICES
    c_bnt = standardize_company("First National B & T Co")
    assert c_bnt.base_name == "FIRST NATIONAL BANK AND TRUST"
    assert "TOKEN_ABBREVIATION_EXPANDED" in c_bnt.healing_actions

    c_bnt_svgs = standardize_company("First B & T Svgs LLC")
    assert c_bnt_svgs.base_name == "FIRST BANK AND TRUST SAVINGS"
    assert c_bnt_svgs.healing_actions.count("TOKEN_ABBREVIATION_EXPANDED") == 1

    c_pgim = standardize_company("PGIM European Servies Ltd")
    assert c_pgim.base_name == "PGIM EUROPEAN SERVICES"

    # Acronym extraction & matching
    assert extract_company_acronym(None) is None
    assert extract_company_acronym("of and the") is None
    assert extract_company_acronym("AB") is None
    assert extract_company_acronym("A B") is None
    assert extract_company_acronym("Alpha Beta") is None
    assert extract_company_acronym("IBM Corp") == "IBM"
    assert extract_company_acronym("Northbridge Partners") is None
    assert extract_company_acronym("Northbridge Sterling Oak") == "NSO"
    assert extract_company_acronym("NS and O Financial Services Group LLC") == "NSO"

    cmp_acr = compare_companies("Northbridge Sterling Oak", "NS and O Financial Services Group LLC")
    assert cmp_acr.is_match is True
    assert cmp_acr.match_type == "ACRONYM_MATCH"
    assert cmp_acr.score == 0.85

    # Two distinct 3-word names with same initials ('ABG') must NOT match on acronym
    cmp_non_acr = compare_companies("Alpha Beta Gamma LLC", "Apex Boston Global Inc")
    assert cmp_non_acr.is_match is False

    # M&A Brand Lineage resolution & matching
    assert resolve_brand_lineage(None) is None
    assert resolve_brand_lineage("Random Boutique Advisors LLC") is None
    assert resolve_brand_lineage("Securities America, Inc.") == "OSAIC"
    assert resolve_brand_lineage("Osaic Wealth, Inc.") == "OSAIC"
    assert are_affiliated_brands("Securities America Inc", "Osaic Wealth Inc") is True
    assert are_affiliated_brands("Piper Jaffray & Co.", "Piper Sandler & Co.") is True
    assert are_affiliated_brands("Goldman Sachs", "Morgan Stanley") is False

    cmp_lin = compare_companies("Securities America Inc", "Osaic Wealth Inc")
    assert cmp_lin.is_match is True
    assert cmp_lin.match_type == "BRAND_LINEAGE_MATCH"
    assert cmp_lin.score == 0.88


def test_roster_scoring_tiers() -> None:
    r_empty = score_member_rosters([], ["1001"])
    assert r_empty.match_type == "EMPTY_ROSTER"
    assert r_empty.to_dict()["score"] == 0.0

    r_disj = score_member_rosters(["1001", "1002"], ["2001", "2002"])
    assert r_disj.match_type == "DISJOINT_ROSTERS"

    r_exact2 = score_member_rosters(["1001", "1002"], ["1002", "1001"])
    assert isinstance(r_exact2, RosterComparisonResult)
    assert r_exact2.is_match is True
    assert r_exact2.match_type == "EXACT_ROSTER_MATCH"
    assert r_exact2.score == 0.98

    r_exact1_same = score_member_rosters(["1001"], ["1001"], same_firm=True)
    r_exact1_diff = score_member_rosters(["1001"], ["1001"], same_firm=False)
    assert r_exact1_same.score == 0.90
    assert r_exact1_diff.score == 0.78

    r_strong = score_member_rosters(["1", "2", "3", "4"], ["1", "2", "3", "5"], same_firm=True)
    assert r_strong.is_match is True
    assert r_strong.match_type == "STRONG_PARTIAL_ROSTER_MATCH"

    r_subset = score_member_rosters(["1", "2"], ["1", "2", "3", "4", "5"], same_firm=True)
    assert r_subset.is_match is True
    assert r_subset.match_type == "SAME_FIRM_ROSTER_SUBSET_MATCH"

    r_cand = score_member_rosters(["1", "2", "3", "4"], ["1", "2", "5", "6", "7"], same_firm=False)
    assert r_cand.is_match is False
    assert r_cand.is_partial_candidate is True
    assert r_cand.match_type == "PARTIAL_ROSTER_CANDIDATE"

    r_weak = score_member_rosters(["1", "2", "3", "4", "5"], ["1", "6", "7", "8", "9"], same_firm=False)
    assert r_weak.is_match is False
    assert r_weak.is_partial_candidate is False
    assert r_weak.match_type == "WEAK_ROSTER_OVERLAP"


def test_scoring_and_explanation_engine_all_dispositions() -> None:
    # 0. Empty / purely negative evidence
    no_ev = synthesize_scored_match([])
    assert no_ev.disposition == MatchDisposition.NO_MATCH.value
    assert no_ev.score == 0.0
    assert "No matching" in no_ev.explanation

    neg_only = synthesize_scored_match([SignalEvidence("FINRA_CRD", 0.10, "CRD differs", is_conflict=True)])
    assert neg_only.conflicting_signals == ("FINRA_CRD",)
    assert "Populated differences" in neg_only.explanation
    assert neg_only.evidence[0].to_dict()["is_conflict"] is True

    # 1. Hard ID + exact multi-pillar -> EXACT_MATCH
    ent_a = standardize_contact(
        person_name="Jerry Vance",
        organization="Securities America Inc",
        street1="302 W Main Ave",
        city="Springfield",
        state="IL",
        postal_code="62701",
        country="US",
        phone="217-555-0100",
        fax="217-555-0101",
        email="jerry.vance@examplewealth.com",
        website="https://examplewealth.com",
    )
    ent_b = standardize_contact(
        person_name="Jerome Edward Vance",
        organization="Osaic Wealth Inc",
        street1="302 Main Ave",
        city="Springfield",
        state="IL",
        postal_code="62701",
        country="US",
        phone="+12175550100",
        fax="+12175550101",
        email="jerry.vance@examplewealth.com",
        website="https://www.examplewealth.com",
    )
    exact_res = explain_and_score_entities(
        ent_a,
        ent_b,
        external_id_a="00000000000000001002",
        external_id_b="1002",
        crd_a="2001001",
        crd_b="2001001",
        member_roster_a=["2001001", "2001002"],
        member_roster_b=["2001001", "2001002"],
    )
    assert isinstance(exact_res, ScoredEntityMatch)
    assert exact_res.is_match is True
    assert exact_res.disposition == MatchDisposition.EXACT_MATCH.value
    assert "VALIDATED_ADDRESS" in exact_res.matched_signals
    assert "ORG_BRAND_LINEAGE" in exact_res.matched_signals
    assert exact_res.to_dict()["matched_signal_count"] >= 7

    # Inverted building-before-number address rescued via STREET_CORE_AND_ZIP5 + EXACT org
    core_res = explain_and_score_entities(
        {
            "person_name": "Mitchell Mercer",
            "organization": "Example Consulting Group LLC",
            "street1": "S Oak Ave Oakwood Tower Bldg 231 Fl 14",
            "city": "Saint Louis",
            "state": "MO",
            "postal_code": "63105",
            "country": "US",
        },
        {
            "person_name": "Mitchell Mercer",
            "organization": "Example Consulting Group LLC",
            "street1": "231 S Oak Ave",
            "street2": "Fl 14",
            "city": "St Louis",
            "state": "MO",
            "postal_code": "63105",
            "country": "US",
        },
        external_id_a="N/A",
        external_id_b="NONE",
    )
    assert core_res.is_match is True
    assert "STREET_CORE_AND_ZIP5" in core_res.matched_signals
    assert "ORGANIZATION_NAME" in core_res.matched_signals

    # 2. STRONG_MATCH via dict coercion + acronym + role email + exact address
    strong_res = explain_and_score_entities(
        {
            "organization": "Northbridge Sterling Oak",
            "street1": "500 Commerce Ctr",
            "city": "Princeton",
            "state": "NJ",
            "postal_code": "08540",
            "country": "US",
            "phone": "609-555-0188",
            "email": "info@northbridge-example.com",
        },
        {
            "organization": "NS and O Financial Services Group LLC",
            "street1": "500 Commerce Center",
            "city": "Princeton",
            "state": "NJ",
            "postal_code": "08540",
            "country": "US",
            "phone": "609-555-0188",
            "email": "info@northbridge-example.com",
        },
    )
    assert strong_res.is_match is True
    assert strong_res.disposition in (
        MatchDisposition.PROBABLE_MATCH.value,
        MatchDisposition.STRONG_MATCH.value,
        MatchDisposition.EXACT_MATCH.value,
    )
    assert "ORG_ACRONYM" in strong_res.matched_signals
    # Exercise STRONG_MATCH band explicitly (0.85 <= score < 0.95)
    strong_band = synthesize_scored_match(
        [SignalEvidence("PERSON", 0.60, "exact person"), SignalEvidence("PHONE", 0.70, "exact phone")]
    )
    assert strong_band.disposition == MatchDisposition.STRONG_MATCH.value

    # 3. PROBABLE_MATCH (0.70 <= score < 0.85) with relocated street in same ZIP5 + corporate email domain + toll-free phone
    prob_res = explain_and_score_entities(
        {
            "person_name": "Mitch Mercer",
            "organization": "Example Consulting Group",
            "street1": "100 Main St",
            "city": "St Louis",
            "state": "MO",
            "postal_code": "63105",
            "country": "US",
            "phone": "800-555-1212",
            "email": "mmercer@examplegroup.com",
        },
        {
            "person_name": "Mitchell Mercer",
            "organization": "Example Consulting Group LLC",
            "street1": "231 S Oak Ave",
            "city": "Saint Louis",
            "state": "MO",
            "postal_code": "63105",
            "country": "US",
            "phone": "800-555-1212",
            "email": "mitch.mercer@examplegroup.com",
        },
    )
    assert prob_res.is_match is True
    assert prob_res.disposition == MatchDisposition.PROBABLE_MATCH.value
    assert "POSTAL_ZIP5" in prob_res.matched_signals
    assert "CORPORATE_EMAIL_DOMAIN" in prob_res.matched_signals
    assert "TOLL_FREE_PHONE" in prob_res.matched_signals
    assert "STREET_ADDRESS" in prob_res.conflicting_signals

    # 4. POTENTIAL_MATCH (0.50 <= score < 0.70): clearing-firm office overlap (same building + same local phone, different org!)
    pot_res = explain_and_score_entities(
        {
            "organization": "Harbor Oak Capital Partners LLC",
            "street1": "100 North St",
            "city": "Metuchen",
            "state": "NJ",
            "postal_code": "08840",
            "country": "US",
            "phone": "732-555-0106",
        },
        {
            "organization": "Clearing Custodian LLC",
            "street1": "100 North St",
            "street2": "Ste 2A",
            "city": "Metuchen",
            "state": "NJ",
            "postal_code": "08840",
            "country": "US",
            "phone": "732-555-0106",
        },
        member_roster_a=["1", "2", "3", "4"],
        member_roster_b=["1", "2", "5", "6", "7"],
    )
    assert pot_res.is_match is False
    assert pot_res.is_potential_match is True
    assert pot_res.disposition == MatchDisposition.POTENTIAL_MATCH.value
    assert "Potential partial match" in pot_res.explanation
    assert "Does not fully match on" in pot_res.explanation
    assert "PARTIAL_MEMBER_ROSTER" in pot_res.matched_signals

    # 5. Below-threshold NO_MATCH with same city/state + conflicting external ID, CRD, person, phone, email, and disjoint rosters
    low_res = explain_and_score_entities(
        {
            "person_name": "John Smith",
            "organization": "Alpha Advisors LLC",
            "street1": "100 Wall St",
            "city": "New York",
            "state": "NY",
            "postal_code": "10005",
            "country": "US",
            "phone": "212-555-0101",
            "email": "john@gmail.com",
        },
        {
            "person_name": "Robert Brown",
            "organization": "Alpha Advisors LLC",
            "street1": "350 Park Ave",
            "city": "New York",
            "state": "NY",
            "postal_code": "10022",
            "country": "US",
            "phone": "212-555-0199",
            "email": "robert@yahoo.com",
        },
        external_id_a="10001",
        external_id_b="20002",
        crd_a="100111",
        crd_b="200222",
        member_roster_a=["1111111"],
        member_roster_b=["2222222"],
    )
    assert low_res.is_match is False
    assert low_res.is_potential_match is False
    assert low_res.disposition == MatchDisposition.NO_MATCH.value
    assert "Below threshold" in low_res.explanation
    assert "CITY_STATE" in low_res.matched_signals

    # Different state/city address conflict + non-matching website + empty roster + below-threshold NO_MATCH without conflicts
    diff_addr_res = explain_and_score_entities(
        {
            "organization": "Acme Wealth LLC",
            "street1": "100 Main St",
            "city": "Boston",
            "state": "MA",
            "postal_code": "02110",
            "country": "US",
            "website": "https://acmewealth.com",
        },
        {
            "organization": "Beta Wealth LLC",
            "street1": "200 Oak Ave",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78701",
            "country": "US",
            "website": "https://betawealth.com",
        },
        member_roster_a=[],
        member_roster_b=["111"],
    )
    assert "ADDRESS" in diff_addr_res.conflicting_signals

    # Potential match without conflicts & below-threshold without conflicts + person edit1/initial weights
    pot_no_conf = synthesize_scored_match([SignalEvidence("EMAIL", 0.55, "matching email")])
    assert pot_no_conf.is_potential_match is True
    assert "Does not fully match" not in pot_no_conf.explanation

    low_no_conf = synthesize_scored_match([SignalEvidence("CITY_STATE", 0.15, "same city")])
    assert low_no_conf.disposition == MatchDisposition.NO_MATCH.value
    assert "Conflicts:" not in low_no_conf.explanation

    # Person initial & edit1 weight tiers + empty address branch
    p_init_res = explain_and_score_entities(
        {"person_name": "J. Smith"},
        {"person_name": "John Smith"},
    )
    assert any(s.startswith("PERSON_") for s in p_init_res.matched_signals)

    p_edit_res = explain_and_score_entities(
        {"person_name": "Jabier Reyes"},
        {"person_name": "Javier Reyes"},
    )
    assert "PERSON_GIVEN_NAME_EDIT1_MATCH" in p_edit_res.matched_signals


def test_person_credentials_false_inversion_guard_and_slash_designations() -> None:
    # Known wealth/Canadian/fiduciary comma-separated credentials
    p_can = standardize_person("Mr. Michael Baker CFA, CIM, FCSI")
    assert p_can.salutation == "MR"
    assert p_can.first_name == "MICHAEL"
    assert p_can.last_name == "BAKER"
    assert p_can.credentials == ["CIM", "FCSI", "CFA"]
    assert "LAST_FIRST_UNINVERTED" not in p_can.healing_actions

    # Unknown regional/future ALL-CAPS credential codes after comma must NOT trigger false Last, First inversion
    p_unk1 = standardize_person("Mr. Michael Baker CFA, CWM, FMAQ")
    assert p_unk1.first_name == "MICHAEL"
    assert p_unk1.last_name == "BAKER"
    assert "CWM" in p_unk1.credentials and "FMAQ" in p_unk1.credentials and "CFA" in p_unk1.credentials

    p_unk2 = standardize_person("Michael Baker, CWM, CBV")
    assert p_unk2.first_name == "MICHAEL"
    assert p_unk2.last_name == "BAKER"
    assert p_unk2.credentials == ["CWM", "CBV"]

    # Slash-joined credentials vs non-credential slash token after comma
    p_slash_cred = standardize_person("John Smith CPA/PFS")
    assert p_slash_cred.first_name == "JOHN"
    assert p_slash_cred.last_name == "SMITH"
    assert p_slash_cred.credentials == ["CPA", "PFS"]

    p_non_cred_slash = standardize_person("Smith, John A/B")
    assert p_non_cred_slash.last_name == "SMITH"
    assert p_non_cred_slash.first_name == "JOHN"
    assert p_non_cred_slash.middle_name == "AB"

    # Leading punctuation-only comma segment must not misalign segment 0 tokens
    p_lead_punct_comma = standardize_person("., John Smith")
    assert p_lead_punct_comma.first_name == "JOHN"
    assert p_lead_punct_comma.last_name == "SMITH"

    # Wealth retirement credentials & ambiguous mixed-case guard ('CFS'/'CES'/'CIS' uppercase vs mixed-case surname)
    p_crps = standardize_person("Mr. Joshua Andrew Carter CRPS")
    assert p_crps.first_name == "JOSHUA"
    assert p_crps.middle_name == "ANDREW"
    assert p_crps.last_name == "CARTER"
    assert p_crps.credentials == ["CRPS"]

    p_ces_cred = standardize_person("John Michael Smith CES")
    assert p_ces_cred.last_name == "SMITH"
    assert p_ces_cred.credentials == ["CES"]

    p_ces_surname = standardize_person("John Michael Ces")
    assert p_ces_surname.last_name == "CES"
    assert p_ces_surname.credentials == []


def test_person_salutations_suffixes_spousal_and_slash_given_names() -> None:
    # Expanded religious, judicial, civic, military, and joint salutations
    p_sis = standardize_person("Sister Mary Walsh")
    assert p_sis.salutation == "SR"
    assert p_sis.first_name == "MARY"
    assert p_sis.last_name == "WALSH"

    p_sr_lead = standardize_person("Sr. Mary Catherine Walsh")
    assert p_sr_lead.salutation == "SR"
    assert p_sr_lead.first_name == "MARY"
    assert p_sr_lead.middle_name == "CATHERINE"
    assert p_sr_lead.last_name == "WALSH"

    p_sr_two = standardize_person("Sr. Walsh")
    assert p_sr_two.salutation is None
    assert p_sr_two.first_name == "SR"
    assert p_sr_two.last_name == "WALSH"

    p_1lt = standardize_person("1Lt. James Miller")
    assert p_1lt.salutation == "LT"
    assert p_1lt.first_name == "JAMES"
    assert p_1lt.last_name == "MILLER"

    p_joint = standardize_person("Mr. & Mrs. John Smith")
    assert p_joint.salutation == "MR_AND_MRS"
    assert p_joint.first_name == "JOHN"
    assert p_joint.last_name == "SMITH"

    # Higher Roman numerals & contextual 'I' suffix vs middle/trailing initial 'I.'
    p_vi = standardize_person("Mr. Jordan Wesley Grant VI")
    assert p_vi.last_name == "GRANT"
    assert p_vi.generational_suffix == "VI"

    p_i_comma = standardize_person("John Robert Smith, I")
    assert p_i_comma.last_name == "SMITH"
    assert p_i_comma.generational_suffix == "I"

    p_i_inline = standardize_person("John Robert Smith I")
    assert p_i_inline.last_name == "SMITH"
    assert p_i_inline.generational_suffix == "I"

    p_i_period = standardize_person("John Robert Smith I.")
    assert p_i_period.generational_suffix is None
    assert p_i_period.last_name == "I"

    # Dual/spousal & slash-paired given names
    p_spouse = standardize_person("Mr. John & Jane Smith")
    assert p_spouse.salutation == "MR"
    assert p_spouse.first_name == "JOHN"
    assert p_spouse.last_name == "SMITH"
    assert "SMITH|JANE" in p_spouse.person_alt_keys
    assert "SECONDARY_PERSON_EXTRACTED" in p_spouse.healing_actions

    # Same root secondary given name ('Bob & Robert Smith') does not duplicate person_root_key
    p_same_sec = standardize_person("Bob & Robert Smith")
    assert p_same_sec.person_root_key == "SMITH|ROBERT"
    assert "SMITH|ROBERT" not in p_same_sec.person_alt_keys
    assert "SECONDARY_PERSON_EXTRACTED" not in standardize_person("John & CFP Smith").healing_actions

    p_slash_given = standardize_person("Tyler/James Miller")
    assert p_slash_given.first_name == "TYLER"
    assert p_slash_given.last_name == "MILLER"
    assert "MILLER|JAMES" in p_slash_given.person_alt_keys

    p_short_slash = standardize_person("A/B Miller")
    assert "SECONDARY_PERSON_EXTRACTED" not in p_short_slash.healing_actions


def test_surname_variants_clerical_abbreviations_and_two_letter_initialisms() -> None:
    assert canonicalize_surname_variants(None) == ()
    assert canonicalize_surname_variants("'- ") == ()

    # O Connor / O'Connor / OConnor
    o_vars = canonicalize_surname_variants("O CONNOR")
    assert "O'CONNOR" in o_vars and "OCONNOR" in o_vars
    assert compare_persons("O Connor, Sean", "Sean O'Connor").match_type == "PARTICLE_SURNAME_MATCH"

    # Particle collapsing & Saint/St & Mc/Mac Gaelic folding (without false-folding Machado!)
    assert "VANDERBEEK" in canonicalize_surname_variants("VAN DER BEEK")
    assert "ST CLAIR" in canonicalize_surname_variants("SAINT CLAIR")
    assert "STCLAIR" in canonicalize_surname_variants("SAINT CLAIR")
    assert "SAINT CLAIR" in canonicalize_surname_variants("ST CLAIR")
    assert "SAINT CLAIR" in canonicalize_surname_variants("STCLAIR")
    assert "MACDONALD" in canonicalize_surname_variants("MC DONALD")
    assert "MCDONALD" in canonicalize_surname_variants("MAC DONALD")
    assert "MACDONALD" in canonicalize_surname_variants("MCDONALD")
    assert "MCDONALD" in canonicalize_surname_variants("MACDONALD")
    assert "MCHADO" not in canonicalize_surname_variants("MACHADO")

    cmp_part = compare_persons("Jerry Van Der Beek", "Gerald Vanderbeek")
    assert cmp_part.is_match is True
    assert cmp_part.match_type == "PARTICLE_SURNAME_MATCH"

    clusters = deduplicate_persons(["William Van Der Beek", "Wm. Vanderbeek", "Jane Machado"])
    assert len(clusters) == 2

    # Clerical abbreviations
    assert standardize_person("Jos. Miller").root_first_name == "JOSEPH"
    assert standardize_person("Chas. Brown").root_first_name == "CHARLES"
    assert standardize_person("Jas. Taylor").root_first_name == "JAMES"

    # Two-letter initialisms ('TJ' <-> 'T. J.' <-> 'Thomas Joseph') in both argument orders
    p_tj = standardize_person("TJ Smith")
    p_t_j = standardize_person("T. J. Smith")
    assert "SMITH|T|J" in p_tj.person_alt_keys
    assert "SMITH|TJ" in p_t_j.person_alt_keys

    c_tj_1 = compare_persons("TJ Smith", "Thomas Joseph Smith")
    assert c_tj_1.is_match is True
    assert c_tj_1.match_type == "TWO_LETTER_INITIALISM_MATCH"

    c_tj_2 = compare_persons("Thomas Joseph Smith", "TJ Smith")
    assert c_tj_2.is_match is True
    assert c_tj_2.match_type == "TWO_LETTER_INITIALISM_MATCH"

    c_tj_3 = compare_persons("TJ Smith", "T. J. Smith")
    assert c_tj_3.is_match is True


def test_pre_match_upgrades_leading_creds_swaps_compact_roles_synthetics_and_batch_arrow(tmp_path) -> None:
    import polars as pl
    import pyarrow as pa

    # 1. Leading credentials + new nicknames ('Herb', 'Ernie', 'Geoff')
    p_cfm = standardize_person("CFM Bill Sterling")
    assert p_cfm.first_name == "BILL"
    assert p_cfm.root_first_name == "WILLIAM"
    assert p_cfm.last_name == "STERLING"
    assert "CFM" in p_cfm.credentials

    p_cpa = standardize_person("CPA Gregory K Bennett")
    assert p_cpa.first_name == "GREGORY"
    assert p_cpa.middle_name == "K"
    assert p_cpa.last_name == "BENNETT"
    assert "CPA" in p_cpa.credentials

    assert standardize_person("Herb Grafton Sharp").root_first_name == "HERBERT"
    assert standardize_person("Ernie Navarro").root_first_name == "ERNEST"
    assert standardize_person("Geoff George").root_first_name == "GEOFFREY"

    # 2. Multi-initial middle + unhyphenated 2-word surname split + swapped Last First
    assert compare_persons("C S Krishnan", "Chandra Sekhar Krishnan").match_type == "TWO_LETTER_INITIALISM_MATCH"
    assert compare_persons("Chandra Sekhar Krishnan", "C S Krishnan").match_type == "TWO_LETTER_INITIALISM_MATCH"
    assert compare_persons("Elena Gomez Vega", "Maria Elena Gomez Vega").match_type == "ALT_NAME_KEY_MATCH"
    assert are_swapped_person_names("Marlowe Julianne", "Julie Marlowe") is True
    assert are_swapped_person_names("Smith William", "Bill Smith") is True
    assert are_swapped_person_names("Julie Marlowe", "Marlowe Julianne") is True
    assert are_swapped_person_names("John Smith", "Jane Doe") is False
    assert are_swapped_person_names(None, "Julie Marlowe") is False

    # 3. Compact company key ('E TRADE' <-> 'ETRADE', 'U S BANCORP' <-> 'US BANCORP') & corporate role classification
    assert compact_company_key(None) is None
    assert compact_company_key("BlackRock") == "BLACKROCK"
    assert compact_company_key("U S Bancorp") == "US BANCORP"
    assert compact_company_key("E Trade Savings Bank") == "ETRADE SAVINGS BANK"
    cmp_etrade = compare_companies("ETrade Savings Bank", "E Trade Savings Bank")
    assert cmp_etrade.is_match is True and cmp_etrade.match_type == "COMPACT_SPACING_MATCH"
    assert resolve_brand_lineage("Investors Group Financial Services Inc") == "IGM FINANCIAL"
    assert resolve_brand_lineage("IG Wealth Management Inc") == "IGM FINANCIAL"

    assert classify_company_role(None) == "UNKNOWN"
    assert classify_company_role("Example Omnibus Terminated") == "OMNIBUS_OR_TERMINATED"
    assert classify_company_role("Raymond James Trust") == "TRUST_FIDUCIARY"
    assert classify_company_role("Example Private Fund Advisors") == "PRIVATE_FUND"
    assert classify_company_role("Blackstone Holdings LP") == "HOLDING_PARENT"
    assert classify_company_role("Morgan Stanley LLC") == "OPERATING_ENTITY"

    # 4. Synthetic/test detection, wealth role-emails & EntityScoringProfile
    assert standardize_crd("").is_placeholder is False
    assert standardize_crd("999888777").is_placeholder is True
    assert standardize_crd("8888888").is_placeholder is True
    assert is_synthetic_or_test_record(name="Test Z Sandbox Record") is True
    assert is_synthetic_or_test_record(email="test@example.com") is True
    assert is_synthetic_or_test_record(crd="999888777") is True
    assert is_synthetic_or_test_record(external_id="00000000") is True
    assert is_synthetic_or_test_record(name="Jane Doe", email="jane@example-ria.com", crd="123456") is False

    assert standardize_email("clientservice@example-ria.com").is_role_account is True
    dom_res = synthesize_domain_match(EntityScoringProfile.FIRM, [SignalEvidence("BRAND_LINEAGE", 0.35, "same family")])
    assert dom_res.disposition == MatchDisposition.NO_MATCH.value

    # 5. Batch CSV & Arrow/Polars pre-match schema parity (include_matching_keys=True + prepare_matching_arrow/polars)
    csv_in = tmp_path / "in.csv"
    csv_out = tmp_path / "out.csv"
    csv_in.write_text(
        "phone,country,address,company,person_name,email,website\n"
        "800-555-0100,US,3402A Trent Rd New Bern NC 28562,E Trade Savings Bank,Herb Sharp,clientservice@example-bank.com,https://example-bank.com\n",
        encoding="utf-8",
    )
    rows = stream_standardize_csv(
        csv_in,
        csv_out,
        address_col="address",
        company_col="company",
        person_col="person_name",
        email_col="email",
        url_col="website",
        include_matching_keys=True,
    )
    assert rows == 1
    out_text = csv_out.read_text(encoding="utf-8")
    assert "phone_is_toll_free" in out_text
    assert "address_street_core_key" in out_text
    assert "company_compact_key" in out_text
    assert "person_surname_variants" in out_text
    assert "email_is_role_account" in out_text

    # Test prepare_matching_arrow (Table + RecordBatch) & prepare_matching_polars (DF + LazyFrame + missing cols)
    tbl = pa.table(
        {
            "phone": ["+14155552671"],
            "country": ["US"],
            "address": ["100 Main St New York NY 10005"],
            "company": ["AXA Advisors LLC"],
            "person_name": ["Van Der Beek, James"],
            "email": ["james@axa.com"],
            "website": ["https://axa.com"],
        }
    )
    res_tbl = prepare_matching_arrow(tbl)
    assert res_tbl.column("phone_is_toll_free").to_pylist() == [False]
    assert res_tbl.column("company_brand_lineage").to_pylist() == ["EQUITABLE"]
    assert "VANDERBEEK" in res_tbl.column("person_surname_variants").to_pylist()[0]
    assert prepare_matching_arrow(pa.table({"person_name": ["Jane Doe"]}), phone_col=None).num_rows == 1

    batch_in = tbl.to_batches()[0]
    res_batch = prepare_matching_arrow(batch_in)
    assert isinstance(res_batch, pa.RecordBatch)

    min_df = pl.DataFrame({"phone": ["+14155552671"]})
    res_pl = prepare_matching_polars(
        min_df.lazy(),
        country_col=None,
        address_col=None,
        company_col=None,
        person_col=None,
        email_col=None,
        url_col=None,
    ).collect()
    assert res_pl["phone_is_toll_free"].to_list() == [False]


def test_extended_lineages_typo_possessive_intersections_and_ca_domains() -> None:
    from entity_standardizer.web import extract_registrable_domain

    assert are_affiliated_brands("Sigma Planning Corp", "Parkland Securities LLC") is True
    assert resolve_brand_lineage("SPC") == "SIGMA FINANCIAL"
    assert resolve_brand_lineage("Sigma Financial Corp") == "SIGMA FINANCIAL"
    assert resolve_brand_lineage("Securities Service Network LLC") == "OSAIC"
    assert resolve_brand_lineage("Concourse Financial Group") == "CETERA"
    assert are_affiliated_brands("Assante Wealth Management", "CI Assante Capital") is True
    assert resolve_brand_lineage("Corient Partners LLC") == "CI FINANCIAL"
    assert are_affiliated_brands("PNC Wealth Management LLC", "PNC Capital Advisors") is True
    assert are_affiliated_brands("BOKF NA", "BOK Financial Securities") is True

    typo_comp = standardize_company("Northstar Asset Mangement & Securites LLC")
    assert typo_comp.base_name == "NORTHSTAR ASSET MANAGEMENT AND SECURITIES"
    assert "TOKEN_ABBREVIATION_EXPANDED" in typo_comp.healing_actions

    cmp_poss = compare_companies("Bank of Lee S Summit", "Bank of Lees Summit")
    assert cmp_poss.is_match is True
    assert cmp_poss.match_type == "COMPACT_SPACING_MATCH"
    assert compact_company_key("Alpha Beta S") == "ALPHA BETA S"
    assert compact_company_key("E Trade Bank") == "ETRADE BANK"

    assert extract_street_core_key("10TH & OAK 500 MAPLEWOOD DR STE B") == "500|MAPLEWOOD DR"
    assert extract_street_core_key("10TH & OAK ST") == "10TH|OAK ST"

    assert extract_registrable_domain("www.college.on.ca")[0] == "college.on.ca"
    assert extract_registrable_domain("portal.qc.ca")[0] == "portal.qc.ca"
    assert extract_registrable_domain("on.ca")[0] is None
    assert extract_registrable_domain("www.banco.com.pa")[0] == "banco.com.pa"
    assert extract_registrable_domain("com.pa")[0] is None

    assert is_generic_institution_name("") is False
    assert is_generic_institution_name(None) is False
    assert is_generic_institution_name("State Bank") is True
    assert is_generic_institution_name("Citizens Savings Bank") is True
    assert is_generic_institution_name("American Bank & Trust Co.") is True
    assert is_generic_institution_name("Oakwood Wealth Management LLC") is False
    assert is_generic_institution_name(standardize_company("First National Bank")) is True

    assert "ANDRES" in resolve_given_name_roots("Andy")
    assert "KATHLEEN" in resolve_given_name_roots("Katie")
    assert "LESLIE" in resolve_given_name_roots("Les")
    assert "RANDALL" in resolve_given_name_roots("Randy")
    assert "NICOLE" in resolve_given_name_roots("Niki")
    assert "VIRGINIA" in resolve_given_name_roots("Ginger")
    assert "SUZANNA" in resolve_given_name_roots("Suzi")
    assert "STELIANOS" in resolve_given_name_roots("Stelio")

    assert resolve_brand_lineage("American Portfolios Advisors Inc") == "OSAIC"
    assert resolve_brand_lineage("Signator Investors Inc") == "OSAIC"
    assert resolve_brand_lineage("Questar Capital Corp") == "OSAIC"
    assert are_affiliated_brands("Peapack-Gladstone Bank", "Peapack Private Bank & Trust") is True
    assert are_affiliated_brands("BFC Planning Inc", "Berthel Fisher & Company") is True
    assert are_affiliated_brands("Securities Mgmt & Research Inc", "BFC Planning Inc") is True
    assert standardize_company("HighPoint Advisor Group LLC").brand_key == "HIGHPOINT"
    assert standardize_company("Spearhead Administrative Services LLC").brand_key == "SPEARHEAD"
    assert standardize_company("Tri-Ad Actuaries Inc").brand_key == "TRI AD"
    assert are_affiliated_brands("MML Investors Services LLC", "MSI Financial Services Inc") is True
    assert resolve_brand_lineage("MassMutual Retirement Services") == "EMPOWER"



