using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace PhoneStandardizer.Client;

public sealed class PhoneStandardizerClient
{
    private readonly HttpClient _http;
    private readonly string _baseUrl;

    public PhoneStandardizerClient(string baseUrl = "http://127.0.0.1:8000", HttpClient? httpClient = null)
    {
        _baseUrl = baseUrl.TrimEnd('/');
        _http = httpClient ?? new HttpClient();
    }

    public async Task<StandardizedPhone?> StandardizeAsync(
        PhoneStandardizeRequest request,
        CancellationToken cancellationToken = default)
    {
        var json = JsonSerializer.Serialize(request);
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        using var resp = await _http.PostAsync($"{_baseUrl}/v1/standardize", content, cancellationToken).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        var body = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
        return JsonSerializer.Deserialize<StandardizedPhone>(body);
    }
}
