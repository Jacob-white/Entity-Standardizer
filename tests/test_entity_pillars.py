"""Comprehensive tests for Organization, Person, Job Title, Email, URL, Social, and Joint Multi-Pillar Standardization."""

from __future__ import annotations

import json

import pytest

from entity_standardizer import (
    CompanyCluster,
    CompanyComparisonResult,
    CrossHealingAction,
    EmailComparisonResult,
    PersonCluster,
    PersonComparisonResult,
    StandardizedCompany,
    StandardizedContact,
    StandardizedEntity,
    StandardizedOrganization,
    StandardizedUrl,
    StandardizedWebsite,
    UrlComparisonResult,
    batch_standardize_companies,
    batch_standardize_contacts,
    batch_standardize_emails,
    batch_standardize_entities,
    batch_standardize_job_titles,
    batch_standardize_organizations,
    batch_standardize_persons,
    batch_standardize_socials,
    batch_standardize_urls,
    batch_standardize_websites,
    compare_companies,
    compare_emails,
    compare_organizations,
    compare_persons,
    compare_urls,
    compare_websites,
    deduplicate_companies,
    deduplicate_organizations,
    deduplicate_persons,
    is_organization_name,
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
from entity_standardizer.company import _normalize_tokens, _pure_normalize_tokens
from entity_standardizer.web import extract_registrable_domain, infer_country_from_domain
import entity_standardizer._native_dispatch as native_dispatch
from entity_standardizer.cli import main as cli_main


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

    # Undotted trailing letter in dotted initialism / suffix, Co., Ltd., and branch before inline DBA/FKA
    c_llc_no_dot = standardize_company("Acme L.L.C")
    assert c_llc_no_dot.legal_name == "ACME LLC"
    assert c_llc_no_dot.legal_suffix == "LLC"

    c_ibm_no_dot = standardize_company("I.B.M")
    assert c_ibm_no_dot.legal_name == "IBM"

    c_co_ltd = standardize_company("Samsung Electronics Co., Ltd.")
    assert c_co_ltd.base_name == "SAMSUNG ELECTRONICS"
    assert c_co_ltd.legal_suffix == "LTD"

    c_branch_before_dba = standardize_company(
        "Acme Holdings, Inc. - West Coast Division DBA Acme Industrial"
    )
    assert c_branch_before_dba.legal_name == "ACME HOLDINGS INC"
    assert c_branch_before_dba.dba_name == "ACME INDUSTRIAL"
    assert c_branch_before_dba.branch_unit == "WEST COAST DIVISION"

    c_branch_on_fka = standardize_company(
        "Block, Inc. f/k/a Square Inc. - Payments Division"
    )
    assert c_branch_on_fka.legal_name == "BLOCK INC"
    assert c_branch_on_fka.fka_name == "SQUARE INC"
    assert c_branch_on_fka.branch_unit == "PAYMENTS DIVISION"


def test_person_and_job_title_standardization() -> None:
    assert standardize_person(None).is_valid is False
    assert standardize_person("   ").is_valid is False
    assert standardize_person(", , ,").is_valid is False
    assert standardize_person("()").is_valid is False
    assert standardize_person("..., Jr.").is_valid is False
    assert standardize_person("123 Main St").is_valid is False

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

    # Salutation and suffix on first segment of Last, First and trailing suffix on given segment
    p3 = standardize_person("Dr. Jones Jr., William III")
    assert p3.salutation == "DR"
    assert p3.last_name == "JONES"
    assert p3.first_name == "WILLIAM"
    assert p3.generational_suffix == "III"

    # Spaced dotted credentials ("Ph. D.") and multiple middle initials ("H. W.") + Ben middle name
    p_spaced_cred = standardize_person("George H. W. Bush, Ph. D.")
    assert p_spaced_cred.first_name == "GEORGE"
    assert p_spaced_cred.middle_name == "H W"
    assert p_spaced_cred.last_name == "BUSH"
    assert p_spaced_cred.credentials == ["PHD"]

    p_ben = standardize_person("Robert Ben 99 Smith")
    assert p_ben.first_name == "ROBERT"
    assert p_ben.middle_name == "BEN"
    assert p_ben.last_name == "SMITH"

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
        ("C.E.O. & Co-Founder", "CHIEF EXECUTIVE OFFICER AND CO-FOUNDER", "C_SUITE", "EXECUTIVE"),
        ("Managing Partner", "MANAGING PARTNER", "OWNER_PARTNER", "EXECUTIVE"),
        ("Sr. VP of Eng", "SENIOR VICE PRESIDENT OF ENGINEER", "VP", "ENGINEERING"),
        ("V.P. of Business Development", "VICE PRESIDENT OF BUSINESS DEVELOPMENT", "VP", "SALES"),
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

    c_de_s2_phone = standardize_contact(
        organization="Siemens GmbH",
        street2="089 636 00",
    )
    assert c_de_s2_phone.phone.e164 == "+498963600"
    assert CrossHealingAction.PHONE_RESCUED_FROM_ADDRESS_FIELD.value in c_de_s2_phone.cross_healing_actions
    assert CrossHealingAction.COUNTRY_INFERRED_FROM_ENTITY_PILLARS.value in c_de_s2_phone.cross_healing_actions

    c_s1_angle_email = standardize_contact(
        street1="123 Main St <jane.doe@acme.com>",
        city="Boston",
        state="MA",
        postal_code="02108",
    )
    assert c_s1_angle_email.email is not None and c_s1_angle_email.email.display_name is None
    assert c_s1_angle_email.person is not None and c_s1_angle_email.person.full_name == "JANE DOE"

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


def test_rust_company_tokens_pure_fallback_and_batch_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert batch_standardize_organizations is batch_standardize_companies

    # Direct pure-Python token normalization parity check
    pure_actions: list[str] = []
    assert _pure_normalize_tokens("The I. B. M. & Co. L.L.C", pure_actions) == [
        "THE",
        "IBM",
        "AND",
        "CO",
        "LLC",
    ]
    assert "AMPERSAND_NORMALIZED" in pure_actions
    assert "INITIALISM_COLLAPSED" in pure_actions
    assert _pure_normalize_tokens("I B M + Group", None) == ["IBM", "AND", "GROUP"]
    assert _pure_normalize_tokens("I.B.M. Corp", None) == ["IBM", "CORP"]

    # Native Rust PyO3 token normalization (or mock when running pure-Python CI job)
    if native_dispatch._native_mod is not None:  # pragma: no cover
        toks_rs, amp_rs, init_rs = native_dispatch._native_mod.normalize_company_tokens_rs(
            "The I. B. M. & Co. L.L.C"
        )
        assert toks_rs == ["THE", "IBM", "AND", "CO", "LLC"]
        assert amp_rs is True
        assert init_rs is True
        batch_rs = native_dispatch._native_mod.normalize_batch_company_tokens_rs(
            ["Novo Nordisk A/S", "Booking.com B.V."]
        )
        assert batch_rs[0][0] == ["NOVO", "NORDISK", "AS"]
        assert batch_rs[1][0] == ["BOOKING", "COM", "BV"]

    class _DummyNative:
        @staticmethod
        def normalize_company_tokens_rs(text: str) -> tuple[list[str], bool, bool]:
            if "&" in text:
                return (["ABC", "AND", "CO"], True, True)
            return (["ACME", "CORP"], False, False)

    monkeypatch.setattr(native_dispatch, "_native_mod", _DummyNative())
    nat_actions: list[str] = []
    assert _normalize_tokens("A.B.C. & Co.", nat_actions) == ["ABC", "AND", "CO"]
    assert "AMPERSAND_NORMALIZED" in nat_actions
    assert "INITIALISM_COLLAPSED" in nat_actions
    nat_actions_plain: list[str] = []
    assert _normalize_tokens("Acme Corp", nat_actions_plain) == ["ACME", "CORP"]
    assert nat_actions_plain == []
    assert _normalize_tokens("Acme Corp", None) == ["ACME", "CORP"]

    # Fallback path when _native_mod is None
    monkeypatch.setattr(native_dispatch, "_native_mod", None)
    fb_actions: list[str] = []
    assert _normalize_tokens("A B C & Partners", fb_actions) == [
        "ABC",
        "AND",
        "PARTNERS",
    ]
    assert "AMPERSAND_NORMALIZED" in fb_actions
    assert "INITIALISM_COLLAPSED" in fb_actions

    # Expanded legal forms, credentials, nicknames, and batch functions
    comp_batch = batch_standardize_companies(
        [
            "JPMorgan Chase Bank, National Association",
            "Acme Limited Liability Limited Partnership",
            "Maple Unlimited Liability Company",
            "Pacific Federal Savings Bank",
            "Vanguard Statutory Trust",
            "Fidelity Business Trust",
        ]
    )
    assert [c.legal_suffix for c in comp_batch] == [
        "NA",
        "LLLP",
        "ULC",
        "FSB",
        "TRUST",
        "TRUST",
    ]
    assert comp_batch[0].inferred_country_iso2 == "US"
    assert comp_batch[2].inferred_country_iso2 == "CA"

    person_batch = batch_standardize_persons(
        [
            "Zack Smith, ChFC, CLU, AIF, CFP",
            "Josh Miller, CIMA, CPWA, CAIA, FRM",
            "Hank Williams, EA, PFS, RICP, CRPC",
            "Jack Welch",
        ]
    )
    assert person_batch[0].root_first_name == "ZACHARY"
    assert "CHFC" in person_batch[0].credentials and "AIF" in person_batch[0].credentials
    assert person_batch[1].root_first_name == "JOSHUA"
    assert "CIMA" in person_batch[1].credentials and "FRM" in person_batch[1].credentials
    assert person_batch[2].root_first_name == "HENRY"
    assert "EA" in person_batch[2].credentials and "RICP" in person_batch[2].credentials
    assert person_batch[3].root_first_name == "JOHN"

    title_batch = batch_standardize_job_titles(["CCO", "CAO", "CSO"])
    assert [t.normalized_title for t in title_batch] == [
        "CHIEF COMPLIANCE OFFICER",
        "CHIEF ACCOUNTING OFFICER",
        "CHIEF STRATEGY OFFICER",
    ]
    assert all(t.seniority_level == "C_SUITE" for t in title_batch)


def test_v2_1_company_diacritics_offshore_suffixes_sec_trusts_and_comparison() -> None:
    # Diacritics folding in both pure-Python and native paths
    assert _pure_normalize_tokens("KKR Opportunities III S.à r.l.", []) == [
        "KKR",
        "OPPORTUNITIES",
        "III",
        "SA",
        "RL",
    ]
    c_sarl = standardize_company("KKR Opportunities III S.à r.l.")
    assert c_sarl.legal_name == "KKR OPPORTUNITIES III SARL"
    assert c_sarl.legal_suffix == "SARL"
    assert c_sarl.inferred_country_iso2 == "LU"

    c_fr_sarl = standardize_company("Société Générale Société à responsabilité limitée")
    assert c_fr_sarl.legal_name == "SOCIETE GENERALE SARL"
    assert c_fr_sarl.inferred_country_iso2 == "FR"

    c_scsp = standardize_company("EQT X Special Limited Partnership")
    assert c_scsp.legal_suffix == "SCSP"
    assert c_scsp.inferred_country_iso2 == "LU"

    c_scsp_abbr = standardize_company("Bain Capital S.C.Sp.")
    assert c_scsp_abbr.legal_suffix == "SCSP"
    assert c_scsp_abbr.inferred_country_iso2 == "LU"

    c_spc = standardize_company("Millennium Global Segregated Portfolio Company")
    assert c_spc.legal_suffix == "SPC"
    assert c_spc.inferred_country_iso2 == "KY"

    c_dst = standardize_company("Inland Exchange Delaware Statutory Trust")
    assert c_dst.legal_suffix == "DST"
    assert c_dst.inferred_country_iso2 == "US"

    c_reit = standardize_company("Prologis Real Estate Investment Trust")
    assert c_reit.legal_suffix == "REIT"

    # SEC /DE/ state suffix stripping (valid US state and non-US state code)
    c_sec_de = standardize_company("BLACKROCK INC /DE/")
    assert c_sec_de.legal_name == "BLACKROCK INC"
    assert c_sec_de.inferred_country_iso2 == "US"
    assert "SEC_STATE_SUFFIX_STRIPPED" in c_sec_de.healing_actions

    c_sec_xx = standardize_company("GLOBAL OFFSHORE CORP /FI/")
    assert c_sec_xx.legal_name == "GLOBAL OFFSHORE CORP"
    assert c_sec_xx.inferred_country_iso2 is None
    assert "SEC_STATE_SUFFIX_STRIPPED" in c_sec_xx.healing_actions

    # Trust agreement date guard (U/A/D, F/B/O, REVOCABLE TRUST) must not split as DBA
    c_trust = standardize_company("U/A/D 01/15/2010 JOHN DOE REVOCABLE TRUST")
    assert c_trust.dba_name is None
    assert c_trust.legal_suffix == "TRUST"

    # Parenthesized acronym alias extraction vs legal suffix inside parentheses
    c_pimco = standardize_company("Pacific Investment Management Company (PIMCO)")
    assert c_pimco.base_name == "PACIFIC INVESTMENT MANAGEMENT"
    assert c_pimco.dba_name == "PIMCO"
    assert "DBA_EXTRACTED" in c_pimco.healing_actions

    c_paren_sfx = standardize_company("Acme Holdings (LLC)")
    assert c_paren_sfx.dba_name is None

    # Institutional role qualifiers in parentheses extracted as branch_unit
    c_prog = standardize_company("Fidelity Investments (Program Manager)")
    assert c_prog.branch_unit == "PROGRAM MANAGER"
    assert c_prog.base_name == "FIDELITY INVESTMENTS"

    # Company comparison across all match tiers
    assert compare_organizations is compare_companies
    cmp_inv = compare_companies(None, "BlackRock, Inc.")
    assert cmp_inv.is_match is False and cmp_inv.match_type == "INVALID_INPUT"

    cmp_exact = compare_companies("BlackRock, Inc.", "BLACKROCK INCORPORATED /DE/")
    assert isinstance(cmp_exact, CompanyComparisonResult)
    assert cmp_exact.is_match is True and cmp_exact.match_type == "EXACT_COMPANY_KEY"
    assert cmp_exact.to_dict()["score"] == 1.0

    cmp_base = compare_companies("Blackstone Group LLC", "Blackstone Group L.P.")
    assert cmp_base.is_match is True and cmp_base.match_type == "BASE_NAME_MATCH"

    cmp_alias = compare_companies("Pacific Investment Management Company (PIMCO)", "PIMCO LLC")
    assert cmp_alias.is_match is True and cmp_alias.match_type == "ALIAS_MATCH"

    cmp_stem = compare_companies("Apollo Global Management LLC", "Apollo Advisors LP")
    assert cmp_stem.is_match is True and cmp_stem.match_type == "BRAND_STEM_MATCH"

    cmp_phon = compare_companies("Schroder Capital LLC", "Schroeder Capital LP")
    assert cmp_phon.is_match is True and cmp_phon.match_type == "PHONETIC_FUZZY_MATCH"

    cmp_no = compare_companies("BlackRock Inc.", "Vanguard Group Inc.")
    assert cmp_no.is_match is False and cmp_no.match_type == "NO_MATCH"


def test_v2_1_person_org_guard_placeholders_executive_titles_and_comparison() -> None:
    # Organization detector in person field
    assert is_organization_name(None) is False
    assert is_organization_name("   ") is False
    assert is_organization_name("NexPoint Energy, L.P.") is True
    assert is_organization_name("Augnition Global Investors US GP, LLC") is True
    assert is_organization_name("Jane M. Doe") is False

    p_org = standardize_person("Augnition Global Investors US GP, LLC")
    assert p_org.is_valid is False
    assert p_org.is_organization is True
    assert "ORGANIZATION_DETECTED_IN_PERSON_FIELD" in p_org.healing_actions
    assert p_org.to_dict()["is_organization"] is True

    # Placeholders rejected vs leading placeholder stripped
    assert standardize_person("N/A").is_valid is False
    assert standardize_person("[none]").is_valid is False
    assert standardize_person("---").is_valid is False

    p_lead = standardize_person("- Enis Hulli")
    assert p_lead.is_valid is True
    assert p_lead.full_name == "ENIS HULLI"
    assert "PLACEHOLDER_STRIPPED" in p_lead.healing_actions

    p_na_lead = standardize_person("N/A Enis Hulli")
    assert p_na_lead.is_valid is True
    assert p_na_lead.full_name == "ENIS HULLI"

    # JSON-serialized role array unpacking and executive flag
    jt_json = standardize_job_title('["Executive Officer", "Director"]')
    assert jt_json.is_valid is True
    assert jt_json.normalized_title == "EXECUTIVE OFFICER AND DIRECTOR"
    assert jt_json.is_executive is True
    assert "JSON_ARRAY_UNPACKED" in jt_json.healing_actions
    assert jt_json.to_dict()["is_executive"] is True

    assert standardize_job_title("[]").is_valid is False
    jt_bad_json = standardize_job_title("[Chief Compliance Officer]")
    assert jt_bad_json.is_valid is True
    assert jt_bad_json.normalized_title == "CHIEF COMPLIANCE OFFICER"

    jt_finop = standardize_job_title("FINOP")
    assert jt_finop.normalized_title == "FINANCIAL AND OPERATIONS PRINCIPAL"
    assert jt_finop.is_executive is True

    jt_iar = standardize_job_title("IAR")
    assert jt_iar.normalized_title == "INVESTMENT ADVISER REPRESENTATIVE"
    assert jt_iar.is_executive is False

    # Person comparison across all match tiers
    p_inv = compare_persons(None, "Jane Doe")
    assert isinstance(p_inv, PersonComparisonResult)
    assert p_inv.is_match is False and p_inv.match_type == "INVALID_INPUT"

    p_gen_conflict = compare_persons("Robert J. Smith Jr.", "Robert J. Smith Sr.")
    assert p_gen_conflict.is_match is False
    assert p_gen_conflict.match_type == "GENERATIONAL_SUFFIX_CONFLICT"

    p_exact = compare_persons("Dr. Robert J. Smith", "Smith, Robert J., M.D.")
    assert p_exact.is_match is True and p_exact.match_type == "EXACT_PERSON_KEY"
    assert p_exact.to_dict()["score"] == 1.0

    p_root = compare_persons("Bob J. Smith", "Robert M. Smith")
    assert p_root.is_match is True and p_root.match_type == "ROOT_NAME_MATCH"

    p_init = compare_persons("R. Smith", "Robert Smith")
    assert p_init.is_match is True and p_init.match_type == "INITIAL_AND_LAST_MATCH"

    p_phon = compare_persons("Steven Jonsson", "Stephen Johnson")
    assert p_phon.is_match is True and p_phon.match_type == "PHONETIC_FUZZY_MATCH"

    p_no = compare_persons("Alice Wonderland", "Bob Builder")
    assert p_no.is_match is False and p_no.match_type == "NO_MATCH"


def test_v2_1_web_batch_helpers_and_joint_org_rescue() -> None:
    assert batch_standardize_websites is batch_standardize_urls
    emails = batch_standardize_emails(["Jane.Doe+tag@gmial.com", "invalid"])
    assert len(emails) == 2 and emails[0].email == "janedoe@gmail.com" and not emails[1].is_valid

    urls = batch_standardize_urls(["http://www.blackrock.com/?utm_source=x", ""])
    assert len(urls) == 2 and urls[0].domain == "blackrock.com" and not urls[1].is_valid

    socials = batch_standardize_socials(["@blackrock", ""], platform="X")
    assert len(socials) == 2 and socials[0].url == "https://x.com/blackrock" and not socials[1].is_valid

    # Joint contact cross-healing: rescue organization misplaced in person_name field
    rec = standardize_contact(
        person_name="Augnition Global Investors US GP, LLC",
        street1="100 Main St",
        city="New York",
        state="NY",
        postal_code="10001",
    )
    assert rec.person is None
    assert rec.organization is not None
    assert rec.organization.legal_name == "AUGNITION GLOBAL INVESTORS US GP LLC"
    assert (
        CrossHealingAction.ORGANIZATION_RESCUED_FROM_PERSON_FIELD.value
        in rec.cross_healing_actions
    )


def test_v2_1_entity_deduplication_web_comparison_and_endpoints(capsys) -> None:
    from fastapi.testclient import TestClient

    from entity_standardizer.mcp import handle_mcp_request
    from entity_standardizer.server import app

    # 1. Company deduplication & clustering
    assert deduplicate_organizations is deduplicate_companies
    assert deduplicate_companies([]) == []
    c_clusters = deduplicate_companies(
        [
            "BlackRock, Inc.",
            "BLACKROCK INCORPORATED /DE/",
            "BlackRock LLC",
            "Citi Corp",
            "Cato Corp",
            "",
        ]
    )
    assert len(c_clusters) == 4
    assert isinstance(c_clusters[0], CompanyCluster)
    assert len(c_clusters[0].members) == 3
    assert c_clusters[0].golden_company.legal_name == "BLACKROCK INC"
    assert c_clusters[0].to_dict()["cluster_id"] == "COMPANY-CLUSTER-0001"
    assert c_clusters[1].match_types == ("SINGLETON",)

    # 2. Person deduplication & clustering
    assert deduplicate_persons([]) == []
    p_clusters = deduplicate_persons(
        [
            "Dr. Robert J. Smith, M.D.",
            "Bob J. Smith",
            "Robert Smith",
            "Richard Smith",
            "",
        ]
    )
    assert len(p_clusters) == 3
    assert isinstance(p_clusters[0], PersonCluster)
    assert len(p_clusters[0].members) == 3
    assert p_clusters[0].golden_person.full_name == "ROBERT J SMITH"
    assert p_clusters[0].to_dict()["cluster_id"] == "PERSON-CLUSTER-0001"


    # 3. Sentinel domain rejection & email/URL comparison
    e_sent = standardize_email("user@example.com")
    assert e_sent.is_valid is False
    assert "SENTINEL_DOMAIN_REJECTED" in e_sent.healing_actions

    u_sent = standardize_url("https://www.none.com/home")
    assert u_sent.is_valid is False
    assert "SENTINEL_DOMAIN_REJECTED" in u_sent.healing_actions

    ec_inv = compare_emails(None, "jane@stripe.com")
    assert isinstance(ec_inv, EmailComparisonResult)
    assert ec_inv.is_match is False and ec_inv.match_type == "INVALID_INPUT"

    ec_exact = compare_emails("Jane.Doe+vip@gmail.com", "janedoe@googlemail.com")
    assert ec_exact.is_match is True and ec_exact.match_type == "EXACT_EMAIL_KEY"
    assert ec_exact.to_dict()["score"] == 1.0

    ec_corp = compare_emails("jdoe@blackrock.com", "jdoe@blackrock.co.uk")
    assert ec_corp.is_match is True and ec_corp.match_type == "CORPORATE_BRAND_LOCAL_MATCH"

    ec_no = compare_emails("alice@stripe.com", "bob@stripe.com")
    assert ec_no.is_match is False and ec_no.match_type == "NO_MATCH"
    assert compare_emails("jdoe@stripe.com", "jdoe@vanguard.com").is_match is False

    assert compare_websites is compare_urls
    uc_inv = compare_urls(None, "https://stripe.com")
    assert isinstance(uc_inv, UrlComparisonResult)
    assert uc_inv.is_match is False and uc_inv.match_type == "INVALID_INPUT"

    uc_exact = compare_urls("http://www.stripe.com/docs/?utm_source=x", "https://stripe.com/docs")
    assert uc_exact.is_match is True and uc_exact.match_type == "EXACT_URL_KEY"
    assert uc_exact.to_dict()["score"] == 1.0

    uc_dom = compare_urls("https://stripe.com/docs", "https://dashboard.stripe.com/login")
    assert uc_dom.is_match is True and uc_dom.match_type == "SAME_REGISTRABLE_DOMAIN"

    uc_stem = compare_urls("https://blackrock.com", "https://blackrock.co.uk")
    assert uc_stem.is_match is True and uc_stem.match_type == "SAME_BRAND_STEM"

    uc_no = compare_urls("https://stripe.com", "https://vanguard.com")
    assert uc_no.is_match is False and uc_no.match_type == "NO_MATCH"

    # 4. FastAPI, MCP, and CLI endpoints for company/person comparison and job title standardization
    client = TestClient(app)
    r_cc = client.post(
        "/v1/company/compare",
        json={"company_a": "BlackRock, Inc.", "company_b": "BLACKROCK INCORPORATED"},
    )
    assert r_cc.status_code == 200 and r_cc.json()["is_match"] is True

    r_pc = client.post(
        "/v1/person/compare",
        json={"person_a": "Bob Smith", "person_b": "Robert Smith"},
    )
    assert r_pc.status_code == 200 and r_pc.json()["is_match"] is True

    r_jt = client.post("/v1/job-title", json={"title": '["Executive Officer", "Director"]'})
    assert r_jt.status_code == 200 and r_jt.json()["is_executive"] is True

    mcp_jt = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 91,
            "method": "tools/call",
            "params": {"name": "standardize_job_title", "arguments": {"title": "FINOP"}},
        }
    )
    assert '"is_executive": true' in mcp_jt["result"]["content"][0]["text"]

    mcp_cc = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 92,
            "method": "tools/call",
            "params": {
                "name": "compare_companies",
                "arguments": {"company_a": "Acme LLC", "company_b": "Acme L.L.C."},
            },
        }
    )
    assert '"is_match": true' in mcp_cc["result"]["content"][0]["text"]

    mcp_pc = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 93,
            "method": "tools/call",
            "params": {
                "name": "compare_persons",
                "arguments": {"person_a": "Bob Smith", "person_b": "Robert Smith"},
            },
        }
    )
    assert '"is_match": true' in mcp_pc["result"]["content"][0]["text"]

    assert cli_main(["compare-companies", "Acme LLC", "Acme L.L.C."]) == 0
    assert json.loads(capsys.readouterr().out)["is_match"] is True

    assert cli_main(["compare-persons", "Bob Smith", "Robert Smith"]) == 0
    assert json.loads(capsys.readouterr().out)["is_match"] is True


def test_v2_1_person_diacritics_compound_splitting_international_suffixes_and_contact_comparison() -> None:
    from fastapi.testclient import TestClient

    from entity_standardizer import (
        ContactComparisonResult,
        compare_contacts,
        compare_entities,
        split_compound_persons,
    )
    from entity_standardizer.mcp import handle_mcp_request
    from entity_standardizer.server import app

    # 1. Person Latin diacritics & ligatures folding
    p_es = standardize_person("José María Núñez")
    assert p_es.full_name == "JOSE MARIA NUNEZ"
    assert p_es.first_name == "JOSE"
    assert p_es.middle_name == "MARIA"
    assert p_es.last_name == "NUNEZ"
    assert "DIACRITICS_FOLDED" in p_es.healing_actions

    p_nordic = standardize_person("Søren Kierkegaard")
    assert p_nordic.full_name == "SOREN KIERKEGAARD"
    assert "DIACRITICS_FOLDED" in p_nordic.healing_actions

    p_de = standardize_person("Jürgen Weiß")
    assert p_de.full_name == "JURGEN WEISS"

    p_pl = standardize_person("Łukasz Kowalski")
    assert p_pl.full_name == "LUKASZ KOWALSKI"

    # 2. Compound / couple person splitting
    assert split_compound_persons(None) == []
    assert split_compound_persons("   ") == []

    org_split = split_compound_persons("Johnson & Johnson LLC")
    assert len(org_split) == 1 and org_split[0].is_organization is True

    couple_prefix = split_compound_persons("Mr. and Mrs. Robert J. Smith")
    assert len(couple_prefix) == 2
    assert couple_prefix[0].salutation == "MR" and couple_prefix[0].full_name == "ROBERT J SMITH"
    assert couple_prefix[1].salutation == "MRS" and couple_prefix[1].full_name == "ROBERT J SMITH"
    assert "COMPOUND_PERSON_SPLIT" in couple_prefix[0].healing_actions

    comma_couple = split_compound_persons("Smith, John & Jane")
    assert [p.full_name for p in comma_couple] == ["JOHN SMITH", "JANE SMITH"]

    comma_single = split_compound_persons("Smith, John")
    assert len(comma_single) == 1 and comma_single[0].full_name == "JOHN SMITH"

    shared_last = split_compound_persons("John & Jane Smith")
    assert [p.full_name for p in shared_last] == ["JOHN SMITH", "JANE SMITH"]

    distinct_last = split_compound_persons("John Smith & Jane Doe")
    assert [p.full_name for p in distinct_last] == ["JOHN SMITH", "JANE DOE"]

    single_plain = split_compound_persons("Alice Wonderland")
    assert len(single_plain) == 1 and single_plain[0].full_name == "ALICE WONDERLAND"

    # 3. International ISO 20275 legal suffixes & Series/Segregated Portfolio extraction
    c_pl = standardize_company("Allegro.pl Sp. z o.o.")
    assert c_pl.legal_suffix == "SP Z OO" and c_pl.inferred_country_iso2 == "PL"

    c_kgaa = standardize_company("Henkel AG & Co. KGaA")
    assert c_kgaa.legal_suffix == "KGAA" and c_kgaa.inferred_country_iso2 == "DE"

    c_sg = standardize_company("Grab Holdings Pte. Ltd.")
    assert c_sg.legal_suffix == "PTE LTD" and c_sg.inferred_country_iso2 == "SG"

    c_in = standardize_company("Flipkart Internet Pvt. Ltd.")
    assert c_in.legal_suffix == "PVT LTD" and c_in.inferred_country_iso2 == "IN"

    c_my = standardize_company("Petronas Dagangan Sdn. Bhd.")
    assert c_my.legal_suffix == "SDN BHD" and c_my.inferred_country_iso2 == "MY"

    c_bhd = standardize_company("Maybank Berhad")
    assert c_bhd.legal_suffix == "BHD" and c_bhd.inferred_country_iso2 == "MY"

    c_se = standardize_company("Allianz Societas Europaea")
    assert c_se.legal_suffix == "SE"

    c_hu = standardize_company("OTP Bank Kft.")
    assert c_hu.legal_suffix == "KFT" and c_hu.inferred_country_iso2 == "HU"

    c_cz = standardize_company("Avast Software s.r.o.")
    assert c_cz.legal_suffix == "SRO" and c_cz.inferred_country_iso2 == "CZ"

    c_ee = standardize_company("Bolt Technology OÜ")
    assert c_ee.legal_suffix == "OU" and c_ee.inferred_country_iso2 == "EE"

    c_series = standardize_company("Acme Real Estate LLC - Series A")
    assert c_series.legal_suffix == "LLC"
    assert c_series.branch_unit == "SERIES A"
    assert c_series.base_name == "ACME REAL ESTATE"

    c_spc_port = standardize_company("Apex Master Fund SPC (Segregated Portfolio 1)")
    assert c_spc_port.legal_suffix == "SPC"
    assert c_spc_port.branch_unit == "SEGREGATED PORTFOLIO 1"

    # 4. Multi-pillar contact comparison
    assert compare_entities is compare_contacts
    cmp_empty = compare_contacts({}, {})
    assert isinstance(cmp_empty, ContactComparisonResult)
    assert cmp_empty.is_match is False and cmp_empty.match_type == "INSUFFICIENT_PILLARS"

    cmp_gen = compare_contacts(
        {"person_name": "Robert J. Smith Jr.", "organization": "Acme LLC"},
        {"person_name": "Robert J. Smith Sr.", "organization": "Acme LLC"},
    )
    assert cmp_gen.is_match is False and cmp_gen.match_type == "PERSON_GENERATIONAL_CONFLICT"

    c1 = standardize_contact(
        organization="BlackRock, Inc.",
        person_name="Bob Smith",
        phone="(212) 555-0199",
        email="bob.smith@blackrock.com",
        website="https://www.blackrock.com",
        street1="50 Hudson Yards",
        city="New York",
        state="NY",
        postal_code="10001",
    )
    c2 = standardize_contact(
        organization="BLACKROCK INCORPORATED /DE/",
        person_name="Robert Smith",
        phone="+1-212-555-0199",
        email="bob.smith+vip@blackrock.com",
        website="http://blackrock.com/?utm_source=x",
        street1="50 Hudson Yards",
        city="New York",
        state="NY",
        postal_code="10001",
    )
    cmp_multi = compare_contacts(c1, c2)
    assert cmp_multi.is_match is True
    assert cmp_multi.match_type == "MULTI_PILLAR_MATCH"
    assert set(cmp_multi.matched_pillars) == {
        "organization",
        "person",
        "phone",
        "email",
        "website",
        "address",
    }
    assert cmp_multi.to_dict()["score"] == 1.0

    # Building key match (different suites at same building) + single pillar match + non-match
    cmp_bldg = compare_contacts(
        {
            "street1": "50 Hudson Yards Suite 100",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
        },
        {
            "street1": "50 Hudson Yards Suite 200",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
        },
    )
    assert cmp_bldg.is_match is True
    assert cmp_bldg.match_type == "SINGLE_PILLAR_ADDRESS_MATCH"
    assert cmp_bldg.pillar_scores["address"] == 0.92

    cmp_no = compare_contacts(
        {
            "organization": "BlackRock Inc.",
            "person_name": "Alice Wonderland",
            "phone": "(212) 555-0199",
            "email": "alice@blackrock.com",
            "website": "https://blackrock.com",
            "street1": "50 Hudson Yards",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
        },
        {
            "organization": "Vanguard Group Inc.",
            "person_name": "Bob Builder",
            "phone": "(415) 555-2671",
            "email": "bob@vanguard.com",
            "website": "https://vanguard.com",
            "street1": "100 Market St",
            "city": "San Francisco",
            "state": "CA",
            "postal_code": "94105",
        },
    )
    assert cmp_no.is_match is False and cmp_no.match_type == "NO_MATCH"

    client = TestClient(app)
    r_cc = client.post(
        "/v1/contact/compare",
        json={
            "contact_a": {"organization": "Acme LLC", "phone": "(415) 555-2671"},
            "contact_b": {"organization": "Acme L.L.C.", "phone": "+14155552671"},
        },
    )
    assert r_cc.status_code == 200 and r_cc.json()["is_match"] is True

    mcp_cc = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "compare_contacts",
                "arguments": {
                    "contact_a": {"organization": "Acme LLC"},
                    "contact_b": {"organization": "Acme L.L.C."},
                },
            },
        }
    )
    assert '"is_match": true' in mcp_cc["result"]["content"][0]["text"]

    # Model serialization parity (.to_dict() on StandardizedAddress and AddressValidationResult)
    from entity_standardizer import standardize_address, validate_address
    from entity_standardizer.address import _pure_python_core
    from entity_standardizer.address.fuzzy import (
        _pure_damerau_levenshtein_distance,
        damerau_levenshtein_distance,
    )
    from entity_standardizer.address.phonetics import (
        _pure_generate_phonetic_address_key,
        generate_phonetic_address_key,
    )

    assert _pure_python_core.__version__ == "2.1.0"
    assert _pure_damerau_levenshtein_distance("ABC", "CA") == 2
    assert damerau_levenshtein_distance("ABC", "CA") == 2
    addr_obj = standardize_address(street1="350 Fifth Ave", city="New York", state="NY", postal_code="10118")
    assert addr_obj.to_dict() == addr_obj.as_dict()
    assert _pure_generate_phonetic_address_key(
        addr_obj.street1, addr_obj.postal_code, addr_obj.city
    ) == generate_phonetic_address_key(addr_obj.street1, addr_obj.postal_code, addr_obj.city)
    val_obj = validate_address("350 Fifth Ave, New York, NY 10118")
    assert val_obj.to_dict() == val_obj.as_dict()
