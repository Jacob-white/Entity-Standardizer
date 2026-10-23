using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace PhoneStandardizer.Client;

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

    [JsonPropertyName("default_country")]
    public string DefaultCountry { get; set; } = "US";
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

public sealed class StandardizedContact
{
    [JsonPropertyName("address")]
    public StandardizedAddress? Address { get; set; }

    [JsonPropertyName("phone")]
    public StandardizedPhone? Phone { get; set; }

    [JsonPropertyName("fax")]
    public StandardizedPhone? Fax { get; set; }

    [JsonPropertyName("entity_key")]
    public string? EntityKey { get; set; }

    [JsonPropertyName("cross_healing_actions")]
    public List<string> CrossHealingActions { get; set; } = new();

    [JsonPropertyName("overall_confidence")]
    public double OverallConfidence { get; set; }
}

