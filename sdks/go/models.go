package entitystandardizer

// HealthResponse is the response payload for GET /health.
type HealthResponse struct {
	Status  string `json:"status"`
	Version string `json:"version"`
}

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

// ReadyResponse is the response payload for GET /ready.
type ReadyResponse struct {
	Status          string `json:"status"`
	Version         string `json:"version"`
	NativeAvailable bool   `json:"native_available"`
}

// AddressStandardizeRequest is the request payload for POST /v1/address.
type AddressStandardizeRequest struct {
	Street1         string `json:"street1,omitempty"`
	Street2         string `json:"street2,omitempty"`
	City            string `json:"city,omitempty"`
	State           string `json:"state,omitempty"`
	PostalCode      string `json:"postal_code,omitempty"`
	Country         string `json:"country,omitempty"`
	EnableGeocoding bool   `json:"enable_geocoding,omitempty"`
	Explain         bool   `json:"explain,omitempty"`
}

// AddressCompareRequest is the request payload for POST /v1/address/compare.
type AddressCompareRequest struct {
	AddressA       any     `json:"address_a"`
	AddressB       any     `json:"address_b"`
	Country        string  `json:"country,omitempty"`
	FuzzyThreshold float64 `json:"fuzzy_threshold,omitempty"`
}

// AddressDeduplicateRequest is the request payload for POST /v1/address/deduplicate.
type AddressDeduplicateRequest struct {
	Addresses      []any   `json:"addresses"`
	Country        string  `json:"country,omitempty"`
	FuzzyThreshold float64 `json:"fuzzy_threshold,omitempty"`
}

// AddressAutocompleteRequest is the request payload for POST /v1/address/autocomplete.
type AddressAutocompleteRequest struct {
	Prefix     string `json:"prefix"`
	City       string `json:"city,omitempty"`
	State      string `json:"state,omitempty"`
	PostalCode string `json:"postal_code,omitempty"`
	MaxResults int    `json:"max_results,omitempty"`
}

// AutocompleteSuggestion represents a single address autocomplete suggestion.
type AutocompleteSuggestion struct {
	Text                    string   `json:"text"`
	Street1                 string   `json:"street1"`
	Street2                 string   `json:"street2"`
	StreetLine              string   `json:"street_line"`
	City                    string   `json:"city"`
	State                   string   `json:"state"`
	PostalCode              string   `json:"postal_code"`
	Country                 string   `json:"country"`
	SecondaryPromptRequired bool     `json:"secondary_prompt_required"`
	SuggestedSecondaryUnits []string `json:"suggested_secondary_units"`
	HighlightRanges         [][]int  `json:"highlight_ranges"`
	Score                   float64  `json:"score"`
	PromptMessage           *string  `json:"prompt_message"`
	Latitude                *float64 `json:"latitude"`
	Longitude               *float64 `json:"longitude"`
	DistanceMeters          *float64 `json:"distance_meters"`
}

// AddressAutocompleteResponse represents the response payload from POST /v1/address/autocomplete.
type AddressAutocompleteResponse struct {
	Count       int                      `json:"count"`
	Suggestions []AutocompleteSuggestion `json:"suggestions"`
}

// AddressComparisonResult represents the response payload from POST /v1/address/compare.
type AddressComparisonResult struct {
	IsMatch   bool                `json:"is_match"`
	Score     float64             `json:"score"`
	MatchType string              `json:"match_type"`
	AddressA  StandardizedAddress `json:"address_a"`
	AddressB  StandardizedAddress `json:"address_b"`
}

// AddressCluster represents a deduplicated Golden Address cluster.
type AddressCluster struct {
	ClusterID     int                   `json:"cluster_id"`
	GoldenAddress StandardizedAddress   `json:"golden_address"`
	Members       []StandardizedAddress `json:"members"`
	RawInputs     []any                 `json:"raw_inputs"`
	Confidence    float64               `json:"confidence"`
}

// AddressDeduplicateResponse represents the response payload from POST /v1/address/deduplicate.
type AddressDeduplicateResponse struct {
	ClusterCount int              `json:"cluster_count"`
	Clusters     []AddressCluster `json:"clusters"`
}

// CompanyStandardizeRequest is the request payload for POST /v1/company.
type CompanyStandardizeRequest struct {
	Name    string `json:"name"`
	Country string `json:"country,omitempty"`
}

// CompanyCompareRequest is the request payload for POST /v1/company/compare.
type CompanyCompareRequest struct {
	CompanyA string `json:"company_a"`
	CompanyB string `json:"company_b"`
}

// CompanyDeduplicateRequest is the request payload for POST /v1/company/deduplicate.
type CompanyDeduplicateRequest struct {
	Companies      []string `json:"companies"`
	Country        string   `json:"country,omitempty"`
	FuzzyThreshold float64  `json:"fuzzy_threshold,omitempty"`
}

// CompanyCluster represents a deduplicated Golden Company cluster.
type CompanyCluster struct {
	ClusterID     string                `json:"cluster_id"`
	GoldenCompany StandardizedCompany   `json:"golden_company"`
	Members       []StandardizedCompany `json:"members"`
	RawInputs     []string              `json:"raw_inputs"`
	MatchTypes    []string              `json:"match_types"`
}

// CompanyDeduplicateResponse represents the response payload from POST /v1/company/deduplicate.
type CompanyDeduplicateResponse struct {
	ClusterCount int              `json:"cluster_count"`
	Clusters     []CompanyCluster `json:"clusters"`
}

// PersonStandardizeRequest is the request payload for POST /v1/person.
type PersonStandardizeRequest struct {
	Name string `json:"name"`
}

// PersonCompareRequest is the request payload for POST /v1/person/compare.
type PersonCompareRequest struct {
	PersonA string `json:"person_a"`
	PersonB string `json:"person_b"`
}

// PersonDeduplicateRequest is the request payload for POST /v1/person/deduplicate.
type PersonDeduplicateRequest struct {
	Persons        []string `json:"persons"`
	FuzzyThreshold float64  `json:"fuzzy_threshold,omitempty"`
}

// PersonCluster represents a deduplicated Golden Person cluster.
type PersonCluster struct {
	ClusterID    string               `json:"cluster_id"`
	GoldenPerson StandardizedPerson   `json:"golden_person"`
	Members      []StandardizedPerson `json:"members"`
	RawInputs    []string             `json:"raw_inputs"`
	MatchTypes   []string             `json:"match_types"`
}

// PersonDeduplicateResponse represents the response payload from POST /v1/person/deduplicate.
type PersonDeduplicateResponse struct {
	ClusterCount int             `json:"cluster_count"`
	Clusters     []PersonCluster `json:"clusters"`
}

// JobTitleStandardizeRequest is the request payload for POST /v1/job-title.
type JobTitleStandardizeRequest struct {
	Title string `json:"title"`
}

// EmailStandardizeRequest is the request payload for POST /v1/email.
type EmailStandardizeRequest struct {
	Email string `json:"email"`
}

// EmailCompareRequest is the request payload for POST /v1/email/compare.
type EmailCompareRequest struct {
	EmailA string `json:"email_a"`
	EmailB string `json:"email_b"`
}

// EmailComparisonResult represents the response payload from POST /v1/email/compare.
type EmailComparisonResult struct {
	IsMatch   bool              `json:"is_match"`
	Score     float64           `json:"score"`
	MatchType string            `json:"match_type"`
	EmailA    StandardizedEmail `json:"email_a"`
	EmailB    StandardizedEmail `json:"email_b"`
}

// UrlStandardizeRequest is the request payload for POST /v1/url.
type UrlStandardizeRequest struct {
	URL string `json:"url"`
}

// UrlCompareRequest is the request payload for POST /v1/url/compare.
type UrlCompareRequest struct {
	URLA string `json:"url_a"`
	URLB string `json:"url_b"`
}

// UrlComparisonResult represents the response payload from POST /v1/url/compare.
type UrlComparisonResult struct {
	IsMatch   bool            `json:"is_match"`
	Score     float64         `json:"score"`
	MatchType string          `json:"match_type"`
	URLA      StandardizedUrl `json:"url_a"`
	URLB      StandardizedUrl `json:"url_b"`
}

// SocialStandardizeRequest is the request payload for POST /v1/social.
type SocialStandardizeRequest struct {
	Profile  string `json:"profile"`
	Platform string `json:"platform,omitempty"`
}

// ContactStandardizeRequest is the request payload for POST /v1/contact.
type ContactStandardizeRequest struct {
	Street1        string `json:"street1,omitempty"`
	Street2        string `json:"street2,omitempty"`
	City           string `json:"city,omitempty"`
	State          string `json:"state,omitempty"`
	PostalCode     string `json:"postal_code,omitempty"`
	Country        string `json:"country,omitempty"`
	Phone          string `json:"phone,omitempty"`
	Fax            string `json:"fax,omitempty"`
	Organization   string `json:"organization,omitempty"`
	PersonName     string `json:"person_name,omitempty"`
	JobTitle       string `json:"job_title,omitempty"`
	Email          string `json:"email,omitempty"`
	Website        string `json:"website,omitempty"`
	Social         string `json:"social,omitempty"`
	DefaultCountry string `json:"default_country,omitempty"`
}

// ContactCompareRequest is the request payload for POST /v1/contact/compare.
type ContactCompareRequest struct {
	ContactA       map[string]any `json:"contact_a"`
	ContactB       map[string]any `json:"contact_b"`
	DefaultCountry string         `json:"default_country,omitempty"`
}

// ContactClusterRequest is the request payload for POST /v1/contact/cluster.
type ContactClusterRequest struct {
	Records        []map[string]any `json:"records"`
	DefaultCountry string           `json:"default_country,omitempty"`
}

// ContactCluster represents a unified Golden Entity cluster returned by POST /v1/contact/cluster.
type ContactCluster struct {
	ClusterID        string            `json:"cluster_id"`
	GoldenPhone      StandardizedPhone `json:"golden_phone"`
	GoldenAddressKey *string           `json:"golden_address_key"`
	RecordIDs        []string          `json:"record_ids"`
	Records          []map[string]any  `json:"records"`
	LinkageReasons   []string          `json:"linkage_reasons"`
}

// ContactClusterResponse represents the response payload from POST /v1/contact/cluster.
type ContactClusterResponse struct {
	ClusterCount int              `json:"cluster_count"`
	Clusters     []ContactCluster `json:"clusters"`
}

// ContactBatchRequest is the request payload for POST /v1/contact/batch.
type ContactBatchRequest struct {
	Contacts       []map[string]any `json:"contacts"`
	DefaultCountry string           `json:"default_country,omitempty"`
}

// ContactBatchResponse represents the response payload from POST /v1/contact/batch.
type ContactBatchResponse struct {
	Count   int                   `json:"count"`
	Results []StandardizedContact `json:"results"`
}

// StandardizedAddress represents a normalized physical/postal address returned by POST /v1/address.
type StandardizedAddress struct {
	Street1              string  `json:"street1"`
	Street2              string  `json:"street2"`
	City                 string  `json:"city"`
	State                string  `json:"state"`
	PostalCode           string  `json:"postal_code"`
	Country              string  `json:"country"`
	NormalizedAddressKey *string `json:"normalized_address_key"`
	BuildingKey          *string `json:"building_key"`
	PhoneticKey          *string `json:"phonetic_key"`
	AddressStatus        string  `json:"address_status"`
	RawStreetAddress     string  `json:"raw_street_address"`
	IsUS                 bool    `json:"is_us"`
	IsPrivateResidence   bool    `json:"is_private_residence"`
	IsRegisteredAgentHub bool    `json:"is_registered_agent_hub"`
}

// StandardizedCompany represents a standardized organization or company name returned by POST /v1/company.
type StandardizedCompany struct {
	RawInput            string   `json:"raw_input"`
	LegalName           *string  `json:"legal_name"`
	BaseName            *string  `json:"base_name"`
	BrandStem           *string  `json:"brand_stem"`
	LegalSuffix         *string  `json:"legal_suffix"`
	DBAName             *string  `json:"dba_name"`
	FKAName             *string  `json:"fka_name"`
	BranchUnit          *string  `json:"branch_unit"`
	InferredCountryISO2 *string  `json:"inferred_country_iso2"`
	CompanyKey          *string  `json:"company_key"`
	BrandKey            *string  `json:"brand_key"`
	PhoneticKey         *string  `json:"phonetic_key"`
	IsValid             bool     `json:"is_valid"`
	Confidence          float64  `json:"confidence"`
	HealingActions      []string `json:"healing_actions"`
}

// CompanyComparisonResult represents the response payload from POST /v1/company/compare.
type CompanyComparisonResult struct {
	IsMatch   bool                `json:"is_match"`
	Score     float64             `json:"score"`
	MatchType string              `json:"match_type"`
	CompanyA  StandardizedCompany `json:"company_a"`
	CompanyB  StandardizedCompany `json:"company_b"`
}

// StandardizedPerson represents a standardized person full name returned by POST /v1/person.
type StandardizedPerson struct {
	RawInput           string   `json:"raw_input"`
	Salutation         *string  `json:"salutation"`
	FirstName          *string  `json:"first_name"`
	RootFirstName      *string  `json:"root_first_name"`
	MiddleName         *string  `json:"middle_name"`
	LastName           *string  `json:"last_name"`
	Nickname           *string  `json:"nickname"`
	GenerationalSuffix *string  `json:"generational_suffix"`
	Credentials        []string `json:"credentials"`
	FullName           *string  `json:"full_name"`
	PersonKey          *string  `json:"person_key"`
	PersonRootKey      *string  `json:"person_root_key"`
	PhoneticKey        *string  `json:"phonetic_key"`
	IsOrganization     bool     `json:"is_organization"`
	IsValid            bool     `json:"is_valid"`
	Confidence         float64  `json:"confidence"`
	HealingActions     []string `json:"healing_actions"`
}

// PersonComparisonResult represents the response payload from POST /v1/person/compare.
type PersonComparisonResult struct {
	IsMatch   bool               `json:"is_match"`
	Score     float64            `json:"score"`
	MatchType string             `json:"match_type"`
	PersonA   StandardizedPerson `json:"person_a"`
	PersonB   StandardizedPerson `json:"person_b"`
}

// StandardizedJobTitle represents a standardized job title.
type StandardizedJobTitle struct {
	RawInput        string   `json:"raw_input"`
	NormalizedTitle *string  `json:"normalized_title"`
	SeniorityLevel  *string  `json:"seniority_level"`
	Department      *string  `json:"department"`
	IsExecutive     bool     `json:"is_executive"`
	IsValid         bool     `json:"is_valid"`
	Confidence      float64  `json:"confidence"`
	HealingActions  []string `json:"healing_actions"`
}

// StandardizedEmail represents a standardized email address returned by POST /v1/email.
type StandardizedEmail struct {
	RawInput            string   `json:"raw_input"`
	Email               *string  `json:"email"`
	LocalPart           *string  `json:"local_part"`
	RawLocalPart        *string  `json:"raw_local_part"`
	Subaddress          *string  `json:"subaddress"`
	Domain              *string  `json:"domain"`
	DisplayName         *string  `json:"display_name"`
	EmailType           *string  `json:"email_type"`
	IsFreeProvider      bool     `json:"is_free_provider"`
	IsRoleAccount       bool     `json:"is_role_account"`
	IsDisposable        bool     `json:"is_disposable"`
	InferredCountryISO2 *string  `json:"inferred_country_iso2"`
	EmailKey            *string  `json:"email_key"`
	IsValid             bool     `json:"is_valid"`
	Confidence          float64  `json:"confidence"`
	HealingActions      []string `json:"healing_actions"`
}

// StandardizedUrl represents a standardized website URL returned by POST /v1/url.
type StandardizedUrl struct {
	RawInput            string   `json:"raw_input"`
	URL                 *string  `json:"url"`
	Scheme              *string  `json:"scheme"`
	Host                *string  `json:"host"`
	Domain              *string  `json:"domain"`
	Subdomain           *string  `json:"subdomain"`
	PublicSuffix        *string  `json:"public_suffix"`
	BrandStem           *string  `json:"brand_stem"`
	Path                *string  `json:"path"`
	InferredCountryISO2 *string  `json:"inferred_country_iso2"`
	URLKey              *string  `json:"url_key"`
	IsValid             bool     `json:"is_valid"`
	Confidence          float64  `json:"confidence"`
	HealingActions      []string `json:"healing_actions"`
}

// StandardizedSocial represents a standardized social media profile returned by POST /v1/social.
type StandardizedSocial struct {
	RawInput       string   `json:"raw_input"`
	Platform       *string  `json:"platform"`
	ProfileType    *string  `json:"profile_type"`
	Handle         *string  `json:"handle"`
	URL            *string  `json:"url"`
	SocialKey      *string  `json:"social_key"`
	IsValid        bool     `json:"is_valid"`
	Confidence     float64  `json:"confidence"`
	HealingActions []string `json:"healing_actions"`
}

// StandardizedContact represents a unified cross-healed entity contact from POST /v1/contact.
type StandardizedContact struct {
	Address             StandardizedAddress   `json:"address"`
	Phone               StandardizedPhone     `json:"phone"`
	Fax                 *StandardizedPhone    `json:"fax"`
	Organization        *StandardizedCompany  `json:"organization"`
	Person              *StandardizedPerson   `json:"person"`
	AdditionalPersons   []StandardizedPerson  `json:"additional_persons"`
	JobTitle            *StandardizedJobTitle `json:"job_title"`
	Email               *StandardizedEmail    `json:"email"`
	Website             *StandardizedUrl      `json:"website"`
	Social              *StandardizedSocial   `json:"social"`
	EntityKey           *string               `json:"entity_key"`
	CrossHealingActions []string              `json:"cross_healing_actions"`
	OverallConfidence   float64               `json:"overall_confidence"`
}

// ContactComparisonResult represents the response payload from POST /v1/contact/compare.
type ContactComparisonResult struct {
	IsMatch        bool                `json:"is_match"`
	Score          float64             `json:"score"`
	MatchType      string              `json:"match_type"`
	MatchedPillars []string            `json:"matched_pillars"`
	PillarScores   map[string]float64  `json:"pillar_scores"`
	ContactA       StandardizedContact `json:"contact_a"`
	ContactB       StandardizedContact `json:"contact_b"`
}
