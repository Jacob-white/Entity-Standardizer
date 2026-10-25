using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace EntityStandardizer.Client;

public sealed class HealthResponse
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = "";

    [JsonPropertyName("version")]
    public string Version { get; set; } = "";
}

public sealed class PhoneStandardizeRequest
{
    [JsonPropertyName("phone")]
    public string Phone { get; set; } = "";

    [JsonPropertyName("country")]
    public string? Country { get; set; }

    [JsonPropertyName("default_country")]
    public string? DefaultCountry { get; set; } = "US";
}

public sealed class PhoneBatchRequest
{
    [JsonPropertyName("phones")]
    public List<string> Phones { get; set; } = new();

    [JsonPropertyName("default_country")]
    public string? DefaultCountry { get; set; } = "US";
}

public sealed class StandardizedPhone
{
    [JsonPropertyName("raw_input")]
    public string RawInput { get; set; } = "";

    [JsonPropertyName("e164")]
    public string? E164 { get; set; }

    [JsonPropertyName("national")]
    public string? National { get; set; }

    [JsonPropertyName("international")]
    public string? International { get; set; }

    [JsonPropertyName("rfc3966")]
    public string? Rfc3966 { get; set; }

    [JsonPropertyName("country_calling_code")]
    public string? CountryCallingCode { get; set; }

    [JsonPropertyName("country_iso2")]
    public string? CountryIso2 { get; set; }

    [JsonPropertyName("country_iso3")]
    public string? CountryIso3 { get; set; }

    [JsonPropertyName("country_name")]
    public string? CountryName { get; set; }

    [JsonPropertyName("national_significant_number")]
    public string? NationalSignificantNumber { get; set; }

    [JsonPropertyName("area_code")]
    public string? AreaCode { get; set; }

    [JsonPropertyName("subscriber_number")]
    public string? SubscriberNumber { get; set; }

    [JsonPropertyName("extension")]
    public string? Extension { get; set; }

    [JsonPropertyName("vanity_alias")]
    public string? VanityAlias { get; set; }

    [JsonPropertyName("region_code")]
    public string? RegionCode { get; set; }

    [JsonPropertyName("line_type")]
    public string LineType { get; set; } = "UNKNOWN";

    [JsonPropertyName("is_valid")]
    public bool IsValid { get; set; }

    [JsonPropertyName("is_possible")]
    public bool IsPossible { get; set; }

    [JsonPropertyName("phone_key")]
    public string? PhoneKey { get; set; }

    [JsonPropertyName("phone_ext_key")]
    public string? PhoneExtKey { get; set; }

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }

    [JsonPropertyName("routing_tier")]
    public string RoutingTier { get; set; } = "MANUAL_STEWARDSHIP";

    [JsonPropertyName("risk_flags")]
    public List<string> RiskFlags { get; set; } = new();

    [JsonPropertyName("healing_actions")]
    public List<string> HealingActions { get; set; } = new();
}

public sealed class PhoneBatchResponse
{
    [JsonPropertyName("count")]
    public int Count { get; set; }

    [JsonPropertyName("results")]
    public List<StandardizedPhone> Results { get; set; } = new();
}

public sealed class PhoneCompareRequest
{
    [JsonPropertyName("phone_a")]
    public string PhoneA { get; set; } = "";

    [JsonPropertyName("phone_b")]
    public string PhoneB { get; set; } = "";

    [JsonPropertyName("country")]
    public string? Country { get; set; }

    [JsonPropertyName("fuzzy_threshold")]
    public double FuzzyThreshold { get; set; } = 0.88;
}

public sealed class PhoneComparisonResult
{
    [JsonPropertyName("phone_a")]
    public StandardizedPhone? PhoneA { get; set; }

    [JsonPropertyName("phone_b")]
    public StandardizedPhone? PhoneB { get; set; }

    [JsonPropertyName("is_exact_match")]
    public bool IsExactMatch { get; set; }

    [JsonPropertyName("is_extension_variant")]
    public bool IsExtensionVariant { get; set; }

    [JsonPropertyName("is_fuzzy_match")]
    public bool IsFuzzyMatch { get; set; }

    [JsonPropertyName("similarity_score")]
    public double SimilarityScore { get; set; }

    [JsonPropertyName("match_type")]
    public string MatchType { get; set; } = "";

    [JsonPropertyName("edit_distance")]
    public int EditDistance { get; set; }

    [JsonPropertyName("transposition_detected")]
    public bool TranspositionDetected { get; set; }

    [JsonPropertyName("keypad_adjacent_typo")]
    public bool KeypadAdjacentTypo { get; set; }

    [JsonPropertyName("explanation")]
    public string Explanation { get; set; } = "";
}

public sealed class PhoneDeduplicateRequest
{
    [JsonPropertyName("phones")]
    public List<string> Phones { get; set; } = new();

    [JsonPropertyName("country")]
    public string? Country { get; set; }

    [JsonPropertyName("fuzzy_threshold")]
    public double FuzzyThreshold { get; set; } = 0.88;
}

public sealed class PhoneCluster
{
    [JsonPropertyName("cluster_id")]
    public string ClusterId { get; set; } = "";

    [JsonPropertyName("golden_phone")]
    public StandardizedPhone? GoldenPhone { get; set; }

    [JsonPropertyName("members")]
    public List<StandardizedPhone> Members { get; set; } = new();

    [JsonPropertyName("raw_inputs")]
    public List<string> RawInputs { get; set; } = new();

    [JsonPropertyName("match_types")]
    public List<string> MatchTypes { get; set; } = new();
}

public sealed class PhoneDeduplicateResponse
{
    [JsonPropertyName("cluster_count")]
    public int ClusterCount { get; set; }

    [JsonPropertyName("clusters")]
    public List<PhoneCluster> Clusters { get; set; } = new();
}

public sealed class CountryDialPlan
{
    [JsonPropertyName("iso2")]
    public string Iso2 { get; set; } = "";

    [JsonPropertyName("iso3")]
    public string Iso3 { get; set; } = "";

    [JsonPropertyName("numeric")]
    public string Numeric { get; set; } = "";

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("calling_code")]
    public string CallingCode { get; set; } = "";

    [JsonPropertyName("idd_prefix")]
    public string IddPrefix { get; set; } = "";

    [JsonPropertyName("national_trunk_prefix")]
    public string? NationalTrunkPrefix { get; set; }

    [JsonPropertyName("nsn_lengths")]
    public List<int> NsnLengths { get; set; } = new();

    [JsonPropertyName("mobile_prefixes")]
    public List<string> MobilePrefixes { get; set; } = new();

    [JsonPropertyName("toll_free_prefixes")]
    public List<string> TollFreePrefixes { get; set; } = new();

    [JsonPropertyName("premium_prefixes")]
    public List<string> PremiumPrefixes { get; set; } = new();

    [JsonPropertyName("voip_prefixes")]
    public List<string> VoipPrefixes { get; set; } = new();

    [JsonPropertyName("shared_cost_prefixes")]
    public List<string> SharedCostPrefixes { get; set; } = new();

    [JsonPropertyName("region")]
    public string Region { get; set; } = "";
}

public sealed class ListCountriesResponse
{
    [JsonPropertyName("count")]
    public int Count { get; set; }

    [JsonPropertyName("countries")]
    public List<CountryDialPlan> Countries { get; set; } = new();
}

public sealed class PhoneIntelligence
{
    [JsonPropertyName("locality")]
    public string? Locality { get; set; }

    [JsonPropertyName("timezones")]
    public List<string> Timezones { get; set; } = new();

    [JsonPropertyName("carrier_hint")]
    public string? CarrierHint { get; set; }

    [JsonPropertyName("is_callable_now")]
    public bool IsCallableNow { get; set; }

    [JsonPropertyName("local_hours")]
    public List<int> LocalHours { get; set; } = new();
}

public sealed class PhoneExplanation
{
    [JsonPropertyName("healing_steps_count")]
    public int HealingStepsCount { get; set; }

    [JsonPropertyName("healing_actions")]
    public List<string> HealingActions { get; set; } = new();

    [JsonPropertyName("risk_flags_count")]
    public int RiskFlagsCount { get; set; }

    [JsonPropertyName("risk_flags")]
    public List<string> RiskFlags { get; set; } = new();

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }

    [JsonPropertyName("routing_tier")]
    public string RoutingTier { get; set; } = "MANUAL_STEWARDSHIP";

    [JsonPropertyName("requires_human_review")]
    public bool RequiresHumanReview { get; set; }
}

public sealed class PhoneExplainReport
{
    [JsonPropertyName("record")]
    public StandardizedPhone? Record { get; set; }

    [JsonPropertyName("intelligence")]
    public PhoneIntelligence? Intelligence { get; set; }

    [JsonPropertyName("explanation")]
    public PhoneExplanation? Explanation { get; set; }
}

public sealed class ReadyResponse
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = "";

    [JsonPropertyName("version")]
    public string Version { get; set; } = "";

    [JsonPropertyName("native_available")]
    public bool NativeAvailable { get; set; }
}

public sealed class AddressStandardizeRequest
{
    [JsonPropertyName("street1")]
    public string? Street1 { get; set; }

    [JsonPropertyName("street2")]
    public string? Street2 { get; set; }

    [JsonPropertyName("city")]
    public string? City { get; set; }

    [JsonPropertyName("state")]
    public string? State { get; set; }

    [JsonPropertyName("postal_code")]
    public string? PostalCode { get; set; }

    [JsonPropertyName("country")]
    public string Country { get; set; } = "US";

    [JsonPropertyName("enable_geocoding")]
    public bool EnableGeocoding { get; set; }

    [JsonPropertyName("explain")]
    public bool Explain { get; set; }
}

public sealed class AddressCompareRequest
{
    [JsonPropertyName("address_a")]
    public object AddressA { get; set; } = "";

    [JsonPropertyName("address_b")]
    public object AddressB { get; set; } = "";

    [JsonPropertyName("country")]
    public string Country { get; set; } = "US";

    [JsonPropertyName("fuzzy_threshold")]
    public double FuzzyThreshold { get; set; } = 0.85;
}

public sealed class AddressDeduplicateRequest
{
    [JsonPropertyName("addresses")]
    public List<object> Addresses { get; set; } = new();

    [JsonPropertyName("country")]
    public string Country { get; set; } = "US";

    [JsonPropertyName("fuzzy_threshold")]
    public double FuzzyThreshold { get; set; } = 0.85;
}

public sealed class AddressAutocompleteRequest
{
    [JsonPropertyName("prefix")]
    public string Prefix { get; set; } = "";

    [JsonPropertyName("city")]
    public string? City { get; set; }

    [JsonPropertyName("state")]
    public string? State { get; set; }

    [JsonPropertyName("postal_code")]
    public string? PostalCode { get; set; }

    [JsonPropertyName("max_results")]
    public int MaxResults { get; set; } = 5;
}

public sealed class AutocompleteSuggestion
{
    [JsonPropertyName("text")]
    public string Text { get; set; } = "";

    [JsonPropertyName("street1")]
    public string Street1 { get; set; } = "";

    [JsonPropertyName("street2")]
    public string Street2 { get; set; } = "";

    [JsonPropertyName("street_line")]
    public string StreetLine { get; set; } = "";

    [JsonPropertyName("city")]
    public string City { get; set; } = "";

    [JsonPropertyName("state")]
    public string State { get; set; } = "";

    [JsonPropertyName("postal_code")]
    public string PostalCode { get; set; } = "";

    [JsonPropertyName("country")]
    public string Country { get; set; } = "USA";

    [JsonPropertyName("secondary_prompt_required")]
    public bool SecondaryPromptRequired { get; set; }

    [JsonPropertyName("suggested_secondary_units")]
    public List<string> SuggestedSecondaryUnits { get; set; } = new();

    [JsonPropertyName("highlight_ranges")]
    public List<List<int>> HighlightRanges { get; set; } = new();

    [JsonPropertyName("score")]
    public double Score { get; set; }

    [JsonPropertyName("prompt_message")]
    public string? PromptMessage { get; set; }

    [JsonPropertyName("latitude")]
    public double? Latitude { get; set; }

    [JsonPropertyName("longitude")]
    public double? Longitude { get; set; }

    [JsonPropertyName("distance_meters")]
    public double? DistanceMeters { get; set; }
}

public sealed class AddressAutocompleteResponse
{
    [JsonPropertyName("count")]
    public int Count { get; set; }

    [JsonPropertyName("suggestions")]
    public List<AutocompleteSuggestion> Suggestions { get; set; } = new();
}

public sealed class AddressComparisonResult
{
    [JsonPropertyName("is_match")]
    public bool IsMatch { get; set; }

    [JsonPropertyName("score")]
    public double Score { get; set; }

    [JsonPropertyName("match_type")]
    public string MatchType { get; set; } = "";

    [JsonPropertyName("address_a")]
    public StandardizedAddress? AddressA { get; set; }

    [JsonPropertyName("address_b")]
    public StandardizedAddress? AddressB { get; set; }
}

public sealed class AddressCluster
{
    [JsonPropertyName("cluster_id")]
    public int ClusterId { get; set; }

    [JsonPropertyName("golden_address")]
    public StandardizedAddress? GoldenAddress { get; set; }

    [JsonPropertyName("members")]
    public List<StandardizedAddress> Members { get; set; } = new();

    [JsonPropertyName("raw_inputs")]
    public List<object> RawInputs { get; set; } = new();

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }
}

public sealed class AddressDeduplicateResponse
{
    [JsonPropertyName("cluster_count")]
    public int ClusterCount { get; set; }

    [JsonPropertyName("clusters")]
    public List<AddressCluster> Clusters { get; set; } = new();
}

public sealed class CompanyStandardizeRequest
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("country")]
    public string? Country { get; set; }
}

public sealed class CompanyCompareRequest
{
    [JsonPropertyName("company_a")]
    public string CompanyA { get; set; } = "";

    [JsonPropertyName("company_b")]
    public string CompanyB { get; set; } = "";
}

public sealed class CompanyDeduplicateRequest
{
    [JsonPropertyName("companies")]
    public List<string> Companies { get; set; } = new();

    [JsonPropertyName("country")]
    public string? Country { get; set; }

    [JsonPropertyName("fuzzy_threshold")]
    public double FuzzyThreshold { get; set; } = 0.85;
}

public sealed class CompanyCluster
{
    [JsonPropertyName("cluster_id")]
    public string ClusterId { get; set; } = "";

    [JsonPropertyName("golden_company")]
    public StandardizedCompany? GoldenCompany { get; set; }

    [JsonPropertyName("members")]
    public List<StandardizedCompany> Members { get; set; } = new();

    [JsonPropertyName("raw_inputs")]
    public List<string> RawInputs { get; set; } = new();

    [JsonPropertyName("match_types")]
    public List<string> MatchTypes { get; set; } = new();
}

public sealed class CompanyDeduplicateResponse
{
    [JsonPropertyName("cluster_count")]
    public int ClusterCount { get; set; }

    [JsonPropertyName("clusters")]
    public List<CompanyCluster> Clusters { get; set; } = new();
}

public sealed class PersonStandardizeRequest
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";
}

public sealed class PersonCompareRequest
{
    [JsonPropertyName("person_a")]
    public string PersonA { get; set; } = "";

    [JsonPropertyName("person_b")]
    public string PersonB { get; set; } = "";
}

public sealed class PersonDeduplicateRequest
{
    [JsonPropertyName("persons")]
    public List<string> Persons { get; set; } = new();

    [JsonPropertyName("fuzzy_threshold")]
    public double FuzzyThreshold { get; set; } = 0.85;
}

public sealed class PersonCluster
{
    [JsonPropertyName("cluster_id")]
    public string ClusterId { get; set; } = "";

    [JsonPropertyName("golden_person")]
    public StandardizedPerson? GoldenPerson { get; set; }

    [JsonPropertyName("members")]
    public List<StandardizedPerson> Members { get; set; } = new();

    [JsonPropertyName("raw_inputs")]
    public List<string> RawInputs { get; set; } = new();

    [JsonPropertyName("match_types")]
    public List<string> MatchTypes { get; set; } = new();
}

public sealed class PersonDeduplicateResponse
{
    [JsonPropertyName("cluster_count")]
    public int ClusterCount { get; set; }

    [JsonPropertyName("clusters")]
    public List<PersonCluster> Clusters { get; set; } = new();
}

public sealed class JobTitleStandardizeRequest
{
    [JsonPropertyName("title")]
    public string Title { get; set; } = "";
}

public sealed class EmailStandardizeRequest
{
    [JsonPropertyName("email")]
    public string Email { get; set; } = "";
}

public sealed class EmailCompareRequest
{
    [JsonPropertyName("email_a")]
    public string EmailA { get; set; } = "";

    [JsonPropertyName("email_b")]
    public string EmailB { get; set; } = "";
}

public sealed class EmailComparisonResult
{
    [JsonPropertyName("is_match")]
    public bool IsMatch { get; set; }

    [JsonPropertyName("score")]
    public double Score { get; set; }

    [JsonPropertyName("match_type")]
    public string MatchType { get; set; } = "";

    [JsonPropertyName("email_a")]
    public StandardizedEmail? EmailA { get; set; }

    [JsonPropertyName("email_b")]
    public StandardizedEmail? EmailB { get; set; }
}

public sealed class UrlStandardizeRequest
{
    [JsonPropertyName("url")]
    public string Url { get; set; } = "";
}

public sealed class UrlCompareRequest
{
    [JsonPropertyName("url_a")]
    public string UrlA { get; set; } = "";

    [JsonPropertyName("url_b")]
    public string UrlB { get; set; } = "";
}

public sealed class UrlComparisonResult
{
    [JsonPropertyName("is_match")]
    public bool IsMatch { get; set; }

    [JsonPropertyName("score")]
    public double Score { get; set; }

    [JsonPropertyName("match_type")]
    public string MatchType { get; set; } = "";

    [JsonPropertyName("url_a")]
    public StandardizedUrl? UrlA { get; set; }

    [JsonPropertyName("url_b")]
    public StandardizedUrl? UrlB { get; set; }
}

public sealed class SocialStandardizeRequest
{
    [JsonPropertyName("profile")]
    public string Profile { get; set; } = "";

    [JsonPropertyName("platform")]
    public string? Platform { get; set; }
}

public sealed class ContactStandardizeRequest
{
    [JsonPropertyName("street1")]
    public string? Street1 { get; set; }

    [JsonPropertyName("street2")]
    public string? Street2 { get; set; }

    [JsonPropertyName("city")]
    public string? City { get; set; }

    [JsonPropertyName("state")]
    public string? State { get; set; }

    [JsonPropertyName("postal_code")]
    public string? PostalCode { get; set; }

    [JsonPropertyName("country")]
    public string? Country { get; set; }

    [JsonPropertyName("phone")]
    public string? Phone { get; set; }

    [JsonPropertyName("fax")]
    public string? Fax { get; set; }

    [JsonPropertyName("organization")]
    public string? Organization { get; set; }

    [JsonPropertyName("person_name")]
    public string? PersonName { get; set; }

    [JsonPropertyName("job_title")]
    public string? JobTitle { get; set; }

    [JsonPropertyName("email")]
    public string? Email { get; set; }

    [JsonPropertyName("website")]
    public string? Website { get; set; }

    [JsonPropertyName("social")]
    public string? Social { get; set; }

    [JsonPropertyName("default_country")]
    public string DefaultCountry { get; set; } = "US";
}

public sealed class ContactCompareRequest
{
    [JsonPropertyName("contact_a")]
    public Dictionary<string, object?> ContactA { get; set; } = new();

    [JsonPropertyName("contact_b")]
    public Dictionary<string, object?> ContactB { get; set; } = new();

    [JsonPropertyName("default_country")]
    public string DefaultCountry { get; set; } = "US";
}

public sealed class ContactClusterRequest
{
    [JsonPropertyName("records")]
    public List<Dictionary<string, object?>> Records { get; set; } = new();

    [JsonPropertyName("default_country")]
    public string DefaultCountry { get; set; } = "US";
}

public sealed class ContactCluster
{
    [JsonPropertyName("cluster_id")]
    public string ClusterId { get; set; } = "";

    [JsonPropertyName("golden_phone")]
    public StandardizedPhone? GoldenPhone { get; set; }

    [JsonPropertyName("golden_address_key")]
    public string? GoldenAddressKey { get; set; }

    [JsonPropertyName("record_ids")]
    public List<string> RecordIds { get; set; } = new();

    [JsonPropertyName("records")]
    public List<Dictionary<string, object?>> Records { get; set; } = new();

    [JsonPropertyName("linkage_reasons")]
    public List<string> LinkageReasons { get; set; } = new();
}

public sealed class ContactClusterResponse
{
    [JsonPropertyName("cluster_count")]
    public int ClusterCount { get; set; }

    [JsonPropertyName("clusters")]
    public List<ContactCluster> Clusters { get; set; } = new();
}

public sealed class ContactBatchRequest
{
    [JsonPropertyName("contacts")]
    public List<Dictionary<string, object?>> Contacts { get; set; } = new();

    [JsonPropertyName("default_country")]
    public string DefaultCountry { get; set; } = "US";
}

public sealed class ContactBatchResponse
{
    [JsonPropertyName("count")]
    public int Count { get; set; }

    [JsonPropertyName("results")]
    public List<StandardizedContact> Results { get; set; } = new();
}

public sealed class StandardizedAddress
{
    [JsonPropertyName("street1")]
    public string Street1 { get; set; } = "";

    [JsonPropertyName("street2")]
    public string Street2 { get; set; } = "";

    [JsonPropertyName("city")]
    public string City { get; set; } = "";

    [JsonPropertyName("state")]
    public string State { get; set; } = "";

    [JsonPropertyName("postal_code")]
    public string PostalCode { get; set; } = "";

    [JsonPropertyName("country")]
    public string Country { get; set; } = "";

    [JsonPropertyName("normalized_address_key")]
    public string? NormalizedAddressKey { get; set; }

    [JsonPropertyName("building_key")]
    public string? BuildingKey { get; set; }

    [JsonPropertyName("phonetic_key")]
    public string? PhoneticKey { get; set; }

    [JsonPropertyName("address_status")]
    public string AddressStatus { get; set; } = "";

    [JsonPropertyName("raw_street_address")]
    public string RawStreetAddress { get; set; } = "";

    [JsonPropertyName("is_us")]
    public bool IsUs { get; set; }

    [JsonPropertyName("is_private_residence")]
    public bool IsPrivateResidence { get; set; }

    [JsonPropertyName("is_registered_agent_hub")]
    public bool IsRegisteredAgentHub { get; set; }
}

public sealed class StandardizedCompany
{
    [JsonPropertyName("raw_input")]
    public string RawInput { get; set; } = "";

    [JsonPropertyName("legal_name")]
    public string? LegalName { get; set; }

    [JsonPropertyName("base_name")]
    public string? BaseName { get; set; }

    [JsonPropertyName("brand_stem")]
    public string? BrandStem { get; set; }

    [JsonPropertyName("legal_suffix")]
    public string? LegalSuffix { get; set; }

    [JsonPropertyName("dba_name")]
    public string? DbaName { get; set; }

    [JsonPropertyName("fka_name")]
    public string? FkaName { get; set; }

    [JsonPropertyName("branch_unit")]
    public string? BranchUnit { get; set; }

    [JsonPropertyName("inferred_country_iso2")]
    public string? InferredCountryIso2 { get; set; }

    [JsonPropertyName("company_key")]
    public string? CompanyKey { get; set; }

    [JsonPropertyName("brand_key")]
    public string? BrandKey { get; set; }

    [JsonPropertyName("phonetic_key")]
    public string? PhoneticKey { get; set; }

    [JsonPropertyName("is_valid")]
    public bool IsValid { get; set; }

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }

    [JsonPropertyName("healing_actions")]
    public List<string> HealingActions { get; set; } = new();
}

public sealed class CompanyComparisonResult
{
    [JsonPropertyName("is_match")]
    public bool IsMatch { get; set; }

    [JsonPropertyName("score")]
    public double Score { get; set; }

    [JsonPropertyName("match_type")]
    public string MatchType { get; set; } = "";

    [JsonPropertyName("company_a")]
    public StandardizedCompany? CompanyA { get; set; }

    [JsonPropertyName("company_b")]
    public StandardizedCompany? CompanyB { get; set; }
}

public sealed class StandardizedPerson
{
    [JsonPropertyName("raw_input")]
    public string RawInput { get; set; } = "";

    [JsonPropertyName("salutation")]
    public string? Salutation { get; set; }

    [JsonPropertyName("first_name")]
    public string? FirstName { get; set; }

    [JsonPropertyName("root_first_name")]
    public string? RootFirstName { get; set; }

    [JsonPropertyName("middle_name")]
    public string? MiddleName { get; set; }

    [JsonPropertyName("last_name")]
    public string? LastName { get; set; }

    [JsonPropertyName("nickname")]
    public string? Nickname { get; set; }

    [JsonPropertyName("generational_suffix")]
    public string? GenerationalSuffix { get; set; }

    [JsonPropertyName("credentials")]
    public List<string> Credentials { get; set; } = new();

    [JsonPropertyName("full_name")]
    public string? FullName { get; set; }

    [JsonPropertyName("person_key")]
    public string? PersonKey { get; set; }

    [JsonPropertyName("person_root_key")]
    public string? PersonRootKey { get; set; }

    [JsonPropertyName("phonetic_key")]
    public string? PhoneticKey { get; set; }

    [JsonPropertyName("is_organization")]
    public bool IsOrganization { get; set; }

    [JsonPropertyName("is_valid")]
    public bool IsValid { get; set; }

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }

    [JsonPropertyName("healing_actions")]
    public List<string> HealingActions { get; set; } = new();
}

public sealed class PersonComparisonResult
{
    [JsonPropertyName("is_match")]
    public bool IsMatch { get; set; }

    [JsonPropertyName("score")]
    public double Score { get; set; }

    [JsonPropertyName("match_type")]
    public string MatchType { get; set; } = "";

    [JsonPropertyName("person_a")]
    public StandardizedPerson? PersonA { get; set; }

    [JsonPropertyName("person_b")]
    public StandardizedPerson? PersonB { get; set; }
}

public sealed class StandardizedJobTitle
{
    [JsonPropertyName("raw_input")]
    public string RawInput { get; set; } = "";

    [JsonPropertyName("normalized_title")]
    public string? NormalizedTitle { get; set; }

    [JsonPropertyName("seniority_level")]
    public string? SeniorityLevel { get; set; }

    [JsonPropertyName("department")]
    public string? Department { get; set; }

    [JsonPropertyName("is_executive")]
    public bool IsExecutive { get; set; }

    [JsonPropertyName("is_valid")]
    public bool IsValid { get; set; }

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }

    [JsonPropertyName("healing_actions")]
    public List<string> HealingActions { get; set; } = new();
}

public sealed class StandardizedEmail
{
    [JsonPropertyName("raw_input")]
    public string RawInput { get; set; } = "";

    [JsonPropertyName("email")]
    public string? Email { get; set; }

    [JsonPropertyName("local_part")]
    public string? LocalPart { get; set; }

    [JsonPropertyName("raw_local_part")]
    public string? RawLocalPart { get; set; }

    [JsonPropertyName("subaddress")]
    public string? Subaddress { get; set; }

    [JsonPropertyName("domain")]
    public string? Domain { get; set; }

    [JsonPropertyName("display_name")]
    public string? DisplayName { get; set; }

    [JsonPropertyName("email_type")]
    public string? EmailType { get; set; }

    [JsonPropertyName("is_free_provider")]
    public bool IsFreeProvider { get; set; }

    [JsonPropertyName("is_role_account")]
    public bool IsRoleAccount { get; set; }

    [JsonPropertyName("is_disposable")]
    public bool IsDisposable { get; set; }

    [JsonPropertyName("inferred_country_iso2")]
    public string? InferredCountryIso2 { get; set; }

    [JsonPropertyName("email_key")]
    public string? EmailKey { get; set; }

    [JsonPropertyName("is_valid")]
    public bool IsValid { get; set; }

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }

    [JsonPropertyName("healing_actions")]
    public List<string> HealingActions { get; set; } = new();
}

public sealed class StandardizedUrl
{
    [JsonPropertyName("raw_input")]
    public string RawInput { get; set; } = "";

    [JsonPropertyName("url")]
    public string? Url { get; set; }

    [JsonPropertyName("scheme")]
    public string? Scheme { get; set; }

    [JsonPropertyName("host")]
    public string? Host { get; set; }

    [JsonPropertyName("domain")]
    public string? Domain { get; set; }

    [JsonPropertyName("subdomain")]
    public string? Subdomain { get; set; }

    [JsonPropertyName("public_suffix")]
    public string? PublicSuffix { get; set; }

    [JsonPropertyName("brand_stem")]
    public string? BrandStem { get; set; }

    [JsonPropertyName("path")]
    public string? Path { get; set; }

    [JsonPropertyName("inferred_country_iso2")]
    public string? InferredCountryIso2 { get; set; }

    [JsonPropertyName("url_key")]
    public string? UrlKey { get; set; }

    [JsonPropertyName("is_valid")]
    public bool IsValid { get; set; }

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }

    [JsonPropertyName("healing_actions")]
    public List<string> HealingActions { get; set; } = new();
}

public sealed class StandardizedSocial
{
    [JsonPropertyName("raw_input")]
    public string RawInput { get; set; } = "";

    [JsonPropertyName("platform")]
    public string? Platform { get; set; }

    [JsonPropertyName("profile_type")]
    public string? ProfileType { get; set; }

    [JsonPropertyName("handle")]
    public string? Handle { get; set; }

    [JsonPropertyName("url")]
    public string? Url { get; set; }

    [JsonPropertyName("social_key")]
    public string? SocialKey { get; set; }

    [JsonPropertyName("is_valid")]
    public bool IsValid { get; set; }

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }

    [JsonPropertyName("healing_actions")]
    public List<string> HealingActions { get; set; } = new();
}

public sealed class StandardizedContact
{
    [JsonPropertyName("address")]
    public StandardizedAddress? Address { get; set; }

    [JsonPropertyName("phone")]
    public StandardizedPhone? Phone { get; set; }

    [JsonPropertyName("fax")]
    public StandardizedPhone? Fax { get; set; }

    [JsonPropertyName("organization")]
    public StandardizedCompany? Organization { get; set; }

    [JsonPropertyName("person")]
    public StandardizedPerson? Person { get; set; }

    [JsonPropertyName("additional_persons")]
    public List<StandardizedPerson> AdditionalPersons { get; set; } = new();

    [JsonPropertyName("job_title")]
    public StandardizedJobTitle? JobTitle { get; set; }

    [JsonPropertyName("email")]
    public StandardizedEmail? Email { get; set; }

    [JsonPropertyName("website")]
    public StandardizedUrl? Website { get; set; }

    [JsonPropertyName("social")]
    public StandardizedSocial? Social { get; set; }

    [JsonPropertyName("entity_key")]
    public string? EntityKey { get; set; }

    [JsonPropertyName("cross_healing_actions")]
    public List<string> CrossHealingActions { get; set; } = new();

    [JsonPropertyName("overall_confidence")]
    public double OverallConfidence { get; set; }
}

public sealed class ContactComparisonResult
{
    [JsonPropertyName("is_match")]
    public bool IsMatch { get; set; }

    [JsonPropertyName("score")]
    public double Score { get; set; }

    [JsonPropertyName("match_type")]
    public string MatchType { get; set; } = "";

    [JsonPropertyName("matched_pillars")]
    public List<string> MatchedPillars { get; set; } = new();

    [JsonPropertyName("pillar_scores")]
    public Dictionary<string, double> PillarScores { get; set; } = new();

    [JsonPropertyName("contact_a")]
    public StandardizedContact? ContactA { get; set; }

    [JsonPropertyName("contact_b")]
    public StandardizedContact? ContactB { get; set; }
}
