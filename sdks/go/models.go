package phonestandardizer

// PhoneStandardizeRequest is the request payload for POST /v1/standardize and POST /v1/explain.
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

// PhoneCompareRequest is the request payload for POST /v1/compare.
type PhoneCompareRequest struct {
	PhoneA         string  `json:"phone_a"`
	PhoneB         string  `json:"phone_b"`
	Country        string  `json:"country,omitempty"`
	FuzzyThreshold float64 `json:"fuzzy_threshold,omitempty"`
}

// PhoneDeduplicateRequest is the request payload for POST /v1/deduplicate.
type PhoneDeduplicateRequest struct {
	Phones         []string `json:"phones"`
	Country        string   `json:"country,omitempty"`
	FuzzyThreshold float64  `json:"fuzzy_threshold,omitempty"`
}

// StandardizedPhone represents a normalized telephone record returned by Phone Standardizer.
// Nullable fields use *string so JSON null is distinguishable from an empty string.
type StandardizedPhone struct {
	RawInput                  string   `json:"raw_input"`
	E164                      *string  `json:"e164"`
	National                  *string  `json:"national"`
	International             *string  `json:"international"`
	RFC3966                   *string  `json:"rfc3966"`
	CountryCallingCode        *string  `json:"country_calling_code"`
	CountryISO2               *string  `json:"country_iso2"`
	CountryISO3               *string  `json:"country_iso3"`
	CountryName               *string  `json:"country_name"`
	NationalSignificantNumber *string  `json:"national_significant_number"`
	AreaCode                  *string  `json:"area_code"`
	SubscriberNumber          *string  `json:"subscriber_number"`
	Extension                 *string  `json:"extension"`
	VanityAlias               *string  `json:"vanity_alias"`
	RegionCode                *string  `json:"region_code"`
	LineType                  string   `json:"line_type"`
	IsValid                   bool     `json:"is_valid"`
	IsPossible                bool     `json:"is_possible"`
	PhoneKey                  *string  `json:"phone_key"`
	PhoneExtKey               *string  `json:"phone_ext_key"`
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

// PhoneComparisonResult represents the response payload from POST /v1/compare.
type PhoneComparisonResult struct {
	PhoneA                StandardizedPhone `json:"phone_a"`
	PhoneB                StandardizedPhone `json:"phone_b"`
	IsExactMatch          bool              `json:"is_exact_match"`
	IsExtensionVariant    bool              `json:"is_extension_variant"`
	IsFuzzyMatch          bool              `json:"is_fuzzy_match"`
	SimilarityScore       float64           `json:"similarity_score"`
	MatchType             string            `json:"match_type"`
	EditDistance          int               `json:"edit_distance"`
	TranspositionDetected bool              `json:"transposition_detected"`
	KeypadAdjacentTypo    bool              `json:"keypad_adjacent_typo"`
	Explanation           string            `json:"explanation"`
}

// PhoneCluster represents a deduplicated Golden Phone cluster.
type PhoneCluster struct {
	ClusterID   string              `json:"cluster_id"`
	GoldenPhone StandardizedPhone   `json:"golden_phone"`
	Members     []StandardizedPhone `json:"members"`
	RawInputs   []string            `json:"raw_inputs"`
	MatchTypes  []string            `json:"match_types"`
}

// DeduplicateResponse represents the response payload from POST /v1/deduplicate.
type DeduplicateResponse struct {
	ClusterCount int            `json:"cluster_count"`
	Clusters     []PhoneCluster `json:"clusters"`
}

// CountryDialPlan represents ITU-T E.164 dialing metadata for a country.
type CountryDialPlan struct {
	ISO2                string   `json:"iso2"`
	ISO3                string   `json:"iso3"`
	Numeric             string   `json:"numeric"`
	Name                string   `json:"name"`
	CallingCode         string   `json:"calling_code"`
	IDDPrefix           string   `json:"idd_prefix"`
	NationalTrunkPrefix *string  `json:"national_trunk_prefix"`
	NSNLengths          []int    `json:"nsn_lengths"`
	MobilePrefixes      []string `json:"mobile_prefixes"`
	TollFreePrefixes    []string `json:"toll_free_prefixes"`
	PremiumPrefixes     []string `json:"premium_prefixes"`
	VoIPPrefixes        []string `json:"voip_prefixes"`
	SharedCostPrefixes  []string `json:"shared_cost_prefixes"`
	Region              string   `json:"region"`
}

// ListCountriesResponse represents the response payload from GET /v1/countries.
type ListCountriesResponse struct {
	Count     int               `json:"count"`
	Countries []CountryDialPlan `json:"countries"`
}

// PhoneIntelligence represents geographic, carrier, and calling window intelligence.
type PhoneIntelligence struct {
	Locality      *string  `json:"locality"`
	Timezones     []string `json:"timezones"`
	CarrierHint   *string  `json:"carrier_hint"`
	IsCallableNow bool     `json:"is_callable_now"`
	LocalHours    []int    `json:"local_hours"`
}

// PhoneExplanation represents diagnostic healing and risk explanations.
type PhoneExplanation struct {
	HealingStepsCount   int      `json:"healing_steps_count"`
	HealingActions      []string `json:"healing_actions"`
	RiskFlagsCount      int      `json:"risk_flags_count"`
	RiskFlags           []string `json:"risk_flags"`
	Confidence          float64  `json:"confidence"`
	RoutingTier         string   `json:"routing_tier"`
	RequiresHumanReview bool     `json:"requires_human_review"`
}

// PhoneExplainReport represents the response payload from POST /v1/explain.
type PhoneExplainReport struct {
	Record       StandardizedPhone `json:"record"`
	Intelligence PhoneIntelligence `json:"intelligence"`
	Explanation  PhoneExplanation  `json:"explanation"`
}


