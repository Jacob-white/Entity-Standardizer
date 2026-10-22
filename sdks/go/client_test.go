package phonestandardizer

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func strPtr(s string) *string {
	return &s
}

func TestClientStandardizeAndBatch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/v1/standardize":
			_ = json.NewEncoder(w).Encode(StandardizedPhone{
				RawInput:    "(415) 555-2671",
				E164:        strPtr("+14155552671"),
				National:    strPtr("(415) 555-2671"),
				CountryISO2: strPtr("US"),
				RegionCode:  strPtr("CA"),
				Extension:   nil,
				IsValid:     true,
				IsPossible:  true,
				Confidence:  1.0,
				RoutingTier: "AUTO_PASS",
			})
			return
		case "/v1/batch":
			_ = json.NewEncoder(w).Encode(BatchResponse{
				Count: 1,
				Results: []StandardizedPhone{
					{E164: strPtr("+14155552671"), IsValid: true},
				},
			})
			return
		case "/v1/explain":
			_ = json.NewEncoder(w).Encode(PhoneExplainReport{
				Record: StandardizedPhone{E164: strPtr("+14155552671"), IsValid: true},
				Intelligence: PhoneIntelligence{
					Locality:      strPtr("San Francisco, CA"),
					Timezones:     []string{"America/Los_Angeles"},
					IsCallableNow: true,
					LocalHours:    []int{10},
				},
				Explanation: PhoneExplanation{
					Confidence:  1.0,
					RoutingTier: "AUTO_PASS",
				},
			})
			return
		case "/v1/compare":
			_ = json.NewEncoder(w).Encode(PhoneComparisonResult{
				IsExactMatch:    true,
				IsFuzzyMatch:    true,
				SimilarityScore: 1.0,
				MatchType:       "EXACT_MATCH",
			})
			return
		case "/v1/deduplicate":
			_ = json.NewEncoder(w).Encode(DeduplicateResponse{
				ClusterCount: 1,
				Clusters: []PhoneCluster{
					{ClusterID: "PHONE-CLUSTER-0001", GoldenPhone: StandardizedPhone{E164: strPtr("+14155552671")}},
				},
			})
			return
		case "/v1/countries/US":
			_ = json.NewEncoder(w).Encode(CountryDialPlan{
				ISO2:        "US",
				CallingCode: "1",
			})
			return
		case "/v1/countries":
			_ = json.NewEncoder(w).Encode(ListCountriesResponse{
				Count:     249,
				Countries: []CountryDialPlan{{ISO2: "US", CallingCode: "1"}},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	client := NewClient(srv.URL)
	res, err := client.Standardize(context.Background(), PhoneStandardizeRequest{
		Phone: "(415) 555-2671",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.E164 == nil || *res.E164 != "+14155552671" || !res.IsValid || res.Extension != nil {
		t.Fatalf("unexpected result: %+v", res)
	}

	batchRes, err := client.Batch(context.Background(), PhoneBatchRequest{
		Phones: []string{"(415) 555-2671"},
	})
	if err != nil {
		t.Fatalf("unexpected batch error: %v", err)
	}
	if batchRes.Count != 1 {
		t.Fatalf("unexpected batch count: %d", batchRes.Count)
	}

	expRes, err := client.Explain(context.Background(), PhoneStandardizeRequest{Phone: "(415) 555-2671"})
	if err != nil || expRes.Intelligence.Locality == nil || *expRes.Intelligence.Locality != "San Francisco, CA" {
		t.Fatalf("unexpected explain result: %+v, err=%v", expRes, err)
	}

	cmpRes, err := client.Compare(context.Background(), PhoneCompareRequest{
		PhoneA: "(415) 555-2671",
		PhoneB: "+14155552671",
	})
	if err != nil || !cmpRes.IsExactMatch {
		t.Fatalf("unexpected compare result: %+v, err=%v", cmpRes, err)
	}

	dedupRes, err := client.Deduplicate(context.Background(), PhoneDeduplicateRequest{
		Phones: []string{"415-555-2671", "+14155552671"},
	})
	if err != nil || dedupRes.ClusterCount != 1 {
		t.Fatalf("unexpected deduplicate result: %+v, err=%v", dedupRes, err)
	}

	countryRes, err := client.GetCountry(context.Background(), "US")
	if err != nil || countryRes.CallingCode != "1" {
		t.Fatalf("unexpected country result: %+v, err=%v", countryRes, err)
	}

	listRes, err := client.ListCountries(context.Background())
	if err != nil || listRes.Count != 249 {
		t.Fatalf("unexpected list countries result: %+v, err=%v", listRes, err)
	}
}

