# Python API (generated)

Docstrings of the main public entry points, rendered from the source. The prose [API reference](api_reference.md) covers
the full surface, the CLI, the HTTP service, and the MCP server.

## Joint Contact Cross-Healing & Comparison

::: entity_standardizer.joint.standardize_contact

::: entity_standardizer.joint.StandardizedContact

::: entity_standardizer.joint.compare_contacts

::: entity_standardizer.joint.ContactComparisonResult

## Organization / Company Standardization

::: entity_standardizer.company.standardize_company

::: entity_standardizer.company.StandardizedCompany

::: entity_standardizer.company.compare_companies

::: entity_standardizer.company.deduplicate_companies

## Person & Job Title Standardization

::: entity_standardizer.person.standardize_person

::: entity_standardizer.person.StandardizedPerson

::: entity_standardizer.person.split_compound_persons

::: entity_standardizer.person.standardize_job_title

::: entity_standardizer.person.compare_persons

::: entity_standardizer.person.deduplicate_persons

## Email, Website URL & Social Standardization

::: entity_standardizer.web.standardize_email

::: entity_standardizer.web.standardize_url

::: entity_standardizer.web.standardize_social

::: entity_standardizer.web.compare_emails

::: entity_standardizer.web.compare_urls

## Address Standardization, Comparison & Deduplication

::: entity_standardizer.address.standardize_address

::: entity_standardizer.address.StandardizedAddress

::: entity_standardizer.dedup.compare_addresses

::: entity_standardizer.dedup.AddressComparisonResult

::: entity_standardizer.dedup.deduplicate_addresses

::: entity_standardizer.dedup.AddressCluster

::: entity_standardizer.address.autocomplete_address

::: entity_standardizer.address.generate_normalized_address_key

::: entity_standardizer.address.normalize_country_code

::: entity_standardizer.address.batch_standardize

::: entity_standardizer.address.compute_confidence_score

## Telephone Standardization & Entity Resolution

::: entity_standardizer.standardizer.standardize_phone

::: entity_standardizer.models.StandardizedPhone

::: entity_standardizer.dedup.compare_phones

::: entity_standardizer.dedup.deduplicate_phones

::: entity_standardizer.dedup.cluster_contact_records

## Columnar Apache Arrow, Polars & DuckDB SQL UDFs

::: entity_standardizer.arrow.standardize_arrow

::: entity_standardizer.arrow.standardize_addresses_arrow

::: entity_standardizer.arrow.standardize_companies_arrow

::: entity_standardizer.arrow.standardize_persons_arrow

::: entity_standardizer.arrow.standardize_emails_arrow

::: entity_standardizer.arrow.standardize_urls_arrow

::: entity_standardizer.arrow.standardize_socials_arrow

::: entity_standardizer.arrow.standardize_contacts_arrow

::: entity_standardizer.arrow.register_duckdb_udfs

