package phonestandardizer

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestClientStandardizeAndBatch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/v1/standardize" {
			_ = json.NewEncoder(w).Encode(StandardizedPhone{
				RawInput:    "(415) 555-2671",
				E164:        "+14155552671",
				National:    "(415) 555-2671",
				CountryISO2: "US",
				RegionCode:  "CA",
				IsValid:     true,
				IsPossible:  true,
				Confidence:  1.0,
				RoutingTier: "AUTO_PASS",
			})
			return
		}
		if r.URL.Path == "/v1/batch" {
			_ = json.NewEncoder(w).Encode(BatchResponse{
				Count: 1,
				Results: []StandardizedPhone{
					{E164: "+14155552671", IsValid: true},
				},
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
	if res.E164 != "+14155552671" || !res.IsValid {
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
}
