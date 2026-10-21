package phonestandardizer

// PhoneStandardizeRequest is the request payload for POST /v1/standardize.
type PhoneStandardizeRequest struct {
	Phone          string `json:"phone"`
	Country        string `json:"country,omitempty"`
	DefaultCountry string `json:"default_country,omitempty"`
}

// PhoneBatchRequest is the request payload for POST /v1/batch.
type PhoneBatchRequest struct {
	Phones         []string `json:"phones"`
	DefaultCountry string   `json:"default_country,omitempty"`
}

// StandardizedPhone represents a normalized telephone record returned by Phone Standardizer.
type StandardizedPhone struct {
	RawInput                  string   `json:"raw_input"`
	E164                      string   `json:"e164"`
	National                  string   `json:"national"`
	International             string   `json:"international"`
	RFC3966                   string   `json:"rfc3966"`
	CountryCallingCode        string   `json:"country_calling_code"`
	CountryISO2               string   `json:"country_iso2"`
	CountryISO3               string   `json:"country_iso3"`
	CountryName               string   `json:"country_name"`
	NationalSignificantNumber string   `json:"national_significant_number"`
	AreaCode                  string   `json:"area_code"`
	SubscriberNumber          string   `json:"subscriber_number"`
	Extension                 string   `json:"extension"`
	VanityAlias               string   `json:"vanity_alias"`
	RegionCode                string   `json:"region_code"`
	LineType                  string   `json:"line_type"`
	IsValid                   bool     `json:"is_valid"`
	IsPossible                bool     `json:"is_possible"`
	PhoneKey                  string   `json:"phone_key"`
	PhoneExtKey               string   `json:"phone_ext_key"`
	Confidence                float64  `json:"confidence"`
	RoutingTier               string   `json:"routing_tier"`
	RiskFlags                 []string `json:"risk_flags"`
	HealingActions            []string `json:"healing_actions"`
}

// BatchResponse represents the response payload from POST /v1/batch.
type BatchResponse struct {
	Count   int                 `json:"count"`
	Results []StandardizedPhone `json:"results"`
}
