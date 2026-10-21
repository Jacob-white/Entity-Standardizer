/**
 * Typed HTTP Client & Offline As-You-Type Formatter for Phone Standardizer.
 */

import {
  CountryDialPlan,
  PhoneBatchRequest,
  PhoneStandardizeRequest,
  StandardizedPhone,
} from "./types.js";

export interface ClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  headers?: Record<string, string>;
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

  async health(): Promise<{ status: string; version: string }> {
    const res = await this.fetchImpl(`${this.baseUrl}/health`, {
      method: "GET",
      headers: this.headers,
    });
    if (!res.ok) {
      throw new Error(`Health check failed with status ${res.status}`);
    }
    return (await res.json()) as { status: string; version: string };
  }

  async standardize(req: PhoneStandardizeRequest): Promise<StandardizedPhone> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/standardize`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
    });
    if (!res.ok) {
      throw new Error(`Standardize failed with status ${res.status}`);
    }
    return (await res.json()) as StandardizedPhone;
  }

  async batch(
    req: PhoneBatchRequest
  ): Promise<{ count: number; results: StandardizedPhone[] }> {
    const res = await this.fetchImpl(`${this.baseUrl}/v1/batch`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(req),
    });
    if (!res.ok) {
      throw new Error(`Batch failed with status ${res.status}`);
    }
    return (await res.json()) as { count: number; results: StandardizedPhone[] };
  }

  async getCountry(identifier: string): Promise<CountryDialPlan> {
    const res = await this.fetchImpl(
      `${this.baseUrl}/v1/countries/${encodeURIComponent(identifier)}`,
      {
        method: "GET",
        headers: this.headers,
      }
    );
    if (!res.ok) {
      throw new Error(`Country lookup failed with status ${res.status}`);
    }
    return (await res.json()) as CountryDialPlan;
  }
}
