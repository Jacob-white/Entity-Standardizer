package phonestandardizer

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// Client is a zero-dependency HTTP client for the Phone Standardizer microservice.
type Client struct {
	BaseURL    string
	HTTPClient *http.Client
}

// NewClient constructs a new Phone Standardizer Go client.
func NewClient(baseURL string) *Client {
	if baseURL == "" {
		baseURL = "http://127.0.0.1:8000"
	}
	return &Client{
		BaseURL: strings.TrimRight(baseURL, "/"),
		HTTPClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// Standardize parses, validates, and formats a single telephone number.
func (c *Client) Standardize(ctx context.Context, req PhoneStandardizeRequest) (*StandardizedPhone, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/v1/standardize", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("standardize returned HTTP %d", resp.StatusCode)
	}
	var out StandardizedPhone
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Batch standardizes multiple phone strings in a single request.
func (c *Client) Batch(ctx context.Context, req PhoneBatchRequest) (*BatchResponse, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/v1/batch", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("batch returned HTTP %d", resp.StatusCode)
	}
	var out BatchResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &out, nil
}
