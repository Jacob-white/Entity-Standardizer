/**
 * Typed HTTP Client & Offline As-You-Type Formatter for Entity & Phone Standardizer.
 */

import {
  AddressStandardizeRequest,
  CompanyStandardizeRequest,
  ContactStandardizeRequest,
  CountryDialPlan,
  EmailStandardizeRequest,
  PersonStandardizeRequest,
  PhoneBatchRequest,
  PhoneCluster,
  PhoneCompareRequest,
  PhoneComparisonResult,
  PhoneDeduplicateRequest,
  PhoneExplainReport,
  PhoneStandardizeRequest,
  SocialStandardizeRequest,
  StandardizedAddress,
  StandardizedCompany,
  StandardizedContact,
  StandardizedEmail,
  StandardizedPerson,
  StandardizedPhone,
  StandardizedSocial,
  StandardizedUrl,
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

export class PhoneStandardizerClient {
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
}
