/**
 * Typed HTTP Client & Offline As-You-Type Formatter for Entity & Phone Standardizer.
 */

import {
  AddressAutocompleteRequest,
  AddressCluster,
  AddressCompareRequest,
  AddressComparisonResult,
  AddressDeduplicateRequest,
  AddressStandardizeRequest,
  AutocompleteSuggestion,
  CompanyCluster,
  CompanyCompareRequest,
  CompanyComparisonResult,
  CompanyDeduplicateRequest,
  CompanyStandardizeRequest,
  ContactBatchRequest,
  ContactCluster,
  ContactClusterRequest,
  ContactCompareRequest,
  ContactComparisonResult,
  ContactStandardizeRequest,
  CountryDialPlan,
  EmailCompareRequest,
  EmailComparisonResult,
  EmailStandardizeRequest,
  JobTitleStandardizeRequest,
  PersonCluster,
  PersonCompareRequest,
  PersonComparisonResult,
  PersonDeduplicateRequest,
  PersonStandardizeRequest,
  PhoneBatchRequest,
  PhoneCluster,
  PhoneCompareRequest,
  PhoneComparisonResult,
  PhoneDeduplicateRequest,
  PhoneExplainReport,
  PhoneStandardizeRequest,
  ReadyResponse,
  SocialStandardizeRequest,
  StandardizedAddress,
  StandardizedCompany,
  StandardizedContact,
  StandardizedEmail,
  StandardizedJobTitle,
  StandardizedPerson,
  StandardizedPhone,
  StandardizedSocial,
  StandardizedUrl,
  UrlCompareRequest,
  UrlComparisonResult,
  UrlStandardizeRequest,
} from "./types.js";

export interface ClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  headers?: Record<string, string>;
}

export interface RequestOptions {
  signal?: AbortSignal;
}

/**
 * Instant client-side as-you-type national/international formatter for responsive UI inputs.
 */
export function formatAsYouType(raw: string, countryIso2: string = "US"): string {
  const trimmed = raw.trim();
  const hasPlus = trimmed.startsWith("+");
  const digits = trimmed.replace(/\D+/g, "");
  if (!digits) return hasPlus ? "+" : "";

  if (!hasPlus && (countryIso2 === "US" || countryIso2 === "CA" || countryIso2 === "PR")) {
    const clean = digits.length === 11 && digits.startsWith("1") ? digits.slice(1) : digits;
    if (clean.length <= 3) return `(${clean}`;
    if (clean.length <= 6) return `(${clean.slice(0, 3)}) ${clean.slice(3)}`;
    return `(${clean.slice(0, 3)}) ${clean.slice(3, 6)}-${clean.slice(6, 10)}`;
  }

  if (hasPlus && digits.startsWith("1") && digits.length <= 11) {
    const nsn = digits.slice(1);
    if (!nsn) return "+1";
    if (nsn.length <= 3) return `+1 (${nsn}`;
    if (nsn.length <= 6) return `+1 (${nsn.slice(0, 3)}) ${nsn.slice(3)}`;
    return `+1 (${nsn.slice(0, 3)}) ${nsn.slice(3, 6)}-${nsn.slice(6, 10)}`;
  }

  return hasPlus ? `+${digits}` : digits;
}

export class EntityStandardizerClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly headers: Record<string, string>;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;
    this.headers = {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    };
  }

  async health(options?: RequestOptions): Promise<{ status: string; version: string }> {
    const res = await this.fetchImpl(`${this.baseUrl}/health`, {
      method: "GET",
      headers: this.headers,
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Health check failed with status ${res.status}`);
    }
    return (await res.json()) as { status: string; version: string };
  }

  async ready(options?: RequestOptions): Promise<ReadyResponse> {
    const res = await this.fetchImpl(`${this.baseUrl}/ready`, {
      method: "GET",
      headers: this.headers,
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Ready check failed with status ${res.status}`);
    }
    return (await res.json()) as ReadyResponse;
  }

  async standardize(
    req: PhoneStandardizeRequest,
    options?: RequestOptions
  ): Promise<StandardizedPhone> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/standardize`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Standardize failed with status ${res.status}`);
    }
    return (await res.json()) as StandardizedPhone;
  }

  async explain(
    req: PhoneStandardizeRequest,
    options?: RequestOptions
  ): Promise<PhoneExplainReport> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/explain`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Explain failed with status ${res.status}`);
    }
    return (await res.json()) as PhoneExplainReport;
  }

  async compare(
    req: PhoneCompareRequest,
    options?: RequestOptions
  ): Promise<PhoneComparisonResult> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/compare`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Compare failed with status ${res.status}`);
    }
    return (await res.json()) as PhoneComparisonResult;
  }

  async deduplicate(
    req: PhoneDeduplicateRequest,
    options?: RequestOptions
  ): Promise<{ cluster_count: number; clusters: PhoneCluster[] }> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/deduplicate`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Deduplicate failed with status ${res.status}`);
    }
    return (await res.json()) as { cluster_count: number; clusters: PhoneCluster[] };
  }

  async batch(
    req: PhoneBatchRequest,
    options?: RequestOptions
  ): Promise<{ count: number; results: StandardizedPhone[] }> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/batch`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Batch failed with status ${res.status}`);
    }
    return (await res.json()) as { count: number; results: StandardizedPhone[] };
  }

  async getCountry(identifier: string, options?: RequestOptions): Promise<CountryDialPlan> {
    const res = await this.fetchImpl(
      `${this.baseUrl}/v1/countries/${encodeURIComponent(identifier)}`,
      {
        method: "GET",
        headers: this.headers,
        signal: options?.signal,
      }
    );
    if (!res.ok) {
      throw new Error(`Country lookup failed with status ${res.status}`);
    }
    return (await res.json()) as CountryDialPlan;
  }

  async listCountries(
    options?: RequestOptions
  ): Promise<{ count: number; countries: CountryDialPlan[] }> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/countries`, {
      method: "GET",
      headers: this.headers,
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`List countries failed with status ${res.status}`);
    }
    return (await res.json()) as { count: number; countries: CountryDialPlan[] };
  }

  async standardizeAddress(
    req: AddressStandardizeRequest,
    options?: RequestOptions
  ): Promise<StandardizedAddress> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/address`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Standardize address failed with status ${res.status}`);
    }
    return (await res.json()) as StandardizedAddress;
  }

  async compareAddresses(
    req: AddressCompareRequest,
    options?: RequestOptions
  ): Promise<AddressComparisonResult> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/address/compare`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Compare addresses failed with status ${res.status}`);
    }
    return (await res.json()) as AddressComparisonResult;
  }

  async deduplicateAddresses(
    req: AddressDeduplicateRequest,
    options?: RequestOptions
  ): Promise<{ cluster_count: number; clusters: AddressCluster[] }> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/address/deduplicate`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Deduplicate addresses failed with status ${res.status}`);
    }
    return (await res.json()) as { cluster_count: number; clusters: AddressCluster[] };
  }

  async autocompleteAddress(
    req: AddressAutocompleteRequest,
    options?: RequestOptions
  ): Promise<{ count: number; suggestions: AutocompleteSuggestion[] }> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/address/autocomplete`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Autocomplete address failed with status ${res.status}`);
    }
    return (await res.json()) as { count: number; suggestions: AutocompleteSuggestion[] };
  }

  async standardizeCompany(
    req: CompanyStandardizeRequest,
    options?: RequestOptions
  ): Promise<StandardizedCompany> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/company`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Standardize company failed with status ${res.status}`);
    }
    return (await res.json()) as StandardizedCompany;
  }

  async compareCompanies(
    req: CompanyCompareRequest,
    options?: RequestOptions
  ): Promise<CompanyComparisonResult> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/company/compare`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Compare companies failed with status ${res.status}`);
    }
    return (await res.json()) as CompanyComparisonResult;
  }

  async deduplicateCompanies(
    req: CompanyDeduplicateRequest,
    options?: RequestOptions
  ): Promise<{ cluster_count: number; clusters: CompanyCluster[] }> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/company/deduplicate`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Deduplicate companies failed with status ${res.status}`);
    }
    return (await res.json()) as { cluster_count: number; clusters: CompanyCluster[] };
  }

  async standardizePerson(
    req: PersonStandardizeRequest,
    options?: RequestOptions
  ): Promise<StandardizedPerson> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/person`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Standardize person failed with status ${res.status}`);
    }
    return (await res.json()) as StandardizedPerson;
  }

  async comparePersons(
    req: PersonCompareRequest,
    options?: RequestOptions
  ): Promise<PersonComparisonResult> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/person/compare`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Compare persons failed with status ${res.status}`);
    }
    return (await res.json()) as PersonComparisonResult;
  }

  async deduplicatePersons(
    req: PersonDeduplicateRequest,
    options?: RequestOptions
  ): Promise<{ cluster_count: number; clusters: PersonCluster[] }> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/person/deduplicate`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Deduplicate persons failed with status ${res.status}`);
    }
    return (await res.json()) as { cluster_count: number; clusters: PersonCluster[] };
  }

  async standardizeJobTitle(
    req: JobTitleStandardizeRequest,
    options?: RequestOptions
  ): Promise<StandardizedJobTitle> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/job-title`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Standardize job title failed with status ${res.status}`);
    }
    return (await res.json()) as StandardizedJobTitle;
  }

  async standardizeEmail(
    req: EmailStandardizeRequest,
    options?: RequestOptions
  ): Promise<StandardizedEmail> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/email`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Standardize email failed with status ${res.status}`);
    }
    return (await res.json()) as StandardizedEmail;
  }

  async compareEmails(
    req: EmailCompareRequest,
    options?: RequestOptions
  ): Promise<EmailComparisonResult> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/email/compare`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Compare emails failed with status ${res.status}`);
    }
    return (await res.json()) as EmailComparisonResult;
  }

  async standardizeUrl(
    req: UrlStandardizeRequest,
    options?: RequestOptions
  ): Promise<StandardizedUrl> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/url`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Standardize url failed with status ${res.status}`);
    }
    return (await res.json()) as StandardizedUrl;
  }

  async compareUrls(
    req: UrlCompareRequest,
    options?: RequestOptions
  ): Promise<UrlComparisonResult> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/url/compare`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Compare urls failed with status ${res.status}`);
    }
    return (await res.json()) as UrlComparisonResult;
  }

  async standardizeSocial(
    req: SocialStandardizeRequest,
    options?: RequestOptions
  ): Promise<StandardizedSocial> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/social`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Standardize social failed with status ${res.status}`);
    }
    return (await res.json()) as StandardizedSocial;
  }

  async standardizeContact(
    req: ContactStandardizeRequest,
    options?: RequestOptions
  ): Promise<StandardizedContact> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/contact`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Standardize contact failed with status ${res.status}`);
    }
    return (await res.json()) as StandardizedContact;
  }

  async compareContacts(
    req: ContactCompareRequest,
    options?: RequestOptions
  ): Promise<ContactComparisonResult> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/contact/compare`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Compare contacts failed with status ${res.status}`);
    }
    return (await res.json()) as ContactComparisonResult;
  }

  async clusterContacts(
    req: ContactClusterRequest,
    options?: RequestOptions
  ): Promise<{ cluster_count: number; clusters: ContactCluster[] }> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/contact/cluster`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Cluster contacts failed with status ${res.status}`);
    }
    return (await res.json()) as { cluster_count: number; clusters: ContactCluster[] };
  }

  async batchStandardizeContacts(
    req: ContactBatchRequest,
    options?: RequestOptions
  ): Promise<{ count: number; results: StandardizedContact[] }> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/contact/batch`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
      signal: options?.signal,
    });
    if (!res.ok) {
      throw new Error(`Batch standardize contacts failed with status ${res.status}`);
    }
    return (await res.json()) as { count: number; results: StandardizedContact[] };
  }
}

export { EntityStandardizerClient as PhoneStandardizerClient };

