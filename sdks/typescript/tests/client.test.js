import assert from "node:assert/strict";
import test from "node:test";
import {
  formatAsYouType,
  PhoneInputController,
  PhoneStandardizerClient,
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
        json: async () => ({ status: "ok", version: "1.0.0" }),
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
    if (u.endsWith("/v1/batch")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ count: 1, results: [] }),
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

  const country = await client.getCountry("US");
  assert.equal(country.calling_code, "1");

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
