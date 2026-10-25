package entitystandardizer

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

// Client is a zero-dependency HTTP client for the Entity Standardizer microservice.
type Client struct {
	BaseURL    string
	HTTPClient *http.Client
}

// EntityStandardizerClient is the canonical type name for the Go SDK client.
type EntityStandardizerClient = Client

// PhoneStandardizerClient is a backward-compatible alias for EntityStandardizerClient.
type PhoneStandardizerClient = EntityStandardizerClient

// NewClient constructs a new Entity Standardizer Go client.
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

// Health checks the health and version of the Phone Standardizer microservice.
func (c *Client) Health(ctx context.Context) (*HealthResponse, error) {
	var out HealthResponse
	if err := c.getJSON(ctx, "/health", &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Ready checks the readiness and native engine availability via GET /ready.
func (c *Client) Ready(ctx context.Context) (*ReadyResponse, error) {
	var out ReadyResponse
	if err := c.getJSON(ctx, "/ready", &out); err != nil {
		return nil, err
	}
	return &out, nil
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

// CompareAddresses compares two physical/postal addresses via POST /v1/address/compare.
func (c *Client) CompareAddresses(ctx context.Context, req AddressCompareRequest) (*AddressComparisonResult, error) {
	var out AddressComparisonResult
	if err := c.postJSON(ctx, "/v1/address/compare", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// DeduplicateAddresses clusters and deduplicates addresses into Golden Address Records via POST /v1/address/deduplicate.
func (c *Client) DeduplicateAddresses(ctx context.Context, req AddressDeduplicateRequest) (*AddressDeduplicateResponse, error) {
	var out AddressDeduplicateResponse
	if err := c.postJSON(ctx, "/v1/address/deduplicate", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// AutocompleteAddress suggests canonical address completions via POST /v1/address/autocomplete.
func (c *Client) AutocompleteAddress(ctx context.Context, req AddressAutocompleteRequest) (*AddressAutocompleteResponse, error) {
	var out AddressAutocompleteResponse
	if err := c.postJSON(ctx, "/v1/address/autocomplete", req, &out); err != nil {
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

// CompareCompanies compares two organization or company names via POST /v1/company/compare.
func (c *Client) CompareCompanies(ctx context.Context, req CompanyCompareRequest) (*CompanyComparisonResult, error) {
	var out CompanyComparisonResult
	if err := c.postJSON(ctx, "/v1/company/compare", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// DeduplicateCompanies clusters and deduplicates company names via POST /v1/company/deduplicate.
func (c *Client) DeduplicateCompanies(ctx context.Context, req CompanyDeduplicateRequest) (*CompanyDeduplicateResponse, error) {
	var out CompanyDeduplicateResponse
	if err := c.postJSON(ctx, "/v1/company/deduplicate", req, &out); err != nil {
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

// ComparePersons compares two person full names via POST /v1/person/compare.
func (c *Client) ComparePersons(ctx context.Context, req PersonCompareRequest) (*PersonComparisonResult, error) {
	var out PersonComparisonResult
	if err := c.postJSON(ctx, "/v1/person/compare", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// DeduplicatePersons clusters and deduplicates person names via POST /v1/person/deduplicate.
func (c *Client) DeduplicatePersons(ctx context.Context, req PersonDeduplicateRequest) (*PersonDeduplicateResponse, error) {
	var out PersonDeduplicateResponse
	if err := c.postJSON(ctx, "/v1/person/deduplicate", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// StandardizeJobTitle standardizes a job title and classifies seniority and department via POST /v1/job-title.
func (c *Client) StandardizeJobTitle(ctx context.Context, req JobTitleStandardizeRequest) (*StandardizedJobTitle, error) {
	var out StandardizedJobTitle
	if err := c.postJSON(ctx, "/v1/job-title", req, &out); err != nil {
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

// CompareEmails compares two email addresses via POST /v1/email/compare.
func (c *Client) CompareEmails(ctx context.Context, req EmailCompareRequest) (*EmailComparisonResult, error) {
	var out EmailComparisonResult
	if err := c.postJSON(ctx, "/v1/email/compare", req, &out); err != nil {
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

// CompareUrls compares two website URLs via POST /v1/url/compare.
func (c *Client) CompareUrls(ctx context.Context, req UrlCompareRequest) (*UrlComparisonResult, error) {
	var out UrlComparisonResult
	if err := c.postJSON(ctx, "/v1/url/compare", req, &out); err != nil {
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

// CompareContacts compares two multi-pillar contact/entity records via POST /v1/contact/compare.
func (c *Client) CompareContacts(ctx context.Context, req ContactCompareRequest) (*ContactComparisonResult, error) {
	var out ContactComparisonResult
	if err := c.postJSON(ctx, "/v1/contact/compare", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ClusterContacts clusters multi-pillar contact records into Golden Entity Clusters via POST /v1/contact/cluster.
func (c *Client) ClusterContacts(ctx context.Context, req ContactClusterRequest) (*ContactClusterResponse, error) {
	var out ContactClusterResponse
	if err := c.postJSON(ctx, "/v1/contact/cluster", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// BatchStandardizeContacts standardizes multiple contact records in a single request via POST /v1/contact/batch.
func (c *Client) BatchStandardizeContacts(ctx context.Context, req ContactBatchRequest) (*ContactBatchResponse, error) {
	var out ContactBatchResponse
	if err := c.postJSON(ctx, "/v1/contact/batch", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
