using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace EntityStandardizer.Client;

public class EntityStandardizerClient
{
    private readonly HttpClient _http;
    private readonly string _baseUrl;

    public EntityStandardizerClient(string baseUrl = "http://127.0.0.1:8000", HttpClient? httpClient = null)
    {
        _baseUrl = baseUrl.TrimEnd('/');
        _http = httpClient ?? new HttpClient();
    }

    public async Task<HealthResponse?> HealthAsync(
        CancellationToken cancellationToken = default)
    {
        using var resp = await _http.GetAsync($"{_baseUrl}/health", cancellationToken).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        var body = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
        return JsonSerializer.Deserialize<HealthResponse>(body);
    }

    public async Task<ReadyResponse?> ReadyAsync(
        CancellationToken cancellationToken = default)
    {
        using var resp = await _http.GetAsync($"{_baseUrl}/ready", cancellationToken).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        var body = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
        return JsonSerializer.Deserialize<ReadyResponse>(body);
    }

    public async Task<StandardizedPhone?> StandardizeAsync(
        PhoneStandardizeRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<PhoneStandardizeRequest, StandardizedPhone>("/v1/standardize", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<PhoneBatchResponse?> BatchAsync(
        PhoneBatchRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<PhoneBatchRequest, PhoneBatchResponse>("/v1/batch", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<PhoneExplainReport?> ExplainAsync(
        PhoneStandardizeRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<PhoneStandardizeRequest, PhoneExplainReport>("/v1/explain", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<PhoneComparisonResult?> CompareAsync(
        PhoneCompareRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<PhoneCompareRequest, PhoneComparisonResult>("/v1/compare", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<PhoneDeduplicateResponse?> DeduplicateAsync(
        PhoneDeduplicateRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<PhoneDeduplicateRequest, PhoneDeduplicateResponse>("/v1/deduplicate", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<CountryDialPlan?> GetCountryAsync(
        string identifier,
        CancellationToken cancellationToken = default)
    {
        var encoded = Uri.EscapeDataString(identifier);
        using var resp = await _http.GetAsync($"{_baseUrl}/v1/countries/{encoded}", cancellationToken).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        var body = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
        return JsonSerializer.Deserialize<CountryDialPlan>(body);
    }

    public async Task<ListCountriesResponse?> ListCountriesAsync(
        CancellationToken cancellationToken = default)
    {
        using var resp = await _http.GetAsync($"{_baseUrl}/v1/countries", cancellationToken).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        var body = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
        return JsonSerializer.Deserialize<ListCountriesResponse>(body);
    }

    public async Task<StandardizedAddress?> StandardizeAddressAsync(
        AddressStandardizeRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<AddressStandardizeRequest, StandardizedAddress>("/v1/address", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<AddressComparisonResult?> CompareAddressesAsync(
        AddressCompareRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<AddressCompareRequest, AddressComparisonResult>("/v1/address/compare", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<AddressDeduplicateResponse?> DeduplicateAddressesAsync(
        AddressDeduplicateRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<AddressDeduplicateRequest, AddressDeduplicateResponse>("/v1/address/deduplicate", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<AddressAutocompleteResponse?> AutocompleteAddressAsync(
        AddressAutocompleteRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<AddressAutocompleteRequest, AddressAutocompleteResponse>("/v1/address/autocomplete", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<StandardizedCompany?> StandardizeCompanyAsync(
        CompanyStandardizeRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<CompanyStandardizeRequest, StandardizedCompany>("/v1/company", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<CompanyComparisonResult?> CompareCompaniesAsync(
        CompanyCompareRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<CompanyCompareRequest, CompanyComparisonResult>("/v1/company/compare", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<CompanyDeduplicateResponse?> DeduplicateCompaniesAsync(
        CompanyDeduplicateRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<CompanyDeduplicateRequest, CompanyDeduplicateResponse>("/v1/company/deduplicate", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<StandardizedPerson?> StandardizePersonAsync(
        PersonStandardizeRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<PersonStandardizeRequest, StandardizedPerson>("/v1/person", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<PersonComparisonResult?> ComparePersonsAsync(
        PersonCompareRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<PersonCompareRequest, PersonComparisonResult>("/v1/person/compare", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<PersonDeduplicateResponse?> DeduplicatePersonsAsync(
        PersonDeduplicateRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<PersonDeduplicateRequest, PersonDeduplicateResponse>("/v1/person/deduplicate", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<StandardizedJobTitle?> StandardizeJobTitleAsync(
        JobTitleStandardizeRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<JobTitleStandardizeRequest, StandardizedJobTitle>("/v1/job-title", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<StandardizedEmail?> StandardizeEmailAsync(
        EmailStandardizeRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<EmailStandardizeRequest, StandardizedEmail>("/v1/email", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<EmailComparisonResult?> CompareEmailsAsync(
        EmailCompareRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<EmailCompareRequest, EmailComparisonResult>("/v1/email/compare", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<StandardizedUrl?> StandardizeUrlAsync(
        UrlStandardizeRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<UrlStandardizeRequest, StandardizedUrl>("/v1/url", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<UrlComparisonResult?> CompareUrlsAsync(
        UrlCompareRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<UrlCompareRequest, UrlComparisonResult>("/v1/url/compare", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<StandardizedSocial?> StandardizeSocialAsync(
        SocialStandardizeRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<SocialStandardizeRequest, StandardizedSocial>("/v1/social", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<StandardizedContact?> StandardizeContactAsync(
        ContactStandardizeRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<ContactStandardizeRequest, StandardizedContact>("/v1/contact", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<ContactComparisonResult?> CompareContactsAsync(
        ContactCompareRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<ContactCompareRequest, ContactComparisonResult>("/v1/contact/compare", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<ContactClusterResponse?> ClusterContactsAsync(
        ContactClusterRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<ContactClusterRequest, ContactClusterResponse>("/v1/contact/cluster", request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<ContactBatchResponse?> BatchStandardizeContactsAsync(
        ContactBatchRequest request,
        CancellationToken cancellationToken = default)
    {
        return await PostJsonAsync<ContactBatchRequest, ContactBatchResponse>("/v1/contact/batch", request, cancellationToken).ConfigureAwait(false);
    }

    private async Task<TResponse?> PostJsonAsync<TRequest, TResponse>(
        string path,
        TRequest request,
        CancellationToken cancellationToken)
    {
        var json = JsonSerializer.Serialize(request);
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        using var resp = await _http.PostAsync($"{_baseUrl}{path}", content, cancellationToken).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        var body = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
        return JsonSerializer.Deserialize<TResponse>(body);
    }
}

public class PhoneStandardizerClient : EntityStandardizerClient
{
    public PhoneStandardizerClient(string baseUrl = "http://127.0.0.1:8000", HttpClient? httpClient = null)
        : base(baseUrl, httpClient)
    {
    }
}

