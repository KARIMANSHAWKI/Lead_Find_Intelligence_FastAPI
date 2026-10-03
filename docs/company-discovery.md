# Company discovery — Milestone 3

Hunter is the current `CompanySearchPort` implementation. Set `HUNTER_API_KEY`
in the environment; `HUNTER_BASE_URL` defaults to `https://api.hunter.io`.
The API key is sent in the `X-API-KEY` header. `POST /api/v1/agent/run` uses Hunter discovery followed by LLM analysis.
No web evidence is retrieved in Milestone 5.

## Filters and limitations

- Industries use Hunter's `industry.include` labels. `Software` maps to
  `Software Development`; `Logistics` maps to
  `Transportation, Logistics, Supply Chain and Storage`. Other trimmed labels
  pass through unchanged; Hunter rejects unsupported labels with an HTTP error.
- Location is a country name/ISO code or `City, Country`, converted to
  `headquarters_location.include`. `Egypt` becomes `{"country": "EG"}`;
  `Cairo, Egypt` adds `"city": "Cairo"`. A bare city is rejected rather than
  guessed. Country lookup uses the local ISO dataset from `pycountry`.
- Employee bounds select every overlapping Hunter headcount band. For 50–300,
  these are `11-50`, `51-200`, and `201-500`. This is approximate and can include
  companies outside the exact interval. A zero-only interval returns `[]`
  without a request because Hunter's smallest band starts at one.
- One Discover page returns up to 100 companies. The domain `limit` accepts
  1–100 and is applied locally. No Premium-only `limit`/`offset` parameters,
  retries, or pagination parameters are sent.
- Discover returns organization names and domains. Websites are normalized to
  HTTPS and the domain is used as `external_id`. Industry, location, and employee
  count remain `None` because the response does not establish those values.
  Hunter's email counts are never interpreted as employee counts.
- After qualification, one Domain Search request enriches the prospect with up
  to three ranked people and available generic company contact details.
- Empty results return `[]`; invalid payloads raise `ProviderResponseError`.
  Configuration, authentication, rate/usage limits, network errors, and timeouts
  have explicit exceptions without raw response bodies or credentials.

See [Hunter Discover documentation](https://hunter.io/api-documentation/v2#discover)
and its [industry labels](https://hunter.io/files/industries.json).

## Verification

Run `.venv/bin/python -m pytest -q`. Hunter tests use `httpx.MockTransport` and
never call the live API. Web research remains a skeleton. A future Google Places
adapter can implement the same domain port without changing agent code.

## ICP provider selection

`CompanySearchProviderResolver.resolve(ClientContext)` returns a `CompanySearchPort`.
The API dependency supplies the validated request ICP; the route, application use
case, and agent contain no vendor selection logic. Only the chosen provider is
constructed, so its key is the only discovery credential required.

1. Any supplied employee bound (including zero) selects Hunter.
2. Without size filters, all categories must match the explicit normalized local
   category set to select Google Places. Mixed/unknown industries select Hunter.
3. There is no automatic fallback or simultaneous search.

Examples: Software + 50–300/Egypt → Hunter; Logistics + size bounds → Hunter;
Restaurants/Cairo with no bounds → Google Places; Gyms/Alexandria with no bounds
→ Google Places; Restaurants with an employee bound → Hunter.

### Google Places

Configure `GOOGLE_PLACES_API_KEY` separately from LLM keys and optionally
`GOOGLE_PLACES_BASE_URL=https://places.googleapis.com`. Enable Places API (New)
and billing in the key's Google Cloud project. Existing generic Google keys are
not implicitly reused.

The adapter POSTs to `/v1/places:searchText`: one deterministic query per category
(`dental clinics in Cairo, Egypt`), English response language, and `pageSize`
sharing a total 1–20 company budget. It reads only the first page per category.
Fields requested: ID, display name, website URI, formatted address, and primary
type display name. Website URI incurs the Enterprise Text Search SKU; field
selection reduces payload but does not avoid that tier.

Places map to provider-independent Company objects: display name → name,
website URI → website, primary type display name → industry, formatted address
→ location, place ID → external_id, source=`google_places`, employee_count=None.
Missing optional values remain None. Empty JSON/no places returns []; malformed
payloads and provider failures remain errors. Employee bounds are explicitly
unsupported by this adapter. Multiple-category results are deduplicated by ID.

Text search is relevance-based, not a strict geographic boundary. Address and
category checks plus evidence-based qualification still apply. Branches with
separate addresses/IDs are retained even when their website is shared. Businesses
without websites normally produce no research evidence and are rejected.

API reference: https://developers.google.com/maps/documentation/places/web-service/text-search
