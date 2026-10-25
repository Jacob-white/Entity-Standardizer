import assert from "node:assert/strict";
import test from "node:test";
import {
  EntityStandardizerClient,
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
        json: async () => ({ status: "ok", version: "2.1.0" }),
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
    if (u.endsWith("/v1/address")) {
      const body = JSON.parse(init.body);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          street1: "350 5TH AVE",
          street2: body.street2 ?? "",
          city: "NEW YORK",
          state: "NY",
          postal_code: "10118",
          country: "USA",
          normalized_address_key: "350 5TH AVE|NEW YORK|NY|10118|USA",
          building_key: "350 5TH AVE|NEW YORK|NY|10118|USA",
          phonetic_key: "350|F130|N620|NY|10118",
          address_status: "standardized",
          raw_street_address: body.street1 ?? "",
          is_us: true,
          is_private_residence: false,
          is_registered_agent_hub: false,
        }),
      };
    }
    if (u.endsWith("/v1/company")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          raw_input: "Acme Holdings, Inc.",
          legal_name: "ACME HOLDINGS INC",
          base_name: "ACME HOLDINGS",
          brand_stem: "ACME",
          legal_suffix: "INC",
          dba_name: null,
          fka_name: null,
          branch_unit: null,
          inferred_country_iso2: null,
          company_key: "ACME HOLDINGS|INC",
          brand_key: "ACME",
          phonetic_key: "A250|H435",
          is_valid: true,
          confidence: 0.98,
          healing_actions: ["LEGAL_SUFFIX_NORMALIZED"],
        }),
      };
    }
    if (u.endsWith("/v1/company/compare")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          is_match: true,
          score: 1.0,
          match_type: "EXACT_COMPANY_KEY",
          company_a: { legal_name: "ACME HOLDINGS INC", is_valid: true },
          company_b: { legal_name: "ACME HOLDINGS INC", is_valid: true },
        }),
      };
    }
    if (u.endsWith("/v1/person")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          raw_input: "Dr. Bob Smith, PhD",
          salutation: "DR",
          first_name: "BOB",
          root_first_name: "ROBERT",
          middle_name: null,
          last_name: "SMITH",
          nickname: null,
          generational_suffix: null,
          credentials: ["PHD"],
          full_name: "BOB SMITH",
          person_key: "SMITH|BOB||",
          person_root_key: "SMITH|ROBERT",
          phonetic_key: "S530|R163",
          is_organization: false,
          is_valid: true,
          confidence: 0.98,
          healing_actions: ["CREDENTIALS_EXTRACTED", "SALUTATION_EXTRACTED", "NICKNAME_RESOLVED_TO_ROOT"],
        }),
      };
    }
    if (u.endsWith("/v1/person/compare")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          is_match: true,
          score: 0.96,
          match_type: "ROOT_NAME_MATCH",
          person_a: { root_first_name: "ROBERT", last_name: "SMITH", is_valid: true },
          person_b: { root_first_name: "ROBERT", last_name: "SMITH", is_valid: true },
        }),
      };
    }
    if (u.endsWith("/v1/job-title")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          raw_input: "CCO",
          normalized_title: "CHIEF COMPLIANCE OFFICER",
          seniority_level: "C_SUITE",
          department: "LEGAL",
          is_executive: true,
          is_valid: true,
          confidence: 0.96,
          healing_actions: ["TITLE_ABBREVIATION_EXPANDED"],
        }),
      };
    }
    if (u.endsWith("/v1/email")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          raw_input: "jane.doe+work@gmail.com",
          email: "janedoe@gmail.com",
          local_part: "janedoe",
          raw_local_part: "jane.doe+work",
          subaddress: "work",
          domain: "gmail.com",
          display_name: null,
          email_type: "FREE_WEBMAIL",
          is_free_provider: true,
          is_role_account: false,
          is_disposable: false,
          inferred_country_iso2: null,
          email_key: "janedoe@gmail.com",
          is_valid: true,
          confidence: 0.99,
          healing_actions: ["SUBADDRESS_EXTRACTED", "GMAIL_DOTS_CANONICALIZED"],
        }),
      };
    }
    if (u.endsWith("/v1/url")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          raw_input: "http://www.acme.co.uk/?utm_source=x",
          url: "https://acme.co.uk",
          scheme: "https",
          host: "acme.co.uk",
          domain: "acme.co.uk",
          subdomain: null,
          public_suffix: "co.uk",
          brand_stem: "ACME",
          path: "/",
          inferred_country_iso2: "GB",
          url_key: "acme.co.uk",
          is_valid: true,
          confidence: 0.98,
          healing_actions: ["SCHEME_UPGRADED_HTTPS", "WWW_STRIPPED", "TRACKING_PARAMS_STRIPPED"],
        }),
      };
    }
    if (u.endsWith("/v1/social")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          raw_input: "https://twitter.com/openai",
          platform: "X",
          profile_type: "USER",
          handle: "openai",
          url: "https://x.com/openai",
          social_key: "X|openai",
          is_valid: true,
          confidence: 0.98,
          healing_actions: ["TWITTER_CANONICALIZED_TO_X"],
        }),
      };
    }
    if (u.endsWith("/v1/contact")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          address: {
            street1: "350 5TH AVE",
            street2: "",
            city: "NEW YORK",
            state: "NY",
            postal_code: "10118",
            country: "USA",
            normalized_address_key: "350 5TH AVE|NEW YORK|NY|10118|USA",
            building_key: "350 5TH AVE|NEW YORK|NY|10118|USA",
            phonetic_key: "350|F130|N620|NY|10118",
            address_status: "standardized",
            raw_street_address: "350 Fifth Ave",
            is_us: true,
            is_private_residence: false,
            is_registered_agent_hub: false,
          },
          phone: {
            raw_input: "555-2368",
            e164: "+12125552368",
            national: "(212) 555-2368",
            international: "+1 212-555-2368",
            rfc3966: "tel:+1-212-555-2368",
            country_calling_code: "1",
            country_iso2: "US",
            country_iso3: "USA",
            country_name: "United States",
            national_significant_number: "2125552368",
            area_code: "212",
            subscriber_number: "5552368",
            extension: null,
            vanity_alias: null,
            region_code: "NY",
            line_type: "FIXED_LINE_OR_MOBILE",
            is_valid: true,
            is_possible: true,
            phone_key: "+12125552368",
            phone_ext_key: "+12125552368",
            confidence: 0.94,
            routing_tier: "AUTO_PASS",
            risk_flags: [],
            healing_actions: ["AREA_CODE_INFERRED_FROM_ADDRESS"],
          },
          fax: null,
          organization: null,
          person: null,
          job_title: null,
          email: null,
          website: null,
          social: null,
          entity_key: "350 5TH AVE|NEW YORK|NY|10118|USA||+12125552368",
          cross_healing_actions: ["PHONE_HEALED_FROM_STANDARDIZED_ADDRESS"],
          overall_confidence: 0.97,
        }),
      };
    }
    if (u.endsWith("/ready")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ status: "ready", version: "2.1.0", native_available: true }),
      };
    }
    if (u.endsWith("/v1/address/compare")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          is_match: true,
          score: 1.0,
          match_type: "EXACT_ADDRESS_KEY",
        }),
      };
    }
    if (u.endsWith("/v1/address/deduplicate")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          cluster_count: 1,
          clusters: [{ cluster_id: 1, confidence: 0.99 }],
        }),
      };
    }
    if (u.endsWith("/v1/address/autocomplete")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          count: 1,
          suggestions: [
            {
              text: "1600 PENNSYLVANIA AVE NW, WASHINGTON, DC 20500",
              street1: "1600 PENNSYLVANIA AVE NW",
              street2: "",
              city: "WASHINGTON",
              state: "DC",
              postal_code: "20500",
              country: "USA",
              secondary_prompt_required: false,
              suggested_secondary_units: [],
              highlight_ranges: [],
              score: 0.99,
              prompt_message: null,
              latitude: null,
              longitude: null,
              distance_meters: null,
            },
          ],
        }),
      };
    }
    if (u.endsWith("/v1/company/deduplicate")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          cluster_count: 1,
          clusters: [{ cluster_id: "COMPANY-CLUSTER-0001" }],
        }),
      };
    }
    if (u.endsWith("/v1/person/deduplicate")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          cluster_count: 1,
          clusters: [{ cluster_id: "PERSON-CLUSTER-0001" }],
        }),
      };
    }
    if (u.endsWith("/v1/email/compare")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          is_match: true,
          score: 1.0,
          match_type: "EXACT_EMAIL_KEY",
        }),
      };
    }
    if (u.endsWith("/v1/url/compare")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          is_match: true,
          score: 1.0,
          match_type: "EXACT_URL_KEY",
        }),
      };
    }
    if (u.endsWith("/v1/contact/cluster")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          cluster_count: 1,
          clusters: [{ cluster_id: "CONTACT-CLUSTER-0001" }],
        }),
      };
    }
    if (u.endsWith("/v1/contact/batch")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          count: 1,
          results: [{ overall_confidence: 0.97, additional_persons: [] }],
        }),
      };
    }
    if (u.endsWith("/v1/contact/compare")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          is_match: true,
          score: 0.98,
          match_type: "MULTI_PILLAR_MATCH",
          matched_pillars: ["organization", "phone"],
          pillar_scores: { organization: 1.0, phone: 1.0 },
        }),
      };
    }
    return { ok: false, status: 404, json: async () => ({}) };
  };

  assert.equal(EntityStandardizerClient, PhoneStandardizerClient);
  const client = new PhoneStandardizerClient({
    baseUrl: "http://localhost:8000",
    fetchImpl: mockFetch,
  });

  const health = await client.health();
  assert.equal(health.status, "ok");
  assert.equal(health.version, "2.1.0");

  const ready = await client.ready();
  assert.equal(ready.status, "ready");
  assert.equal(ready.native_available, true);

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

  const addr = await client.standardizeAddress({
    street1: "350 Fifth Ave",
    city: "New York",
    state: "NY",
    postal_code: "10118",
  });
  assert.equal(addr.street1, "350 5TH AVE");
  assert.equal(addr.is_us, true);

  const addrCmp = await client.compareAddresses({
    address_a: "350 Fifth Ave, New York, NY 10118",
    address_b: "350 5th Ave, New York, NY 10118",
  });
  assert.equal(addrCmp.is_match, true);
  assert.equal(addrCmp.match_type, "EXACT_ADDRESS_KEY");

  const addrDedup = await client.deduplicateAddresses({
    addresses: ["350 Fifth Ave, New York, NY 10118", "350 5th Ave, New York, NY 10118"],
  });
  assert.equal(addrDedup.cluster_count, 1);

  const autoRes = await client.autocompleteAddress({ prefix: "1600 Penn" });
  assert.equal(autoRes.count, 1);
  assert.equal(autoRes.suggestions[0].street1, "1600 PENNSYLVANIA AVE NW");

  const comp = await client.standardizeCompany({ name: "Acme Holdings, Inc." });
  assert.equal(comp.legal_suffix, "INC");
  assert.equal(comp.brand_stem, "ACME");

  const compCmp = await client.compareCompanies({
    company_a: "Acme Holdings, Inc.",
    company_b: "ACME HOLDINGS INC /DE/",
  });
  assert.equal(compCmp.is_match, true);
  assert.equal(compCmp.match_type, "EXACT_COMPANY_KEY");

  const compDedup = await client.deduplicateCompanies({
    companies: ["Acme Holdings, Inc.", "ACME HOLDINGS INC"],
  });
  assert.equal(compDedup.cluster_count, 1);

  const person = await client.standardizePerson({ name: "Dr. Bob Smith, PhD" });
  assert.equal(person.root_first_name, "ROBERT");

  const personCmp = await client.comparePersons({
    person_a: "Dr. Bob Smith",
    person_b: "Robert Smith",
  });
  assert.equal(personCmp.is_match, true);
  assert.equal(personCmp.match_type, "ROOT_NAME_MATCH");

  const personDedup = await client.deduplicatePersons({
    persons: ["Dr. Bob Smith", "Robert Smith"],
  });
  assert.equal(personDedup.cluster_count, 1);

  const titleRes = await client.standardizeJobTitle({ title: "CCO" });
  assert.equal(titleRes.normalized_title, "CHIEF COMPLIANCE OFFICER");
  assert.equal(titleRes.is_executive, true);

  const email = await client.standardizeEmail({ email: "jane.doe+work@gmail.com" });
  assert.equal(email.email, "janedoe@gmail.com");

  const emailCmp = await client.compareEmails({
    email_a: "jane.doe+work@gmail.com",
    email_b: "janedoe@gmail.com",
  });
  assert.equal(emailCmp.is_match, true);

  const urlRes = await client.standardizeUrl({ url: "http://www.acme.co.uk/?utm_source=x" });
  assert.equal(urlRes.domain, "acme.co.uk");

  const urlCmp = await client.compareUrls({
    url_a: "http://www.acme.co.uk/?utm_source=x",
    url_b: "https://acme.co.uk",
  });
  assert.equal(urlCmp.is_match, true);

  const socRes = await client.standardizeSocial({ profile: "https://twitter.com/openai" });
  assert.equal(socRes.platform, "X");

  const contact = await client.standardizeContact({
    street1: "350 Fifth Ave",
    city: "New York",
    postal_code: "10118",
    phone: "555-2368",
  });
  assert.equal(contact.phone.e164, "+12125552368");
  assert.equal(contact.address.state, "NY");
  assert.equal(contact.entity_key, "350 5TH AVE|NEW YORK|NY|10118|USA||+12125552368");
  assert.deepEqual(contact.cross_healing_actions, [
    "PHONE_HEALED_FROM_STANDARDIZED_ADDRESS",
  ]);

  const contactCmp = await client.compareContacts({
    contact_a: { organization: "Acme Holdings, Inc.", phone: "+12125552368" },
    contact_b: { organization: "ACME HOLDINGS INC", phone: "212-555-2368" },
  });
  assert.equal(contactCmp.is_match, true);
  assert.equal(contactCmp.match_type, "MULTI_PILLAR_MATCH");

  const contactClust = await client.clusterContacts({
    records: [{ phone: "+12125552368" }, { phone: "212-555-2368" }],
  });
  assert.equal(contactClust.cluster_count, 1);

  const contactBatch = await client.batchStandardizeContacts({
    contacts: [{ street1: "350 Fifth Ave", postal_code: "10118", phone: "555-2368" }],
  });
  assert.equal(contactBatch.count, 1);

  const failingClient = new PhoneStandardizerClient({
    fetchImpl: async () => ({ ok: false, status: 500, json: async () => ({}) }),
  });
  await assert.rejects(
    () => failingClient.ready(),
    /Ready check failed with status 500/
  );
  await assert.rejects(
    () => failingClient.standardizeAddress({ street1: "350 Fifth Ave" }),
    /Standardize address failed with status 500/
  );
  await assert.rejects(
    () => failingClient.compareAddresses({ address_a: "a", address_b: "b" }),
    /Compare addresses failed with status 500/
  );
  await assert.rejects(
    () => failingClient.deduplicateAddresses({ addresses: ["a"] }),
    /Deduplicate addresses failed with status 500/
  );
  await assert.rejects(
    () => failingClient.autocompleteAddress({ prefix: "1600" }),
    /Autocomplete address failed with status 500/
  );
  await assert.rejects(
    () => failingClient.standardizeCompany({ name: "Acme" }),
    /Standardize company failed with status 500/
  );
  await assert.rejects(
    () => failingClient.compareCompanies({ company_a: "Acme", company_b: "Beta" }),
    /Compare companies failed with status 500/
  );
  await assert.rejects(
    () => failingClient.deduplicateCompanies({ companies: ["Acme"] }),
    /Deduplicate companies failed with status 500/
  );
  await assert.rejects(
    () => failingClient.standardizePerson({ name: "Jane Doe" }),
    /Standardize person failed with status 500/
  );
  await assert.rejects(
    () => failingClient.comparePersons({ person_a: "Jane Doe", person_b: "John Doe" }),
    /Compare persons failed with status 500/
  );
  await assert.rejects(
    () => failingClient.deduplicatePersons({ persons: ["Jane Doe"] }),
    /Deduplicate persons failed with status 500/
  );
  await assert.rejects(
    () => failingClient.standardizeJobTitle({ title: "CCO" }),
    /Standardize job title failed with status 500/
  );
  await assert.rejects(
    () => failingClient.standardizeEmail({ email: "jane@acme.com" }),
    /Standardize email failed with status 500/
  );
  await assert.rejects(
    () => failingClient.compareEmails({ email_a: "a@b.com", email_b: "c@d.com" }),
    /Compare emails failed with status 500/
  );
  await assert.rejects(
    () => failingClient.standardizeUrl({ url: "https://acme.com" }),
    /Standardize url failed with status 500/
  );
  await assert.rejects(
    () => failingClient.compareUrls({ url_a: "https://a.com", url_b: "https://b.com" }),
    /Compare urls failed with status 500/
  );
  await assert.rejects(
    () => failingClient.standardizeSocial({ profile: "@acme" }),
    /Standardize social failed with status 500/
  );
  await assert.rejects(
    () => failingClient.standardizeContact({ street1: "350 Fifth Ave", phone: "555-2368" }),
    /Standardize contact failed with status 500/
  );
  await assert.rejects(
    () => failingClient.compareContacts({ contact_a: {}, contact_b: {} }),
    /Compare contacts failed with status 500/
  );
  await assert.rejects(
    () => failingClient.clusterContacts({ records: [] }),
    /Cluster contacts failed with status 500/
  );
  await assert.rejects(
    () => failingClient.batchStandardizeContacts({ contacts: [] }),
    /Batch standardize contacts failed with status 500/
  );

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
