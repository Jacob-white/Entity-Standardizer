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
