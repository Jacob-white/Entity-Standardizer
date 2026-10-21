/**
 * Headless React <PhoneInput /> Controller & Hook for Phone Standardizer.
 */

import { formatAsYouType, PhoneStandardizerClient } from "./client.js";
import { StandardizedPhone } from "./types.js";

export interface UsePhoneInputOptions {
  client?: PhoneStandardizerClient;
  defaultCountry?: string;
  initialValue?: string;
  onStandardized?: (record: StandardizedPhone) => void;
}

export class PhoneInputController {
  public rawValue: string;
  public formattedValue: string;
  public country: string;
  public record: StandardizedPhone | null = null;
  public isValidating: boolean = false;
  public error: Error | null = null;

  private readonly client: PhoneStandardizerClient;
  private readonly onStandardized?: (record: StandardizedPhone) => void;
  private readonly listeners: Set<() => void> = new Set();

  constructor(options: UsePhoneInputOptions = {}) {
    this.client = options.client ?? new PhoneStandardizerClient();
    this.country = options.defaultCountry ?? "US";
    this.rawValue = options.initialValue ?? "";
    this.formattedValue = formatAsYouType(this.rawValue, this.country);
    this.onStandardized = options.onStandardized;
  }

  public subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }

  public setCountry(countryIso2: string): void {
    this.country = countryIso2.toUpperCase();
    this.formattedValue = formatAsYouType(this.rawValue, this.country);
    this.notify();
  }

  public setValue(nextRaw: string): void {
    this.rawValue = nextRaw;
    this.formattedValue = formatAsYouType(nextRaw, this.country);
    this.error = null;
    this.notify();
  }

  public async validate(): Promise<StandardizedPhone | null> {
    if (!this.rawValue.trim()) {
      this.record = null;
      this.notify();
      return null;
    }
    this.isValidating = true;
    this.error = null;
    this.notify();
    try {
      const res = await this.client.standardize({
        phone: this.rawValue,
        country: this.country,
        default_country: this.country,
      });
      this.record = res;
      if (res.is_valid && res.national) {
        this.formattedValue = res.national;
      }
      this.isValidating = false;
      this.notify();
      if (this.onStandardized) {
        this.onStandardized(res);
      }
      return res;
    } catch (err: unknown) {
      this.error = err instanceof Error ? err : new Error(String(err));
      this.isValidating = false;
      this.notify();
      return null;
    }
  }
}
