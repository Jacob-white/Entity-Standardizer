import assert from "node:assert/strict";
import test from "node:test";
import {
  formatAsYouType,
  PhoneInputController,
  PhoneStandardizerClient,
  usePhoneInput,
} from "../dist/index.js";

test("formatAsYouType formats US and international numbers progressively", () => {
  assert.equal(formatAsYouType(""), "");
  assert.equal(formatAsYouType("+"), "+");
  assert.equal(formatAsYouType("415", "US"), "(415");
  assert.equal(formatAsYouType("415555", "US"), "(415) 555");
  assert.equal(formatAsYouType("4155552671", "US"), "(415) 555-2671");
  assert.equal(formatAsYouType("+14155552671", "US"), "+1 (415) 555-2671");
  assert.equal(formatAsYouType("+44 20 7946 0912", "GB"), "+442079460912");
});

test("PhoneStandardizerClient and PhoneInputController interact with API", async () => {
  const mockFetch = async (url, init) => {
    const u = String(url);
    if (u.endsWith("/health")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ status: "ok", version: "1.3.0" }),
      };
    }
    if (u.endsWith("/v1/standardize")) {
      const body = JSON.parse(init.body);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          raw_input: body.phone,
          e164: "+14155552671",
          national: "(415) 555-2671",
          international: "+1 415-555-2671",
          rfc3966: "tel:+1-415-555-2671",
          country_calling_code: "1",
          country_iso2: "US",
          country_iso3: "USA",
          country_name: "United States",
          national_significant_number: "4155552671",
          area_code: "415",
          subscriber_number: "5552671",
          extension: null,
          vanity_alias: null,
          region_code: "CA",
          line_type: "FIXED_LINE_OR_MOBILE",
          is_valid: true,
          is_possible: true,
          phone_key: "+14155552671",
          phone_ext_key: "+14155552671",
          confidence: 1.0,
          routing_tier: "AUTO_PASS",
          risk_flags: [],
          healing_actions: [],
        }),
      };
    }
    if (u.endsWith("/v1/explain")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          record: { e164: "+14155552671", is_valid: true },
          intelligence: {
            locality: "San Francisco",
            timezones: ["America/Los_Angeles"],
            carrier_hint: null,
            is_callable_now: true,
            local_hours: [10],
          },
          explanation: {
            healing_steps_count: 0,
            healing_actions: [],
            risk_flags_count: 0,
            risk_flags: [],
            confidence: 1.0,
            routing_tier: "AUTO_PASS",
            requires_human_review: false,
          },
        }),
      };
    }
    if (u.endsWith("/v1/compare")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          is_exact_match: true,
          is_extension_variant: false,
          is_fuzzy_match: true,
          similarity_score: 1.0,
          match_type: "EXACT_MATCH",
          edit_distance: 0,
          transposition_detected: false,
          keypad_adjacent_typo: false,
          explanation: "Exact canonical E.164 match (+14155552671).",
        }),
      };
    }
    if (u.endsWith("/v1/deduplicate")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          cluster_count: 1,
          clusters: [
            {
              cluster_id: "PHONE-CLUSTER-0001",
              golden_phone: { e164: "+14155552671" },
              members: [],
              raw_inputs: ["415-555-2671", "+14155552671"],
              match_types: ["EXACT_MATCH"],
            },
          ],
        }),
      };
    }
    if (u.endsWith("/v1/batch")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ count: 1, results: [] }),
      };
    }
    if (u.endsWith("/v1/countries")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          count: 249,
          countries: [{ iso2: "US", calling_code: "1" }],
        }),
      };
    }
    if (u.includes("/v1/countries/")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          iso2: "US",
          iso3: "USA",
          numeric: "840",
          name: "United States",
          calling_code: "1",
        }),
      };
    }
    return { ok: false, status: 404, json: async () => ({}) };
  };

  const client = new PhoneStandardizerClient({
    baseUrl: "http://localhost:8000",
    fetchImpl: mockFetch,
  });

  const health = await client.health();
  assert.equal(health.status, "ok");
  assert.equal(health.version, "1.3.0");

  const country = await client.getCountry("US");
  assert.equal(country.calling_code, "1");

  const countries = await client.listCountries();
  assert.equal(countries.count, 249);

  const explained = await client.explain({ phone: "(415) 555-2671" });
  assert.equal(explained.record.e164, "+14155552671");
  assert.equal(explained.intelligence.locality, "San Francisco");
  assert.equal(explained.explanation.routing_tier, "AUTO_PASS");

  const cmp = await client.compare({
    phone_a: "(415) 555-2671",
    phone_b: "+14155552671",
  });
  assert.equal(cmp.is_exact_match, true);
  assert.equal(cmp.match_type, "EXACT_MATCH");

  const dedup = await client.deduplicate({
    phones: ["415-555-2671", "+14155552671"],
  });
  assert.equal(dedup.cluster_count, 1);

  const batch = await client.batch({ phones: ["(415) 555-2671"] });
  assert.equal(batch.count, 1);

  let callbackRecord = null;
  const controller = new PhoneInputController({
    client,
    defaultCountry: "US",
    onStandardized: (r) => {
      callbackRecord = r;
    },
  });

  let notifications = 0;
  const unsub = controller.subscribe(() => {
    notifications += 1;
  });

  controller.setValue("4155552671");
  assert.equal(controller.formattedValue, "(415) 555-2671");

  const validated = await controller.validate();
  assert.equal(validated.e164, "+14155552671");
  assert.equal(callbackRecord.e164, "+14155552671");
  assert.ok(notifications >= 2);
  unsub();
});

test("usePhoneInput React hook and stale requestId cancellation work deterministically", async () => {
  let resolveSlow;
  const slowPromise = new Promise((r) => {
    resolveSlow = r;
  });

  let callCount = 0;
  const mockFetch = async (_url, init) => {
    callCount += 1;
    const body = JSON.parse(init.body);
    if (callCount === 1) {
      await slowPromise;
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({
        raw_input: body.phone,
        e164: body.phone === "4155552671" ? "+14155552671" : "+12125550199",
        national: body.phone === "4155552671" ? "(415) 555-2671" : "(212) 555-0199",
        is_valid: true,
        is_possible: true,
      }),
    };
  };

  const client = new PhoneStandardizerClient({ fetchImpl: mockFetch });

  // Fake minimal ReactLike implementation
  let stateVal = 0;
  const refObj = { current: null };
  const fakeReact = {
    useState: (init) => [
      stateVal,
      (updater) => {
        stateVal = typeof updater === "function" ? updater(stateVal) : updater;
      },
    ],
    useEffect: (fn) => {
      fn();
    },
    useRef: (init) => {
      if (refObj.current === null && init !== null) refObj.current = init;
      return refObj;
    },
    useCallback: (fn) => fn,
  };

  const hook = usePhoneInput({
    client,
    defaultCountry: "US",
    initialValue: "4155552671",
    react: fakeReact,
  });

  // Start first (slow) validation
  const firstValidation = hook.validate();
  // Immediately change value and start second validation
  hook.setValue("2125550199");
  const secondValidation = await hook.validate();
  assert.equal(secondValidation.e164, "+12125550199");

  // Resolve slow first request and verify it does NOT overwrite the newer state
  resolveSlow();
  const staleResult = await firstValidation;
  assert.equal(staleResult, null);
  assert.equal(hook.controller.record.e164, "+12125550199");
});

