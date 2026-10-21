/**
 * Public TypeScript interfaces for Phone Standardizer Client & React SDK.
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
