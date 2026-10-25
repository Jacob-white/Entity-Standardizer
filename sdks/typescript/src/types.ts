/**
 * Public TypeScript interfaces for Entity & Phone Standardizer Client & React SDK.
 */

export type PhoneLineType =
  | "MOBILE"
  | "FIXED_LINE"
  | "FIXED_LINE_OR_MOBILE"
  | "TOLL_FREE"
  | "PREMIUM_RATE"
  | "SHARED_COST"
  | "VOIP"
  | "PERSONAL_NUMBER"
  | "PAGER"
  | "UAN"
  | "VOICEMAIL"
  | "SHORT_CODE"
  | "EMERGENCY"
  | "UNKNOWN";

export type PhoneRoutingTier = "AUTO_PASS" | "FUZZY_REVIEW" | "MANUAL_STEWARDSHIP";

export interface PhoneStandardizeRequest {
  phone: string;
  country?: string | null;
  default_country?: string;
}

export interface PhoneBatchRequest {
  phones: string[];
  default_country?: string;
}

export interface PhoneCompareRequest {
  phone_a: string;
  phone_b: string;
  country?: string | null;
  fuzzy_threshold?: number;
}

export interface PhoneDeduplicateRequest {
  phones: string[];
  country?: string | null;
  fuzzy_threshold?: number;
}

export interface AddressStandardizeRequest {
  street1?: string | null;
  street2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string;
}

export interface CompanyStandardizeRequest {
  name: string;
  country?: string | null;
}

export interface PersonStandardizeRequest {
  name: string;
}

export interface EmailStandardizeRequest {
  email: string;
}

export interface UrlStandardizeRequest {
  url: string;
}

export interface SocialStandardizeRequest {
  profile: string;
  platform?: string | null;
}

export interface ContactStandardizeRequest {
  street1?: string | null;
  street2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  phone?: string | null;
  fax?: string | null;
  organization?: string | null;
  person_name?: string | null;
  job_title?: string | null;
  email?: string | null;
  website?: string | null;
  social?: string | null;
  default_country?: string;
}

export interface StandardizedAddress {
  street1: string;
  street2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  normalized_address_key: string | null;
  building_key: string | null;
  phonetic_key: string | null;
  address_status: string;
  raw_street_address: string;
  is_us: boolean;
  is_private_residence: boolean;
  is_registered_agent_hub: boolean;
}

export interface StandardizedCompany {
  raw_input: string;
  legal_name: string | null;
  base_name: string | null;
  brand_stem: string | null;
  legal_suffix: string | null;
  dba_name: string | null;
  fka_name: string | null;
  branch_unit: string | null;
  inferred_country_iso2: string | null;
  company_key: string | null;
  brand_key: string | null;
  phonetic_key: string | null;
  is_valid: boolean;
  confidence: number;
  healing_actions: string[];
}

export interface StandardizedPerson {
  raw_input: string;
  salutation: string | null;
  first_name: string | null;
  root_first_name: string | null;
  middle_name: string | null;
  last_name: string | null;
  nickname: string | null;
  generational_suffix: string | null;
  credentials: string[];
  full_name: string | null;
  person_key: string | null;
  person_root_key: string | null;
  phonetic_key: string | null;
  is_organization: boolean;
  is_valid: boolean;
  confidence: number;
  healing_actions: string[];
}

export interface StandardizedJobTitle {
  raw_input: string;
  normalized_title: string | null;
  seniority_level: string | null;
  department: string | null;
  is_executive: boolean;
  is_valid: boolean;
  confidence: number;
  healing_actions: string[];
}

export interface StandardizedEmail {
  raw_input: string;
  email: string | null;
  local_part: string | null;
  raw_local_part: string | null;
  subaddress: string | null;
  domain: string | null;
  display_name: string | null;
  email_type: string | null;
  is_free_provider: boolean;
  is_role_account: boolean;
  is_disposable: boolean;
  inferred_country_iso2: string | null;
  email_key: string | null;
  is_valid: boolean;
  confidence: number;
  healing_actions: string[];
}

export interface StandardizedUrl {
  raw_input: string;
  url: string | null;
  scheme: string | null;
  host: string | null;
  domain: string | null;
  subdomain: string | null;
  public_suffix: string | null;
  brand_stem: string | null;
  path: string | null;
  inferred_country_iso2: string | null;
  url_key: string | null;
  is_valid: boolean;
  confidence: number;
  healing_actions: string[];
}

export interface StandardizedSocial {
  raw_input: string;
  platform: string | null;
  profile_type: string | null;
  handle: string | null;
  url: string | null;
  social_key: string | null;
  is_valid: boolean;
  confidence: number;
  healing_actions: string[];
}

export interface StandardizedContact {
  address: StandardizedAddress;
  phone: StandardizedPhone;
  fax: StandardizedPhone | null;
  organization: StandardizedCompany | null;
  person: StandardizedPerson | null;
  job_title: StandardizedJobTitle | null;
  email: StandardizedEmail | null;
  website: StandardizedUrl | null;
  social: StandardizedSocial | null;
  entity_key: string | null;
  cross_healing_actions: string[];
  overall_confidence: number;
}

export interface StandardizedPhone {
  raw_input: string;
  e164: string | null;
  national: string | null;
  international: string | null;
  rfc3966: string | null;
  country_calling_code: string | null;
  country_iso2: string | null;
  country_iso3: string | null;
  country_name: string | null;
  national_significant_number: string | null;
  area_code: string | null;
  subscriber_number: string | null;
  extension: string | null;
  vanity_alias: string | null;
  region_code: string | null;
  line_type: PhoneLineType;
  is_valid: boolean;
  is_possible: boolean;
  phone_key: string | null;
  phone_ext_key: string | null;
  confidence: number;
  routing_tier: PhoneRoutingTier;
  risk_flags: string[];
  healing_actions: string[];
}

export interface PhoneComparisonResult {
  phone_a: StandardizedPhone;
  phone_b: StandardizedPhone;
  is_exact_match: boolean;
  is_extension_variant: boolean;
  is_fuzzy_match: boolean;
  similarity_score: number;
  match_type: string;
  edit_distance: number;
  transposition_detected: boolean;
  keypad_adjacent_typo: boolean;
  explanation: string;
}

export interface PhoneCluster {
  cluster_id: string;
  golden_phone: StandardizedPhone;
  members: StandardizedPhone[];
  raw_inputs: string[];
  match_types: string[];
}

export interface PhoneIntelligence {
  locality: string | null;
  timezones: string[];
  carrier_hint: string | null;
  is_callable_now: boolean;
  local_hours: number[];
}

export interface PhoneExplanation {
  healing_steps_count: number;
  healing_actions: string[];
  risk_flags_count: number;
  risk_flags: string[];
  confidence: number;
  routing_tier: PhoneRoutingTier;
  requires_human_review: boolean;
}

export interface PhoneExplainReport {
  record: StandardizedPhone;
  intelligence: PhoneIntelligence;
  explanation: PhoneExplanation;
}

export interface CountryDialPlan {
  iso2: string;
  iso3: string;
  numeric: string;
  name: string;
  calling_code: string;
  idd_prefix: string;
  national_trunk_prefix: string | null;
  nsn_lengths: number[];
  mobile_prefixes: string[];
  toll_free_prefixes: string[];
  premium_prefixes: string[];
  voip_prefixes: string[];
  shared_cost_prefixes: string[];
  region: string;
}
