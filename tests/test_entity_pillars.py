"""Comprehensive tests for Organization, Person, Job Title, Email, URL, Social, and Joint Multi-Pillar Standardization."""

from __future__ import annotations

import json

import pytest

from entity_standardizer import (
    CrossHealingAction,
    StandardizedCompany,
    StandardizedContact,
    StandardizedEntity,
    StandardizedOrganization,
    StandardizedUrl,
    StandardizedWebsite,
    batch_standardize_contacts,
    batch_standardize_entities,
    standardize_company,
    standardize_contact,
    standardize_email,
    standardize_entity,
    standardize_job_title,
    standardize_organization,
    standardize_person,
    standardize_social,
    standardize_url,
    standardize_website,
)
from entity_standardizer.web import extract_registrable_domain, infer_country_from_domain
from phone_standardizer.cli import main as cli_main


def test_company_standardization_and_legal_suffixes() -> None:
    assert StandardizedOrganization is StandardizedCompany
    assert standardize_organization is standardize_company

    # Empty / None / punctuation-only inputs
    assert standardize_company(None).is_valid is False
    assert standardize_company("   ").is_valid is False
    assert standardize_company("...").is_valid is False

    # Dotted and spaced initialisms, ampersand, leading article, legal suffix
    c_ibm = standardize_company("The I. B. M. Corporation")
    assert c_ibm.is_valid is True
    assert c_ibm.base_name == "IBM"
    assert c_ibm.legal_suffix == "CORP"
    assert c_ibm.legal_name == "IBM CORP"
    assert c_ibm.brand_stem == "IBM"
    assert c_ibm.company_key == "IBM|CORP"
    assert c_ibm.brand_key == "IBM"
    assert c_ibm.phonetic_key is not None
    assert "INITIALISM_COLLAPSED" in c_ibm.healing_actions
    assert "LEADING_ARTICLE_STRIPPED" in c_ibm.healing_actions
    assert "LEGAL_SUFFIX_NORMALIZED" in c_ibm.healing_actions
    assert c_ibm.to_dict()["legal_name"] == "IBM CORP"

    c_spaced = standardize_company("I B M Holdings & Group LLC")
    assert c_spaced.base_name == "IBM HOLDINGS AND GROUP"
    assert c_spaced.brand_stem == "IBM"
    assert c_spaced.legal_suffix == "LLC"
    assert "AMPERSAND_NORMALIZED" in c_spaced.healing_actions
    assert "INITIALISM_COLLAPSED" in c_spaced.healing_actions

    # Multi-token and single-token ISO 20275 legal suffixes & country inference
    cases = [
        ("Acme Sociedad Anonima de Capital Variable", "ACME", "SA DE CV", "MX"),
        ("Beta S.A. de C.V.", "BETA", "SA DE CV", "MX"),
        ("Gamma Professional Limited Liability Company", "GAMMA", "PLLC", None),
        ("Delta Limited Liability Company", "DELTA", "LLC", None),
        ("Epsilon Limited Liability Partnership", "EPSILON", "LLP", None),
        ("Barclays Public Limited Company", "BARCLAYS", "PLC", "GB"),
        ("Atlassian Pty Ltd", "ATLASSIAN", "PTY LTD", "AU"),
        ("BHP Proprietary Limited", "BHP", "PTY LTD", "AU"),
        ("Bosch GmbH & Co. KG", "BOSCH", "GMBH", "DE"),
        ("Sony Kabushiki Kaisha", "SONY", "KK", "JP"),
        ("K.K. Toyota", "TOYOTA", "KK", "JP"),
        ("Omega Limited Partnership", "OMEGA", "LP", None),
        ("Smith & Associates, P.C.", "SMITH AND ASSOCIATES", "PC", None),
        ("Total Societe Anonyme", "TOTAL", "SA", None),
        ("Renault S.A.R.L.", "RENAULT", "SARL", "FR"),
        ("Airbus SAS", "AIRBUS", "SAS", "FR"),
        ("Ferrari S.p.A.", "FERRARI", "SPA", "IT"),
        ("Pirelli S.r.l.", "PIRELLI", "SRL", "IT"),
        ("ASML Holding N.V.", "ASML HOLDING", "NV", "NL"),
        ("Booking.com B.V.", "BOOKING COM", "BV", "NL"),
        ("Petrobras Ltda.", "PETROBRAS", "LTDA", "BR"),
        ("Nokia Oyj", "NOKIA", "OY", "FI"),
        ("Spotify AB", "SPOTIFY", "AB", "SE"),
        ("Equinor ASA", "Equinor".upper(), "AS", "NO"),
        ("Novo Nordisk A/S", "NOVO NORDISK", "AS", None),
        ("Lego ApS", "LEGO", "APS", "DK"),
        ("Acme & Co.", "ACME", "CO", None),
        ("Acme & Limited Liability Company", "ACME", "LLC", None),
    ]
    for raw, exp_base, exp_sfx, exp_country in cases:
        res = standardize_company(raw)
        assert res.is_valid is True
        assert res.base_name == exp_base
        assert res.legal_suffix == exp_sfx
        assert res.inferred_country_iso2 == exp_country

    # Explicit country override and single-word company without legal suffix
    c_single = standardize_company("Stripe", country="US")
    assert c_single.base_name == "STRIPE"
    assert c_single.legal_suffix is None
    assert c_single.inferred_country_iso2 == "US"
    assert c_single.confidence == 0.92

    # Numeric-only company name (empty soundex)
    c_num = standardize_company("360")
    assert c_num.base_name == "360"
    assert c_num.phonetic_key is None


def test_company_dba_fka_and_branch_extraction() -> None:
    # Parenthesized DBA, FKA, and Branch
    c1 = standardize_company("Alphabet Inc. (d/b/a The Google LLC) (f/k/a The BackRub Inc.) (West Coast Division)")
    assert c1.legal_name == "ALPHABET INC"
    assert c1.dba_name == "GOOGLE"
    assert c1.fka_name == "BACKRUB INC"
    assert c1.branch_unit == "WEST COAST DIVISION"
    assert "DBA_EXTRACTED" in c1.healing_actions
    assert "FKA_EXTRACTED" in c1.healing_actions
    assert "BRANCH_UNIT_EXTRACTED" in c1.healing_actions

    # Inline FKA followed by DBA and trailing hyphen branch
    c2 = standardize_company("Meta Platforms, Inc. formerly known as Facebook Inc. DBA Meta - Menlo Park HQ")
    assert c2.legal_name == "META PLATFORMS INC"
    assert c2.fka_name == "FACEBOOK INC"
    assert c2.dba_name == "META"
    assert c2.branch_unit == "MENLO PARK HQ"

    # Inline FKA without DBA
    c3 = standardize_company("Block, Inc. f/k/a Square")
    assert c3.legal_name == "BLOCK INC"
    assert c3.fka_name == "SQUARE"
    assert c3.dba_name is None

    # Inline DBA without FKA, including ampersand and dotted/spaced initialisms in DBA
    c4 = standardize_company("Federal Express Corp. doing business as A.B.C. & X Y Z")
    assert c4.legal_name == "FEDERAL EXPRESS CORP"
    assert c4.dba_name == "ABC AND XYZ"


def test_person_and_job_title_standardization() -> None:
    assert standardize_person(None).is_valid is False
    assert standardize_person("   ").is_valid is False
    assert standardize_person(", , ,").is_valid is False
    assert standardize_person("()").is_valid is False
    assert standardize_person("..., Jr.").is_valid is False

    # Salutation, parenthetical nickname, middle initial, compound surname, suffix, credentials
    p1 = standardize_person("Dr. Robert (Bob) J. Van Der Beek, Jr., MD, PhD")
    assert p1.is_valid is True
    assert p1.salutation == "DR"
    assert p1.first_name == "ROBERT"
    assert p1.root_first_name == "ROBERT"
    assert p1.middle_name == "J"
    assert p1.last_name == "VAN DER BEEK"
    assert p1.nickname == "BOB"
    assert p1.generational_suffix == "JR"
    assert p1.credentials == ["MD", "PHD"]
    assert p1.full_name == "ROBERT J VAN DER BEEK JR"
    assert p1.person_key == "VAN DER BEEK|ROBERT|J|JR"
    assert p1.person_root_key == "VAN DER BEEK|ROBERT"
    assert p1.to_dict()["credentials"] == ["MD", "PHD"]

    # Last, First inversion with middle segment suffix/credentials and salutation
    p2 = standardize_person("Smith, Jr., PhD, Dr. Bob J. MD")
    assert p2.salutation == "DR"
    assert p2.first_name == "BOB"
    assert p2.root_first_name == "ROBERT"
    assert p2.middle_name == "J"
    assert p2.last_name == "SMITH"
    assert p2.generational_suffix == "JR"
    assert "PHD" in p2.credentials and "MD" in p2.credentials
    assert "LAST_FIRST_UNINVERTED" in p2.healing_actions
    assert "NICKNAME_RESOLVED_TO_ROOT" in p2.healing_actions
    assert p2.person_root_key == "SMITH|ROBERT"

    # Salutation on first segment of Last, First and trailing suffix on given segment
    p3 = standardize_person("Dr. Jones, William III")
    assert p3.salutation == "DR"
    assert p3.last_name == "JONES"
    assert p3.first_name == "WILLIAM"
    assert p3.generational_suffix == "III"

    # Inline trailing credentials and generational suffix without commas
    p4 = standardize_person("Prof. Rev. Elizabeth Margaret Taylor Sr. JD CPA MBA")
    assert p4.salutation == "REV"
    assert p4.first_name == "ELIZABETH"
    assert p4.middle_name == "MARGARET"
    assert p4.last_name == "TAYLOR"
    assert p4.generational_suffix == "SR"
    assert p4.credentials == ["JD", "CPA", "MBA"]

    # Parenthetical credential & generational suffix, plus first initial + nickname root resolution
    p5 = standardize_person('R. "Bob" Smith (Jr.) (CPA) (CPA)')
    assert p5.first_name == "R"
    assert p5.nickname == "BOB"
    assert p5.root_first_name == "ROBERT"
    assert p5.generational_suffix == "JR"
    assert p5.credentials == ["CPA"]

    # Two-token and single-token names + Second nickname ignored when first already extracted
    p6 = standardize_person("Bill (Billy) 'Will' Gates")
    assert p6.first_name == "BILL"
    assert p6.root_first_name == "WILLIAM"
    assert p6.last_name == "GATES"
    assert p6.nickname == "BILLY"

    p7 = standardize_person("Madonna")
    assert p7.first_name == "MADONNA"
    assert p7.last_name is None
    assert p7.confidence == 0.78

    # Job titles: abbreviations, seniority levels, and departments
    assert standardize_job_title(None).is_valid is False
    assert standardize_job_title("   ").is_valid is False
    assert standardize_job_title("---").is_valid is False

    title_cases = [
        ("CEO & Co-Founder", "CHIEF EXECUTIVE OFFICER AND CO-FOUNDER", "C_SUITE", "EXECUTIVE"),
        ("Managing Partner", "MANAGING PARTNER", "OWNER_PARTNER", "EXECUTIVE"),
        ("Sr. VP of Eng", "SENIOR VICE PRESIDENT OF ENGINEER", "VP", "ENGINEERING"),
        ("Head of Finance & Accounting", "HEAD OF FINANCE AND ACCOUNTING", "DIRECTOR", "FINANCE"),
        ("Mktg Mgr", "MARKETING MANAGER", "MANAGER", "MARKETING"),
        ("Principal Sales Architect", "PRINCIPAL SALES ARCHITECT", "SENIOR", "ENGINEERING"),
        ("Enterprise Account Executive", "ENTERPRISE ACCOUNT EXECUTIVE", "INDIVIDUAL_CONTRIBUTOR", "SALES"),
        ("Supply Chain Ops Supervisor", "SUPPLY CHAIN OPERATIONS SUPERVISOR", "MANAGER", "OPERATIONS"),
        ("Assoc. Legal Counsel", "ASSOCIATE LEGAL COUNSEL", "ENTRY", "LEGAL"),
        ("HR Recruiting Specialist", "HR RECRUITING SPECIALIST", "INDIVIDUAL_CONTRIBUTOR", "HR"),
        ("Office Coordinator", "OFFICE COORDINATOR", "INDIVIDUAL_CONTRIBUTOR", "GENERAL"),
    ]
    for raw_t, exp_norm, exp_sen, exp_dept in title_cases:
        jt = standardize_job_title(raw_t)
        assert jt.is_valid is True
        assert jt.normalized_title == exp_norm
        assert jt.seniority_level == exp_sen
        assert jt.department == exp_dept
        assert jt.to_dict()["seniority_level"] == exp_sen


def test_email_url_and_social_standardization() -> None:
    assert StandardizedWebsite is StandardizedUrl
    assert standardize_website is standardize_url

    # Direct helper edge cases
    assert extract_registrable_domain("localhost") == (None, None, None, None)
    assert extract_registrable_domain("co.uk") == (None, None, "co.uk", None)
    assert infer_country_from_domain("") is None
    assert infer_country_from_domain("acme.com.co") == "CO"

    # Email standardization
    assert standardize_email(None).is_valid is False
    assert standardize_email("   ").is_valid is False
    assert standardize_email("not-an-email").is_valid is False
    assert standardize_email(".bad@acme.com").is_valid is False
    assert standardize_email("+tag@acme.com").is_valid is False
    assert standardize_email("user@bad..domain.com").is_valid is False
    assert standardize_email("user@123.456").is_valid is False
    assert standardize_email("user@-bad.com").is_valid is False
    assert standardize_email("user@localhost").is_valid is False
    assert standardize_email("user@" + "a" * 70 + ".com").is_valid is False

    e1 = standardize_email('"Jane Doe" <mailto:Jane.Doe+newsletter@googlemial.com?subject=hi>')
    assert e1.is_valid is True
    assert e1.display_name == "Jane Doe"
    assert e1.email == "janedoe@gmail.com"
    assert e1.local_part == "janedoe"
    assert e1.raw_local_part == "jane.doe+newsletter"
    assert e1.subaddress == "newsletter"
    assert e1.domain == "gmail.com"
    assert e1.email_type == "FREE_WEBMAIL"
    assert e1.is_free_provider is True
    assert "DISPLAY_NAME_EXTRACTED" in e1.healing_actions
    assert "MAILTO_PREFIX_STRIPPED" in e1.healing_actions
    assert "DOMAIN_TYPO_HEALED" in e1.healing_actions
    assert "GMAIL_DOMAIN_CANONICALIZED" in e1.healing_actions
    assert "SUBADDRESS_EXTRACTED" in e1.healing_actions
    assert "GMAIL_DOTS_CANONICALIZED" in e1.healing_actions
    assert e1.to_dict()["email"] == "janedoe@gmail.com"

    e_mailto_plain = standardize_email("mailto:jane@acme.com")
    assert e_mailto_plain.email == "jane@acme.com"

    # IDNA / Punycode email, role account, disposable, corporate ccTLD, TLD typos (.con, .cmo)
    e_idna = standardize_email("<info@münchen.de>")
    assert e_idna.is_valid is True
    assert e_idna.domain == "xn--mnchen-3ya.de"
    assert e_idna.email_type == "ROLE_ACCOUNT"
    assert e_idna.is_role_account is True
    assert e_idna.inferred_country_iso2 == "DE"
    assert "IDNA_PUNYCODE_NORMALIZED" in e_idna.healing_actions

    e_disp = standardize_email("temp@mailinator.com")
    assert e_disp.is_disposable is True
    assert e_disp.email_type == "DISPOSABLE"

    e_corp_con = standardize_email("alice@acme.con")
    assert e_corp_con.domain == "acme.com"
    assert e_corp_con.email_type == "CORPORATE"

    e_corp_cmo = standardize_email("alice@acme.cmo")
    assert e_corp_cmo.domain == "acme.com"

    # URL standardization
    assert standardize_url(None).is_valid is False
    assert standardize_url("   ").is_valid is False
    assert standardize_url("mailto:user@acme.com").is_valid is False
    assert standardize_url("javascript:alert(1)").is_valid is False
    assert standardize_url("ftp://files.acme.com").is_valid is False
    assert standardize_url("http://localhost").is_valid is False
    assert standardize_url("https://co.uk").is_valid is False

    u1 = standardize_url("http://www.shop.acme-holdings.co.uk/products/item/?utm_source=google&fbclid=123&id=42")
    assert u1.is_valid is True
    assert u1.url == "https://shop.acme-holdings.co.uk/products/item?id=42"
    assert u1.domain == "acme-holdings.co.uk"
    assert u1.subdomain == "shop"
    assert u1.public_suffix == "co.uk"
    assert u1.brand_stem == "ACME"
    assert u1.path == "/products/item"
    assert u1.inferred_country_iso2 == "GB"
    assert u1.url_key == "acme-holdings.co.uk/products/item"
    assert "SCHEME_UPGRADED_HTTPS" in u1.healing_actions
    assert "WWW_STRIPPED" in u1.healing_actions
    assert "TRACKING_PARAMS_STRIPPED" in u1.healing_actions
    assert u1.to_dict()["domain"] == "acme-holdings.co.uk"

    # Social standardization across all platforms and formats
    assert standardize_social(None).is_valid is False
    assert standardize_social("   ").is_valid is False
    assert standardize_social("just_a_word").is_valid is False
    assert standardize_social("https://linkedin.com/").is_valid is False
    assert standardize_social("https://unknown.example.com/user").is_valid is False
    assert standardize_social("https://x.com/bad!handle").is_valid is False
    assert standardize_social("in/bad!handle").is_valid is False
    assert standardize_social("@bad!handle").is_valid is False

    social_cases = [
        ("https://www.linkedin.com/in/satyanadella/", None, "LINKEDIN", "PERSON", "satyanadella", "https://linkedin.com/in/satyanadella"),
        ("linkedin.com/company/openai", None, "LINKEDIN", "COMPANY", "openai", "https://linkedin.com/company/openai"),
        ("linkedin.com/satyanadella", None, "LINKEDIN", "PERSON", "satyanadella", "https://linkedin.com/in/satyanadella"),
        ("https://mobile.twitter.com/@elonmusk", None, "X", "USER", "elonmusk", "https://x.com/elonmusk"),
        ("https://github.com/torvalds", None, "GITHUB", "USER", "torvalds", "https://github.com/torvalds"),
        ("https://instagram.com/natgeo", None, "INSTAGRAM", "USER", "natgeo", "https://instagram.com/natgeo"),
        ("https://fb.com/meta", None, "FACEBOOK", "USER", "meta", "https://facebook.com/meta"),
        ("https://youtube.com/@mkbhd", None, "YOUTUBE", "CHANNEL", "mkbhd", "https://youtube.com/@mkbhd"),
        ("https://youtube.com/c/veritasium", None, "YOUTUBE", "CHANNEL", "veritasium", "https://youtube.com/@veritasium"),
        ("https://youtube.com/channel/UC12345", None, "YOUTUBE", "CHANNEL", "UC12345", "https://youtube.com/channel/UC12345"),
        ("https://youtu.be/google", None, "YOUTUBE", "CHANNEL", "google", "https://youtube.com/@google"),
        ("in/jane-doe", None, "LINKEDIN", "PERSON", "jane-doe", "https://linkedin.com/in/jane-doe"),
        ("company/acme-corp", None, "LINKEDIN", "COMPANY", "acme-corp", "https://linkedin.com/company/acme-corp"),
        ("twitter: @jack", None, "X", "USER", "jack", "https://x.com/jack"),
        ("jdoe", "LINKEDIN", "LINKEDIN", "PERSON", "jdoe", "https://linkedin.com/in/jdoe"),
        ("jdoe", "GITHUB", "GITHUB", "USER", "jdoe", "https://github.com/jdoe"),
        ("jdoe", "INSTAGRAM", "INSTAGRAM", "USER", "jdoe", "https://instagram.com/jdoe"),
        ("jdoe", "FACEBOOK", "FACEBOOK", "USER", "jdoe", "https://facebook.com/jdoe"),
        ("jdoe", "YOUTUBE", "YOUTUBE", "CHANNEL", "jdoe", "https://youtube.com/@jdoe"),
        ("@openai", None, "X", "USER", "openai", "https://x.com/openai"),
    ]
    for raw_s, plat_hint, exp_plat, exp_type, exp_handle, exp_url in social_cases:
        soc = standardize_social(raw_s, platform=plat_hint)
        assert soc.is_valid is True
        assert soc.platform == exp_plat
        assert soc.profile_type == exp_type
        assert soc.handle == exp_handle
        assert soc.url == exp_url
        assert soc.to_dict()["url"] == exp_url


def test_joint_multi_pillar_cross_healing() -> None:
    assert StandardizedEntity is StandardizedContact
    assert standardize_entity is standardize_contact
    assert batch_standardize_entities is batch_standardize_contacts

    # 1. Rescue email from street1, street2, organization, and person_name + rescue URL from street1/street2
    c_rescue1 = standardize_contact(
        street1="350 Fifth Ave, Email: jane.doe@acme.co.uk, Web: www.acme.co.uk",
        city="London",
        postal_code="SW1A 2AA",
        phone="020 7946 0912",
    )
    assert c_rescue1.email is not None and c_rescue1.email.email == "jane.doe@acme.co.uk"
    assert c_rescue1.website is not None and c_rescue1.website.domain == "acme.co.uk"
    assert c_rescue1.person is not None and c_rescue1.person.full_name == "JANE DOE"
    assert c_rescue1.organization is not None and c_rescue1.organization.base_name == "ACME"
    assert c_rescue1.company is c_rescue1.organization
    assert c_rescue1.phone.e164 == "+442079460912"
    assert CrossHealingAction.EMAIL_RESCUED_FROM_FIELD.value in c_rescue1.cross_healing_actions
    assert CrossHealingAction.URL_RESCUED_FROM_FIELD.value in c_rescue1.cross_healing_actions
    assert CrossHealingAction.PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF.value in c_rescue1.cross_healing_actions
    assert CrossHealingAction.ORGANIZATION_INFERRED_FROM_DOMAIN.value in c_rescue1.cross_healing_actions
    assert CrossHealingAction.EMAIL_WEBSITE_DOMAIN_MATCH.value in c_rescue1.cross_healing_actions
    assert CrossHealingAction.COUNTRY_INFERRED_FROM_ENTITY_PILLARS.value in c_rescue1.cross_healing_actions

    # 2. Rescue email from street2 and URL from street2
    c_rescue2 = standardize_contact(
        street1="1600 Amphitheatre Pkwy",
        street2="   ",
        organization="Acme Corp (billing@acme.com)",
        city="Mountain View",
        state="CA",
        postal_code="94043",
    )
    assert c_rescue2.email is not None and c_rescue2.email.email == "billing@acme.com"
    assert c_rescue2.organization is not None and c_rescue2.organization.base_name == "ACME"

    c_rescue_s2 = standardize_contact(
        street1="1600 Amphitheatre Pkwy",
        street2="Suite 100, contact@stripe.com, https://stripe.com",
        city="Mountain View",
        state="CA",
        postal_code="94043",
    )
    assert c_rescue_s2.email is not None and c_rescue_s2.email.email == "contact@stripe.com"
    assert c_rescue_s2.website is not None and c_rescue_s2.website.domain == "stripe.com"

    # 3. Rescue angle-bracketed email from person_name + invalid direct pillar inputs
    c_rescue_person = standardize_contact(
        person_name="Robert Smith <bob.smith@bad..domain.com>",
        street1="invalid@... https://co.uk",
        website="bad_url",
        email="bad_email",
        organization="...",
        job_title="---",
        social="bad_social",
    )
    assert c_rescue_person.email is None
    assert c_rescue_person.website is None
    assert c_rescue_person.organization is None
    assert c_rescue_person.job_title is None
    assert c_rescue_person.social is None
    assert standardize_contact(person_name="...").person is None

    c_rescue_angle = standardize_contact(
        person_name="Robert Smith <bob.smith@widgets.com>",
        website="https://other-domain.com",
        job_title="CTO",
        social="@bobsmith",
    )
    assert c_rescue_angle.email is not None and c_rescue_angle.email.email == "bob.smith@widgets.com"
    assert c_rescue_angle.person is not None and c_rescue_angle.person.root_first_name == "ROBERT"
    assert c_rescue_angle.job_title is not None and c_rescue_angle.job_title.seniority_level == "C_SUITE"
    assert c_rescue_angle.social is not None and c_rescue_angle.social.platform == "X"
    assert CrossHealingAction.EMAIL_WEBSITE_DOMAIN_MISMATCH.value in c_rescue_angle.cross_healing_actions

    # 4. Rescue person from Address care_of ("C/O Jane Doe") and Email display_name (and guard corporate/single care_of)
    c_care_of = standardize_contact(
        street1="C/O Dr. Jane Smith",
        street2="100 Main St",
        city="Boston",
        state="MA",
        postal_code="02108",
    )
    assert c_care_of.person is not None and c_care_of.person.last_name == "SMITH"
    assert CrossHealingAction.PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF.value in c_care_of.cross_healing_actions

    assert standardize_contact(street1="C/O Acme Holdings", street2="100 Main St", city="Boston", state="MA", postal_code="02108").person is None
    assert standardize_contact(street1="C/O Madonna", street2="100 Main St", city="Boston", state="MA", postal_code="02108").person is None

    c_disp_person = standardize_contact(
        email="Mary Jane Watson <mjw@dailybugle.com>",
    )
    assert c_disp_person.person is not None and c_disp_person.person.last_name == "WATSON"
    assert c_disp_person.organization is not None and c_disp_person.organization.base_name == "DAILYBUGLE"
    assert CrossHealingAction.PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF.value in c_disp_person.cross_healing_actions
    assert CrossHealingAction.ORGANIZATION_INFERRED_FROM_DOMAIN.value in c_disp_person.cross_healing_actions

    assert standardize_contact(email="(.) <jdoe@acme.com>").person is None
    assert standardize_contact(email="jdoe@acme.com").person is None
    assert standardize_contact(email="jane.doe123@acme.com").person is None

    # 5. Country inferred from legal suffix (GmbH -> DE) heals domestic German phone or address without phone
    c_de = standardize_contact(
        organization="Siemens GmbH",
        phone="089 636 00",
    )
    assert c_de.phone.country_iso2 == "DE"
    assert c_de.phone.e164 == "+498963600"
    assert CrossHealingAction.COUNTRY_INFERRED_FROM_ENTITY_PILLARS.value in c_de.cross_healing_actions

    c_de_addr_only = standardize_contact(
        organization="Siemens GmbH",
        street1="Wittelsbacherplatz 2",
        city="Munich",
        postal_code="80333",
    )
    assert c_de_addr_only.address.country == "DEU"

    c_de_bad_phone = standardize_contact(
        organization="Siemens GmbH",
        phone="12",
    )
    assert c_de_bad_phone.phone.is_valid is False

    # 6. Batch standardization with alias keys
    batch_res = batch_standardize_contacts(
        [
            {
                "company": "The Acme Ltd",
                "name": "Bob Smith",
                "title": "VP Sales",
                "email": "bob@acme.co.uk",
                "url": "acme.co.uk",
                "social": "@acme",
                "phone": "020 7946 0912",
            }
        ]
    )
    assert len(batch_res) == 1
    assert batch_res[0].organization is not None and batch_res[0].organization.legal_suffix == "LTD"
    assert batch_res[0].phone.e164 == "+442079460912"


def test_cli_entity_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["company", "The Acme & Co., Inc."]) == 0
    out_comp = json.loads(capsys.readouterr().out)
    assert out_comp["legal_name"] == "ACME CORP" or out_comp["legal_suffix"] == "INC"

    assert cli_main(["person", "Smith, Jr., Bob"]) == 0
    out_per = json.loads(capsys.readouterr().out)
    assert out_per["person_root_key"] == "SMITH|ROBERT"

    assert cli_main(["title", "SVP of Engineering"]) == 0
    out_title = json.loads(capsys.readouterr().out)
    assert out_title["seniority_level"] == "VP"

    assert cli_main(["email", "Jane.Doe+tag@gmail.com"]) == 0
    out_email = json.loads(capsys.readouterr().out)
    assert out_email["email"] == "janedoe@gmail.com"

    assert cli_main(["url", "www.acme.co.uk/?utm_source=x"]) == 0
    out_url = json.loads(capsys.readouterr().out)
    assert out_url["domain"] == "acme.co.uk"

    assert cli_main(["social", "@octocat", "--platform", "GITHUB"]) == 0
    out_soc = json.loads(capsys.readouterr().out)
    assert out_soc["url"] == "https://github.com/octocat"
