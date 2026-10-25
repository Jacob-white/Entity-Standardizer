/**
 * Headless React <PhoneInput /> Controller & Hook for Phone Standardizer.
 */

import { EntityStandardizerClient, formatAsYouType } from "./client.js";
import { StandardizedPhone } from "./types.js";

export interface ReactLike {
  useState<T>(initial: T | (() => T)): [T, (next: T | ((prev: T) => T)) => void];
  useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
  useRef<T>(initial: T): { current: T };
  useCallback<T extends (...args: never[]) => unknown>(fn: T, deps: readonly unknown[]): T;
}

export interface UsePhoneInputOptions {
  client?: EntityStandardizerClient;
  defaultCountry?: string;
  initialValue?: string;
  onStandardized?: (record: StandardizedPhone) => void;
  react?: ReactLike;
}

export interface UsePhoneInputResult {
  rawValue: string;
  formattedValue: string;
  country: string;
  record: StandardizedPhone | null;
  isValidating: boolean;
  error: Error | null;
  setValue: (nextRaw: string) => void;
  setCountry: (countryIso2: string) => void;
  validate: () => Promise<StandardizedPhone | null>;
  controller: PhoneInputController;
}

export class PhoneInputController {
  public rawValue: string;
  public formattedValue: string;
  public country: string;
  public record: StandardizedPhone | null = null;
  public isValidating: boolean = false;
  public error: Error | null = null;

  private readonly client: EntityStandardizerClient;
  private readonly onStandardized?: (record: StandardizedPhone) => void;
  private readonly listeners: Set<() => void> = new Set();
  private requestId: number = 0;
  private abortController: AbortController | null = null;

  constructor(options: UsePhoneInputOptions = {}) {
    this.client = options.client ?? new EntityStandardizerClient();
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

  private cancelInFlight(): void {
    this.requestId += 1;
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    this.isValidating = false;
  }

  public setCountry(countryIso2: string): void {
    this.cancelInFlight();
    this.country = countryIso2.toUpperCase();
    this.formattedValue = formatAsYouType(this.rawValue, this.country);
    this.notify();
  }

  public setValue(nextRaw: string): void {
    this.cancelInFlight();
    this.rawValue = nextRaw;
    this.formattedValue = formatAsYouType(nextRaw, this.country);
    this.error = null;
    this.notify();
  }

  public async validate(): Promise<StandardizedPhone | null> {
    if (!this.rawValue.trim()) {
      this.cancelInFlight();
      this.record = null;
      this.notify();
      return null;
    }
    if (this.abortController) {
      this.abortController.abort();
    }
    const currentRequestId = ++this.requestId;
    const ac = new AbortController();
    this.abortController = ac;
    this.isValidating = true;
    this.error = null;
    this.notify();
    try {
      const res = await this.client.standardize(
        {
          phone: this.rawValue,
          country: this.country,
          default_country: this.country,
        },
        { signal: ac.signal }
      );
      if (currentRequestId !== this.requestId) {
        return null;
      }
      this.record = res;
      if (res.is_valid && res.national) {
        this.formattedValue = res.national;
      }
      this.isValidating = false;
      this.abortController = null;
      this.notify();
      if (this.onStandardized) {
        this.onStandardized(res);
      }
      return res;
    } catch (err: unknown) {
      if (currentRequestId !== this.requestId) {
        return null;
      }
      this.error = err instanceof Error ? err : new Error(String(err));
      this.isValidating = false;
      this.abortController = null;
      this.notify();
      return null;
    }
  }
}

/**
 * Headless React hook for progressive phone formatting, country switching, and async E.164 standardization.
 */
export function usePhoneInput(options: UsePhoneInputOptions = {}): UsePhoneInputResult {
  const ReactImpl =
    options.react ??
    ((globalThis as unknown as { React?: ReactLike }).React as ReactLike | undefined);
  if (!ReactImpl) {
    throw new Error(
      "usePhoneInput requires a React instance via options.react or globalThis.React"
    );
  }

  const controllerRef = ReactImpl.useRef<PhoneInputController | null>(null);
  if (!controllerRef.current) {
    controllerRef.current = new PhoneInputController(options);
  }
  const controller = controllerRef.current;

  const [, setTick] = ReactImpl.useState(0);

  ReactImpl.useEffect(() => {
    return controller.subscribe(() => {
      setTick((t) => t + 1);
    });
  }, [controller]);

  const setValue = ReactImpl.useCallback(
    (nextRaw: string) => {
      controller.setValue(nextRaw);
    },
    [controller]
  );

  const setCountry = ReactImpl.useCallback(
    (countryIso2: string) => {
      controller.setCountry(countryIso2);
    },
    [controller]
  );

  const validate = ReactImpl.useCallback(() => {
    return controller.validate();
  }, [controller]);

  return {
    rawValue: controller.rawValue,
    formattedValue: controller.formattedValue,
    country: controller.country,
    record: controller.record,
    isValidating: controller.isValidating,
    error: controller.error,
    setValue,
    setCountry,
    validate,
    controller,
  };
}
