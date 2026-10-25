"""Command Line Interface (CLI) for Entity & Phone Standardizer."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from entity_standardizer.address.autocomplete import autocomplete_address
from entity_standardizer.address.standardizer import standardize_address
from entity_standardizer.company import (
    compare_companies,
    deduplicate_companies,
    standardize_company,
)
from entity_standardizer.person import (
    compare_persons,
    deduplicate_persons,
    standardize_job_title,
    standardize_person,
)
from entity_standardizer.web import (
    compare_emails,
    compare_urls,
    standardize_email,
    standardize_social,
    standardize_url,
)
from entity_standardizer.batch import stream_standardize_csv
from entity_standardizer.dedup import (
    cluster_contact_records,
    compare_addresses,
    compare_phones,
    deduplicate_addresses,
    deduplicate_phones,
)
from entity_standardizer.joint import standardize_contact
from entity_standardizer.registry import get_dial_plan
from entity_standardizer.standardizer import standardize_phone


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="entity-standardizer",
        description="Universal multi-national entity, address, phone, company, person, and web standardization CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # parse command
    parse_cmd = sub.add_parser("parse", help="Standardize a single phone number and output JSON.")
    parse_cmd.add_argument("phone", help="Raw phone number string to standardize.")
    parse_cmd.add_argument("-c", "--country", default=None, help="Optional ISO country hint (e.g. US, GB, DE).")
    parse_cmd.add_argument("-d", "--default-country", default="US", help="Fallback ISO country (default: US).")

    # country command
    country_cmd = sub.add_parser("country", help="Lookup ITU-T E.164 dial plan metadata for a country.")
    country_cmd.add_argument("identifier", help="ISO-2, ISO-3, numeric code, or country name.")

    # batch command
    batch_cmd = sub.add_parser("batch", help="Batch-standardize a CSV file.")
    batch_cmd.add_argument("input_csv", help="Input CSV file path.")
    batch_cmd.add_argument("output_csv", help="Output CSV file path.")
    batch_cmd.add_argument("--phone-col", default="phone", help="Column containing raw phone numbers.")
    batch_cmd.add_argument("--country-col", default="country", help="Optional column containing country hints.")
    batch_cmd.add_argument("--default-country", default="US", help="Fallback ISO country (default: US).")
    batch_cmd.add_argument("--address-col", default=None, help="Optional column containing street addresses.")
    batch_cmd.add_argument("--company-col", default=None, help="Optional column containing company names.")
    batch_cmd.add_argument("--person-col", default=None, help="Optional column containing person names.")
    batch_cmd.add_argument("--email-col", default=None, help="Optional column containing email addresses.")
    batch_cmd.add_argument("--url-col", default=None, help="Optional column containing website URLs.")

    # compare command
    cmp_cmd = sub.add_parser("compare", help="Compare two phone numbers for exact or fuzzy similarity.")
    cmp_cmd.add_argument("phone_a", help="First raw phone number.")
    cmp_cmd.add_argument("phone_b", help="Second raw phone number.")
    cmp_cmd.add_argument("-c", "--country", default=None, help="Optional ISO country hint.")
    cmp_cmd.add_argument("-t", "--threshold", type=float, default=0.88, help="Fuzzy threshold (default: 0.88).")

    # dedup command
    dedup_cmd = sub.add_parser("dedup", help="Cluster and deduplicate phone numbers into Golden Phone Records.")
    dedup_cmd.add_argument("phones", nargs="+", help="Raw phone strings to deduplicate.")
    dedup_cmd.add_argument("-c", "--country", default=None, help="Optional ISO country hint.")
    dedup_cmd.add_argument("-t", "--threshold", type=float, default=0.88, help="Fuzzy threshold (default: 0.88).")

    # address command
    addr_cmd = sub.add_parser("address", help="Standardize a physical/mailing address and output JSON.")
    addr_cmd.add_argument("street1", help="Primary street address line.")
    addr_cmd.add_argument("--street2", default=None, help="Secondary unit/suite line.")
    addr_cmd.add_argument("--city", default=None, help="City/locality.")
    addr_cmd.add_argument("--state", default=None, help="State/province/region.")
    addr_cmd.add_argument("--postal-code", default=None, help="ZIP or postal code.")
    addr_cmd.add_argument("-c", "--country", default="US", help="ISO country code or name (default: US).")
    addr_cmd.add_argument("--geocode", action="store_true", help="Enable offline spatial coordinate resolution.")
    addr_cmd.add_argument("--explain", action="store_true", help="Include standardization explanation and field confidence.")

    # compare-addresses command
    cmp_addr_cmd = sub.add_parser("compare-addresses", help="Compare two physical/mailing addresses and output JSON.")
    cmp_addr_cmd.add_argument("address_a", help="First raw address string.")
    cmp_addr_cmd.add_argument("address_b", help="Second raw address string.")
    cmp_addr_cmd.add_argument("-c", "--country", default="US", help="ISO country code or name (default: US).")
    cmp_addr_cmd.add_argument("-t", "--threshold", type=float, default=0.85, help="Fuzzy threshold (default: 0.85).")

    # dedup-addresses command
    dedup_addr_cmd = sub.add_parser("dedup-addresses", help="Cluster and deduplicate addresses into Golden Address Records.")
    dedup_addr_cmd.add_argument("addresses", nargs="+", help="Raw address strings to deduplicate.")
    dedup_addr_cmd.add_argument("-c", "--country", default="US", help="ISO country code or name (default: US).")
    dedup_addr_cmd.add_argument("-t", "--threshold", type=float, default=0.85, help="Fuzzy threshold (default: 0.85).")

    # autocomplete command
    auto_cmd = sub.add_parser("autocomplete", help="Autocomplete a partial street address prefix.")
    auto_cmd.add_argument("prefix", help="Partial street or address prefix string.")
    auto_cmd.add_argument("--city", default=None, help="Optional city filter.")
    auto_cmd.add_argument("--state", default=None, help="Optional state filter.")
    auto_cmd.add_argument("--postal-code", default=None, help="Optional postal code filter.")
    auto_cmd.add_argument("-n", "--max-results", type=int, default=5, help="Max suggestions to return (default: 5).")

    # company command
    company_cmd = sub.add_parser("company", help="Standardize an organization or company name and output JSON.")
    company_cmd.add_argument("name", help="Raw organization or company name.")
    company_cmd.add_argument("-c", "--country", default=None, help="Optional ISO country hint.")

    # person command
    person_cmd = sub.add_parser("person", help="Standardize a person full name and output JSON.")
    person_cmd.add_argument("name", help="Raw person full name.")

    # compare-companies command
    cmp_comp_cmd = sub.add_parser("compare-companies", help="Compare two company names and output JSON.")
    cmp_comp_cmd.add_argument("company_a", help="First company name.")
    cmp_comp_cmd.add_argument("company_b", help="Second company name.")

    # dedup-companies command
    dedup_comp_cmd = sub.add_parser("dedup-companies", help="Cluster and deduplicate company names into Golden Company Records.")
    dedup_comp_cmd.add_argument("companies", nargs="+", help="Raw company names to deduplicate.")
    dedup_comp_cmd.add_argument("-c", "--country", default=None, help="Optional ISO country hint.")
    dedup_comp_cmd.add_argument("-t", "--threshold", type=float, default=0.85, help="Fuzzy threshold (default: 0.85).")

    # compare-persons command
    cmp_per_cmd = sub.add_parser("compare-persons", help="Compare two person names and output JSON.")
    cmp_per_cmd.add_argument("person_a", help="First person full name.")
    cmp_per_cmd.add_argument("person_b", help="Second person full name.")

    # dedup-persons command
    dedup_per_cmd = sub.add_parser("dedup-persons", help="Cluster and deduplicate person names into Golden Person Records.")
    dedup_per_cmd.add_argument("persons", nargs="+", help="Raw person names to deduplicate.")
    dedup_per_cmd.add_argument("-t", "--threshold", type=float, default=0.85, help="Fuzzy threshold (default: 0.85).")

    # title command
    title_cmd = sub.add_parser("title", help="Standardize a job title and classify seniority and department.")
    title_cmd.add_argument("title", help="Raw job title string.")

    # email command
    email_cmd = sub.add_parser("email", help="Standardize an email address and output JSON.")
    email_cmd.add_argument("email", help="Raw email address string.")

    # compare-emails command
    cmp_email_cmd = sub.add_parser("compare-emails", help="Compare two email addresses and output JSON.")
    cmp_email_cmd.add_argument("email_a", help="First email address string.")
    cmp_email_cmd.add_argument("email_b", help="Second email address string.")

    # url command
    url_cmd = sub.add_parser("url", help="Standardize a website URL and extract registrable domain.")
    url_cmd.add_argument("url", help="Raw website URL string.")

    # compare-urls command
    cmp_url_cmd = sub.add_parser("compare-urls", help="Compare two website URLs and output JSON.")
    cmp_url_cmd.add_argument("url_a", help="First website URL string.")
    cmp_url_cmd.add_argument("url_b", help="Second website URL string.")

    # social command
    social_cmd = sub.add_parser("social", help="Standardize a social profile URL or @handle.")
    social_cmd.add_argument("profile", help="Raw social URL or @handle string.")
    social_cmd.add_argument("-p", "--platform", default=None, help="Optional social platform hint.")

    # contact command
    contact_cmd = sub.add_parser(
        "contact",
        help="Jointly standardize an entity's address, phone, company, person, title, and web pillars.",
    )
    contact_cmd.add_argument("--street1", default=None, help="Primary street address line.")
    contact_cmd.add_argument("--street2", default=None, help="Secondary unit/suite line.")
    contact_cmd.add_argument("--city", default=None, help="City/locality.")
    contact_cmd.add_argument("--state", default=None, help="State/province/region.")
    contact_cmd.add_argument("--postal-code", default=None, help="ZIP or postal code.")
    contact_cmd.add_argument("-c", "--country", default=None, help="Optional ISO country hint.")
    contact_cmd.add_argument("--phone", default=None, help="Raw telephone number.")
    contact_cmd.add_argument("--fax", default=None, help="Raw fax number.")
    contact_cmd.add_argument("--organization", default=None, help="Raw company or organization name.")
    contact_cmd.add_argument("--person-name", "--person", default=None, help="Raw contact person full name.")
    contact_cmd.add_argument("--job-title", default=None, help="Raw contact job title.")
    contact_cmd.add_argument("--email", default=None, help="Raw contact email address.")
    contact_cmd.add_argument("--website", default=None, help="Raw contact website URL.")
    contact_cmd.add_argument("--social", default=None, help="Raw contact social URL or @handle.")
    contact_cmd.add_argument("-d", "--default-country", default="US", help="Fallback ISO country (default: US).")

    # cluster-contacts command
    cluster_cmd = sub.add_parser("cluster-contacts", help="Cluster JSON contact records into Golden Entity Clusters.")
    cluster_cmd.add_argument("records_json", help="JSON array string of contact records.")
    cluster_cmd.add_argument("-d", "--default-country", default="US", help="Fallback ISO country (default: US).")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning exit status code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "parse":
        res = standardize_phone(
            args.phone,
            country=args.country,
            default_country=args.default_country,
        )
        sys.stdout.write(json.dumps(res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "country":
        plan = get_dial_plan(args.identifier)
        if plan is None:
            sys.stderr.write(f"Error: Unknown country identifier '{args.identifier}'\n")
            return 1
        sys.stdout.write(json.dumps(plan.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "compare":
        cmp_res = compare_phones(
            args.phone_a,
            args.phone_b,
            country=args.country,
            fuzzy_threshold=args.threshold,
        )
        sys.stdout.write(json.dumps(cmp_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "dedup":
        clusters = deduplicate_phones(
            args.phones,
            country=args.country,
            fuzzy_threshold=args.threshold,
        )
        sys.stdout.write(json.dumps([c.to_dict() for c in clusters], indent=2) + "\n")
        return 0

    if args.command == "address":
        addr_res = standardize_address(
            street1=args.street1,
            street2=args.street2,
            city=args.city,
            state=args.state,
            postal_code=args.postal_code,
            country=args.country,
            allow_locality=True,
            enable_geocoding=args.geocode,
            explain=args.explain,
        )
        sys.stdout.write(json.dumps(addr_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "compare-addresses":
        ca_res = compare_addresses(
            args.address_a,
            args.address_b,
            country=args.country,
            fuzzy_threshold=args.threshold,
        )
        sys.stdout.write(json.dumps(ca_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "dedup-addresses":
        addr_clusters = deduplicate_addresses(
            args.addresses,
            country=args.country,
            fuzzy_threshold=args.threshold,
        )
        sys.stdout.write(json.dumps([c.to_dict() for c in addr_clusters], indent=2) + "\n")
        return 0

    if args.command == "autocomplete":
        suggestions = autocomplete_address(
            prefix=args.prefix,
            city=args.city,
            state=args.state,
            postal_code=args.postal_code,
            max_results=args.max_results,
        )
        sys.stdout.write(json.dumps([s.to_dict() for s in suggestions], indent=2) + "\n")
        return 0

    if args.command == "company":
        comp_res = standardize_company(args.name, country=args.country)
        sys.stdout.write(json.dumps(comp_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "person":
        per_res = standardize_person(args.name)
        sys.stdout.write(json.dumps(per_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "compare-companies":
        cc_res = compare_companies(args.company_a, args.company_b)
        sys.stdout.write(json.dumps(cc_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "dedup-companies":
        comp_clusters = deduplicate_companies(
            args.companies,
            country=args.country,
            fuzzy_threshold=args.threshold,
        )
        sys.stdout.write(json.dumps([c.to_dict() for c in comp_clusters], indent=2) + "\n")
        return 0

    if args.command == "compare-persons":
        cp_res = compare_persons(args.person_a, args.person_b)
        sys.stdout.write(json.dumps(cp_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "dedup-persons":
        per_clusters = deduplicate_persons(
            args.persons,
            fuzzy_threshold=args.threshold,
        )
        sys.stdout.write(json.dumps([c.to_dict() for c in per_clusters], indent=2) + "\n")
        return 0

    if args.command == "title":
        title_res = standardize_job_title(args.title)
        sys.stdout.write(json.dumps(title_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "email":
        email_res = standardize_email(args.email)
        sys.stdout.write(json.dumps(email_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "compare-emails":
        ce_res = compare_emails(args.email_a, args.email_b)
        sys.stdout.write(json.dumps(ce_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "url":
        url_res = standardize_url(args.url)
        sys.stdout.write(json.dumps(url_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "compare-urls":
        cu_res = compare_urls(args.url_a, args.url_b)
        sys.stdout.write(json.dumps(cu_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "social":
        soc_res = standardize_social(args.profile, platform=args.platform)
        sys.stdout.write(json.dumps(soc_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "contact":
        contact_res = standardize_contact(
            street1=args.street1,
            street2=args.street2,
            city=args.city,
            state=args.state,
            postal_code=args.postal_code,
            country=args.country,
            phone=args.phone,
            fax=args.fax,
            organization=args.organization,
            person_name=args.person_name,
            job_title=args.job_title,
            email=args.email,
            website=args.website,
            social=args.social,
            default_country=args.default_country,
        )
        sys.stdout.write(json.dumps(contact_res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "cluster-contacts":
        records = json.loads(args.records_json)
        ent_clusters = cluster_contact_records(records, default_country=args.default_country)
        sys.stdout.write(json.dumps([c.to_dict() for c in ent_clusters], indent=2) + "\n")
        return 0

    # args.command == "batch"
    rows = stream_standardize_csv(
        args.input_csv,
        args.output_csv,
        phone_col=args.phone_col,
        country_col=args.country_col,
        default_country=args.default_country,
        address_col=args.address_col,
        company_col=args.company_col,
        person_col=args.person_col,
        email_col=args.email_col,
        url_col=args.url_col,
    )
    sys.stdout.write(json.dumps({"processed_rows": rows, "output_csv": args.output_csv}) + "\n")
    return 0
