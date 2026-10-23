package phonestandardizer

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
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

func (c *Client) postJSON(ctx context.Context, path string, req any, out any) error {
	body, err := json.Marshal(req)
	if err != nil {
		return err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+path, bytes.NewReader(body))
	if err != nil {
		return err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("%s returned HTTP %d", path, resp.StatusCode)
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func (c *Client) getJSON(ctx context.Context, path string, out any) error {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+path, nil)
	if err != nil {
		return err
	}
	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("%s returned HTTP %d", path, resp.StatusCode)
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

// Standardize parses, validates, and formats a single telephone number.
func (c *Client) Standardize(ctx context.Context, req PhoneStandardizeRequest) (*StandardizedPhone, error) {
	var out StandardizedPhone
	if err := c.postJSON(ctx, "/v1/standardize", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Explain returns a diagnostic and geographic intelligence report for a phone number.
func (c *Client) Explain(ctx context.Context, req PhoneStandardizeRequest) (*PhoneExplainReport, error) {
	var out PhoneExplainReport
	if err := c.postJSON(ctx, "/v1/explain", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Compare compares two phone numbers using E.164 equivalence and fuzzy keypad distance.
func (c *Client) Compare(ctx context.Context, req PhoneCompareRequest) (*PhoneComparisonResult, error) {
	var out PhoneComparisonResult
	if err := c.postJSON(ctx, "/v1/compare", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Deduplicate clusters and deduplicates a list of phone numbers into Golden Phone Records.
func (c *Client) Deduplicate(ctx context.Context, req PhoneDeduplicateRequest) (*DeduplicateResponse, error) {
	var out DeduplicateResponse
	if err := c.postJSON(ctx, "/v1/deduplicate", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Batch standardizes multiple phone strings in a single request.
func (c *Client) Batch(ctx context.Context, req PhoneBatchRequest) (*BatchResponse, error) {
	var out BatchResponse
	if err := c.postJSON(ctx, "/v1/batch", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// GetCountry retrieves the ITU-T E.164 dial plan for an ISO country identifier.
func (c *Client) GetCountry(ctx context.Context, identifier string) (*CountryDialPlan, error) {
	var out CountryDialPlan
	if err := c.getJSON(ctx, "/v1/countries/"+url.PathEscape(identifier), &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ListCountries retrieves all 249 country dial plans.
func (c *Client) ListCountries(ctx context.Context) (*ListCountriesResponse, error) {
	var out ListCountriesResponse
	if err := c.getJSON(ctx, "/v1/countries", &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// StandardizeAddress parses, validates, and standardizes a physical/postal address via POST /v1/address.
func (c *Client) StandardizeAddress(ctx context.Context, req AddressStandardizeRequest) (*StandardizedAddress, error) {
	var out StandardizedAddress
	if err := c.postJSON(ctx, "/v1/address", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// StandardizeCompany standardizes an organization or company name via POST /v1/company.
func (c *Client) StandardizeCompany(ctx context.Context, req CompanyStandardizeRequest) (*StandardizedCompany, error) {
	var out StandardizedCompany
	if err := c.postJSON(ctx, "/v1/company", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// StandardizePerson standardizes a person full name via POST /v1/person.
func (c *Client) StandardizePerson(ctx context.Context, req PersonStandardizeRequest) (*StandardizedPerson, error) {
	var out StandardizedPerson
	if err := c.postJSON(ctx, "/v1/person", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// StandardizeEmail standardizes an email address via POST /v1/email.
func (c *Client) StandardizeEmail(ctx context.Context, req EmailStandardizeRequest) (*StandardizedEmail, error) {
	var out StandardizedEmail
	if err := c.postJSON(ctx, "/v1/email", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// StandardizeUrl standardizes a website URL via POST /v1/url.
func (c *Client) StandardizeUrl(ctx context.Context, req UrlStandardizeRequest) (*StandardizedUrl, error) {
	var out StandardizedUrl
	if err := c.postJSON(ctx, "/v1/url", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// StandardizeSocial standardizes a social profile URL or @handle via POST /v1/social.
func (c *Client) StandardizeSocial(ctx context.Context, req SocialStandardizeRequest) (*StandardizedSocial, error) {
	var out StandardizedSocial
	if err := c.postJSON(ctx, "/v1/social", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// StandardizeContact performs multi-pillar entity cross-healing via POST /v1/contact.
func (c *Client) StandardizeContact(ctx context.Context, req ContactStandardizeRequest) (*StandardizedContact, error) {
	var out StandardizedContact
	if err := c.postJSON(ctx, "/v1/contact", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
