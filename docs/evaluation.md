# Independent accuracy evaluation

The golden datasets under `benchmarks/` are generated from this engine's own templates and reviewed overrides, so a
100% result there means "no regression", not "accurate on real addresses". This page describes the **independent**
evaluation harness under `benchmarks/eval/`, whose ground truth comes from outside the engine.

## How ground truth is obtained

1. `benchmarks/eval/build_osm_corpus.py` queries the OpenStreetMap Overpass API for objects (nodes, ways,
   relations) inside small, configurable bounding boxes per country. An object qualifies when it carries
   `addr:housenumber`, `addr:street`, `addr:postcode` and `addr:city`; `addr:state` (or `addr:province`) is kept when
   present.
2. Those structured tags are the **labels**: `house_number`, `street`, `city`, `state`, `postcode`, plus the country
   (from the bounding-box configuration). Multi-valued or implausible tags (`12;14`, very long names) are dropped.
3. For each record the builder renders several **inputs** with seeded, deterministic string transformations that
   never call the engine (the module does not import it, and a test enforces that):

   | style | what it does |
   |---|---|
   | `structured` | separate street1 / city / state / postal_code / country fields in local order |
   | `structured_swapped` | city and state values swapped between their fields (needs a state label) |
   | `line` | one line in local order with commas; country passed as an ISO code |
   | `line_country_text` | like `line` but the country name is appended and no country parameter is given |
   | `line_nocomma` | one line without commas |
   | `line_upper`, `line_lower` | ALL CAPS and lowercase |
   | `line_abbrev` | street types/directionals abbreviated (per-language table; skipped when nothing abbreviates) |
   | `line_no_postal` | postal code removed from the input (the postcode field is then not scored) |
   | `line_swapped` | city and state swapped inside the line |
   | `line_messy` | extra/odd whitespace (NBSP, tabs), NFD-decomposed accents, curly apostrophes, odd hyphens |

4. Responses from Overpass are cached on disk (`benchmarks/eval/.cache`, git-ignored). The builder sends a
   descriptive `User-Agent` with the project URL, sleeps between requests, retries with back-off across the
   `overpass-api.de` and `overpass.kumi.systems` endpoints, and uses small bounding boxes and result limits.

Rebuild (needs network the first time; later runs are offline from the cache):

```bash
PYTHONPATH=. python benchmarks/eval/build_osm_corpus.py --per-country 12 --seed 20261009 \
    --out benchmarks/eval/osm_sample.json
PYTHONPATH=. python benchmarks/eval/build_osm_corpus.py --offline ...   # cache only
```

Data is (c) OpenStreetMap contributors under the ODbL 1.0. See `benchmarks/eval/DATA_LICENSE.md`.
The committed `osm_sample.json` is **OSM-derived and not human-reviewed**.

## Running the evaluation

```bash
PYTHONPATH=. python benchmarks/eval/run_eval.py --corpus benchmarks/eval/osm_sample.json \
    --out-json eval.json --out-md eval.md
# regression gate against the committed baseline (exit 1 if any country/field accuracy drops > tolerance)
PYTHONPATH=. python benchmarks/eval/run_eval.py --baseline benchmarks/eval/baseline.json
# after an intentional, understood change: record a new snapshot
PYTHONPATH=. python benchmarks/eval/run_eval.py --write-baseline benchmarks/eval/baseline.json
```

`tests/test_eval_runner.py::test_committed_sample_meets_baseline` runs the same gate in CI.
**The baseline is a snapshot of current behaviour, not a target. Do not tune the engine to the sample.**

### Comparison rules

Comparisons are deliberately lenient only where the same address can legitimately be written differently:

- case, accents/diacritics and punctuation are ignored (`ß` = `ss`, NFKC/NFKD folding);
- street types and directionals are canonicalised (`St`/`Street`, `Str.`/`straße`, `N`/`North`, `Av.`/`Avenida`,
  `ул.`/`улица` ...) and English ordinal words (`Fifth` = `5th`);
- Colombian grid street types (`Cra`/`Cr`/`Carrera`, `Diag`/`Diagonal`, `Transv`/`Transversal`, `Circ`/`Circular`) and Dutch
  `-str.`/`-straat` are one form each (added for round 2, after v2 showed the engine's abbreviation scored as wrong);
- Turkish dotted/dotless `i` are one letter (`ı`, `İ`, `I`, `i` all fold to `i`): the engine upper-cases
  `Kızılırmak` to `KIZILIRMAK`, which is the same street, not a different one;
- for records labelled Canada only, French directionals equal their one-letter forms and the English words
  (`Ouest`/`O`/`West`/`W`, `Est`/`E`/`East`, `Nord`/`N`, `Sud`/`S`) and `boul` = `boulevard` (`Avenue`/`AV` and
  `Boulevard`/`BD` were already canonical). A different direction, a missing directional or a different street name
  still counts as wrong, and `O`/`E` are not equated with `Ouest`/`Est` for any other country;
- the house number is correct when its alphanumeric form appears as a whole token (or adjacent tokens) of the
  engine's street line; `12` does not match `123`;
- postal codes ignore spaces/hyphens/case; a US ZIP+4 matches its ZIP5;
- US/Canadian/Australian state names and abbreviations are equivalent;
- the country is compared as ISO 3166-1 alpha-3.

Everything else is a strict token comparison, so a missing locality word or a transliteration counts as wrong.

## Reading the report

- **Per field**: `accuracy` = correct / labelled (equal to recall); `precision` = correct / (correct + wrong), i.e.
  among values the engine actually produced; the 95% **Wilson** interval is on accuracy. A field is only scored
  when the label has a value and the input style kept it.
- **exact-match**: all scored fields of a rendering correct at once.
- **By country / by style**: use these to see where the engine fails, not the single headline number. Samples per
  country are small (a dozen records), so intervals are wide.
- **Worst failures**: renderings with the most wrong fields, with input and mismatching output, for triage. Always
  check whether the OSM label or the engine is wrong before changing code.
- **Calibration**: raw composite confidence versus observed exact-match (below).

## Confidence calibration

`address_standardizer/calibration.py` provides reliability bins, Expected Calibration Error (ECE, 10 equal-width
bins), the Brier score and a pure-Python isotonic (pool-adjacent-violators) `Calibrator` with `save`/`load`/`calibrate`.
Default behaviour of the confidence scorer is unchanged; to opt in:

```python
from address_standardizer.calibration import Calibrator
from address_standardizer.confidence import compute_confidence_score
cal = Calibrator.load("benchmarks/eval/calibration.json")
result = compute_confidence_score(std, raw_input=raw, calibrator=cal)   # result.calibrated_score
```

Per-field confidences (`standardize_address(..., explain=True)`, see
[api_reference.md](api_reference.md#explanations-per-field-confidence-and-alternatives)) are heuristic evidence scores and
are *not* covered by this calibration: the fitted `calibration.json` maps the composite score. A `calibrator=` passed
to `standardize_address` is applied to each field value, which is only meaningful for a calibrator fitted on
`(field_score, field_was_correct)` pairs; none ships with the package.

`benchmarks/eval/fit_calibration.py` fits it from evaluation rows (all-fields exact match is the "correct" label),
reports raw vs calibrated ECE/Brier on a held-out half split by record id, and writes `calibration.json`.
The raw score is a rule-based heuristic and was never trained to be a probability; see the measured numbers in the
section below. A calibrator fitted on this OSM sample reflects this sample's mix of countries and styles only and must
be refitted on data resembling production before its output is read as a probability.

## What "accuracy" does and does not mean

Does mean: on addresses that real mappers entered into OSM, and on mechanically degraded renderings of them, how
often the engine's fields agree with OSM's tags under the rules above.

Does not mean:

- **Not a delivery guarantee.** Nothing here checks that mail reaches the place; there is no postal authority check.
- **Labels are noisy.** OSM is volunteer data: typos, local abbreviations, inconsistent state/city usage, and
  addresses that are valid but written differently from the label. Some "errors" are label errors. The sample is
  not human-reviewed.
- **Sampling bias.** Addresses come from a few city bounding boxes chosen by hand, from objects that happen to be
  fully tagged (and Overpass returns the lowest ids first). Rural, informal and multi-unit addresses are
  under-represented. Countries are not weighted by population.
- **Synthetic degradation.** The messy styles are my model of mess, not observed production mess.
- **Country given.** Most styles pass the country as an ISO code, which makes the country field trivial; only
  `line_country_text` tests recognising it from text.
- **Small n.** About a dozen records per country; per-country numbers carry wide intervals.
- **Fields the engine does not model** (for example OSM `addr:suburb`, block/neighbourhood hierarchies in Japan or
  Korea) are not scored.

## Measured results (committed sample, 2026-10-09)

Full tables: `benchmarks/eval/REPORT.md`. Sample: 282 records from 26 countries (Latin, Cyrillic, Greek, Hebrew, Thai,
Japanese, Korean and Han scripts), 2,417 renderings. Pulled live from Overpass on 2026-10-09; some bounding boxes
returned HTTP 500/timeouts and were skipped, and Australia yielded too few tagged addresses to include.

| field | accuracy | 95% CI |
|---|---|---|
| house_number | 79.9% | 78.2 - 81.4 |
| street | 72.2% | 70.4 - 74.0 |
| city | 71.9% | 70.1 - 73.7 |
| state (where labelled) | 87.4% | 81.0 - 91.9 |
| postcode | 87.1% | 85.6 - 88.5 |
| country (mostly given) | 100% | 99.8 - 100 |
| **all fields exact** | **64.2%** | 62.2 - 66.1 |

Per style the picture is very uneven: structured input 91.8% exact, one-line with commas 71.3%, no-comma lines 3.2%
(the engine needs separators; this style is deliberately harsh), swapped city/state 0% (stress test).
Per country, Latin-script Western European countries sit near 87-89% exact (the remainder is the no-comma and
swapped stress styles), while Japan, Taiwan, Korea, Russia and Ukraine are near 0-12% on one-line input (the
engine's comma/word-order assumptions fail there), Brazil's `street, number, city` order mis-assigns the number to
the city, Dutch unspaced postcodes (`1012AP`) leak into the city, and several US ZIPs in Dorchester resolve to
WORCESTER. These are engine findings, but see the limits above before treating any single number as a verdict.

Raw confidence calibration: the composite score is essentially three clusters (0.0, ~0.88, ~0.98). Over all
renderings ECE = 0.310 and Brier = 0.310: the score reads 0.98 while the observed all-fields exact-match rate in that
bin is 66.2%. It does not discriminate well among the high-scoring renderings. An isotonic calibrator fitted on one half of the records
reduces held-out ECE from 0.289 to 0.048 (Brier 0.289 to 0.150), but most of that gain is learning the sample's base rate,
and it depends on the style mix (about one rendering in eight is a no-comma or swapped stress style). Treat `calibration.json` as a
demonstration of the mechanism, not a production calibrator.

## Held-out evaluation

**Why it exists.** `osm_sample.json` and its `baseline.json`/`REPORT.md` were used to diagnose and fix engine failures,
so the engine's score on them (93.7% all-fields exact on 2,417 renderings after those fixes) is partly *in-sample* and
must not be quoted as accuracy on unseen addresses. `osm_holdout.json` is a second corpus that nothing has been tuned
against, to be reported as the **generalisation estimate**.

**Methodology.** Same pipeline, labels, renderings, comparison rules and runner as above; only the areas change.
`build_osm_corpus.py --holdout` reads each country's `holdout_bboxes` (different cities or non-overlapping districts
from its development `bboxes`; a test enforces that no holdout box overlaps a development box), uses a different default
seed (20261201) and samples 30 records per country. It adds countries the sample never had: AU, AR, CL, CZ, EG, FI, HU,
IN, MX, NO, RO, SA, SG, TR, ZA (Hong Kong was configured but has no tagged postcodes). A test also checks that no OSM
object appears in both files. Without `--holdout` the builder behaves exactly as before.

**Rebuild** (needs network the first time; boxes that return HTTP 500/504 are skipped and are retried on the next run,
the cache serves everything already fetched):

```bash
PYTHONPATH=. python benchmarks/eval/build_osm_corpus.py --holdout --fetch-limit 200 --delay 4
PYTHONPATH=. python benchmarks/eval/run_eval.py --corpus benchmarks/eval/osm_holdout.json \
    --out-md benchmarks/eval/REPORT_HOLDOUT.md   # then add the in-sample comparison header
```

**Headline (2026-10-09, 1,195 records, 40 countries, 10,211 renderings).** All-fields exact **85.4%** held-out versus
93.7% in-sample (-8.3 points); per field house_number 96.2% (100.0% in-sample), street 87.8% (94.4%), city 89.5% (95.2%),
state 90.8% (95.8%), postcode 93.3% (97.0%), country 100%. The countries that drop most are those with the
least in-sample coverage or new city shapes: Japan 21% (100% in-sample), Hungary 12.5%, Turkey 47%, India 58%, Czechia
79%, Canada 67% (Montréal). Full tables, side-by-side comparison and the observed failure categories are in
`benchmarks/eval/REPORT_HOLDOUT.md`.

**Rules.**

- Holdout data is **never used for tuning**: no engine change, abbreviation table, comparison rule or baseline is derived
  from it, and `baseline.json` is never written from it. Its failures may be read to choose what to work on next.
- Once a fix is made from holdout findings, that area is no longer held out. Cut a fresh holdout (new
  `holdout_bboxes`, new seed) before reporting a new generalisation number, and keep the old file for history.
- Quote the held-out figure, with its interval and the OSM-label caveats above, whenever an accuracy number is needed.

## Held-out v2 (sealed)

`osm_holdout_v2.json` is a third corpus, built with `build_osm_corpus.py --holdout-v2` from each country's
`holdout_v2_bboxes` (new cities or districts, disjoint from both the development `bboxes` and the v1 `holdout_bboxes`),
seed 20270115, up to 30 records per country, the same 40 countries plus ID, MY, PH, VN, KE, NG, UY, CO, PE, EC (1,506
records in 51 countries; Ukraine has 20 and Kenya 16 because Overpass returned too few tagged addresses, and Hong Kong
yielded none, so it is absent). Offline tests check disjointness, structure, the ODbL note and that no OSM
object or record id is shared with the other two files.

**It is sealed until the current accuracy round is complete.** The engine has not been run on it, there is no report or
baseline for it, and nobody should look at per-record failures before the fixes made from the development and v1 sets
are finished. Run it once, afterwards, with `run_eval.py --corpus benchmarks/eval/osm_holdout_v2.json`, and report that
number as the generalisation estimate. After that it is contaminated like the others: any further fix derived from it
needs a v3 with fresh boxes and a fresh seed. Without `--holdout-v2` the builder's default and `--holdout` outputs are
unchanged.

### Held-out v2: measured (once)

`osm_holdout_v2.json` (1,506 records, 51 countries, seed 20270115, built from new areas and never run through the engine
before the accuracy round was complete) was measured exactly once, on 2026-10-09. Result: **92.2% all-fields exact match**
(95% CI 91.7% - 92.6%, n = 12,872 renderings); see `benchmarks/eval/REPORT_HOLDOUT_V2.md`.

| Set | Role | All-fields exact |
| :--- | :--- | :--- |
| `osm_sample.json` | development (used to diagnose and fix) | ~98.5% |
| `osm_holdout.json` (v1) | diagnostic during the accuracy round | ~97% |
| `osm_holdout_v2.json` | sealed, measured once | **92.2%** |

The gap between the development sets and v2 (about 5-6 points) is the over-fitting the fixes carry; v2 is the honest
generalisation estimate. Weakest fields on v2: `state` (66.5%, mostly Latin-American and Indian labels that carry the full
state name while the engine returns nothing or a code) and, by country, AR, CO, JP, ID, KE, MX, SA and PE. V2 is now
consumed: any engine change motivated by its failures must be validated on a new, sealed v3, never on v2 again.

## Round 2: v2 becomes a development set, v3 is sealed

After v2 was measured, its failures were used to fix the engine (that is what a development set is for), so v2 is no longer
an independent estimate. The fixes (all with tests, 100% coverage kept):

- state from a known city when the address names none: Argentine provinces and Chilean regions (as Mexico already did);
- a small gazetteer of major cities (ID, VN, KE, NG, SA, EG, TH, IN, CO, PE, AR, CL, UY, EC) to find where the city starts
  in comma-less lines such as `6813 Jabal Omar Makkah al Mukarramah 24231`;
- structured input with city and state swapped is repaired for Canada and Australia (the US already was);
- Canadian `Street, Province, City Postal`; Brazilian eight-digit CEP without a hyphen and `S/N`; Italian dotted type
  abbreviations (`V.`, `C.so`, `P.za`, `V.le`); Japanese numbers glued to a district name (`榴岡1`);
- a real bug: a bare last number such as the house number `136` was read as ISO numeric country code 136 (Cayman Islands)
  in the Russian, Latin-American, Romance, MENA and offshore grammars, which dropped it from the street.

Not done on purpose: expanding Cyrillic abbreviations (`пр-т` to `проспект`; the engine keeps the address as written and
existing tests pin that), and chasing labels that are OSM noise (Indonesian sub-localities inside the city tag, Japanese
house numbers truncated in the label, three-digit Colombian/Peruvian "postcodes" that are phone prefixes).

On v2 (now development) the all-fields exact match moved from 92.2% to about 95.9%. That number is **not** a
generalisation estimate. The honest one comes from `osm_holdout_v3.json`: built from areas disjoint from every earlier
set (`holdout_v3_bboxes`, seed 20270302), committed before any engine change from this round, run through the engine once.

### Held-out v3: measured (once)

`osm_holdout_v3.json` (1,182 records, seed 20270302) was committed before the round-2 engine commit and measured exactly
once. Six boxes (UA, MX, HK, CZ, PH, UY) were never fetched because Overpass returned HTTP 500 after retries; they are not
backfilled. Result: **94.5% all-fields exact match** (95% CI 94.0% - 94.9%, n = 10,106 renderings); see
`benchmarks/eval/REPORT_HOLDOUT_V3.md`.

| Set | Role | All-fields exact |
| :--- | :--- | :--- |
| `osm_holdout_v2.json` | consumed, now development | ~95.9% |
| `osm_holdout_v3.json` | sealed, measured once | **94.5%** |

Generalisation improved from 92.2% (v2, before the round) to 94.5% (v3, after it), and the development-to-held-out gap
shrank to about 1.4 points. The two figures are on different sets, so the improvement is indicative, not a paired
comparison. Countries under 95% on v3: JP (28.1%), PE (30.9%), ID (67.9%), MX (70.6%), EC (80.5%), BR (87.9%), TW, PH, IN,
SA, SG. Weakest field: `state` (78.4% accuracy, 93.1% precision). Part of that is OSM label noise (see above), but it has
not been separated from real engine misses, so no share is claimed. v3 is now consumed too; further tuning needs a v4.
