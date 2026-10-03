# Lead Intelligence Agent

A FastAPI service that finds companies matching a client's Ideal Customer Profile (ICP), researches their websites, and returns qualified sales opportunities with evidence explaining **why they may need the client's product now**.

For example, a recruitment software vendor can search for software companies in Egypt. The service discovers candidates, reads their careers and company pages, and identifies supported hiring signals. Each accepted opportunity includes the company, buying signals, source URLs, product relevance, and a “why now” explanation.

This service supplies prospect intelligence. Laravel owns persistence, authentication, deterministic lead scoring, and the Filament dashboard. FastAPI does not access Laravel's database or contact prospects.

## How it works

The project uses one `LeadIntelligenceAgent`. Python controls the workflow; OpenAI selects research candidates and interprets retrieved evidence.

```text
Laravel sends client context and run ID
    → FastAPI validates the request
    → Discover companies through CompanySearchPort
    → Remove duplicates and known ICP mismatches
    → OpenAI selects candidates for deeper research
    → Crawl company websites and collect sourced text
    → OpenAI analyzes ICP fit, relevance, and buying signals
    → Validate evidence and apply qualification rules
    → Enrich qualified companies with contact information
    → Return JSON or deliver results to Laravel
```

Company discovery uses Hunter by default and whenever employee-size filters are supplied. Google Places is selected when all industries match the resolver's local-business categories and no employee-size filter is supplied. Provider selection is implemented in Python.

Research crawls company websites, prioritizing careers, news, about, and location pages. It does not currently use a general web search engine. OpenAI uses the official Python SDK, forced function calls, and Pydantic validation.

### Evidence-based qualification

Every buying signal must quote retrieved text exactly and include that text's matching source URL. A company qualifies only when:

- ICP fit is `high`.
- Product relevance is `medium` or `high`.
- Evidence quality is `medium` or `high`.
- At least one supported buying signal has `medium` or `high` strength.

The returned `why_now` combines up to three accepted evidence quotes with a product-need explanation. Companies without enough supporting evidence are skipped; an empty prospect list is a valid result.

Exact quote validation establishes traceability to retrieved content. It does not independently verify the source's accuracy or freshness. The current workflow does not require dated evidence.

## Project structure

```text
app/
├── api/             # HTTP endpoints and dependency wiring
├── application/     # Use cases and request/response DTOs
├── domain/          # Business models and provider contracts
├── agents/          # Single lead-intelligence orchestrator
├── infrastructure/  # OpenAI, discovery, research, contacts, callbacks
└── core/            # Configuration, logging, and exceptions
tests/
├── fakes/           # Test doubles; not production providers
├── unit/
└── integration/
```

The agent depends on `CompanySearchPort`, `WebResearchPort`, `LLMPort`, and optional `ContactEnrichmentPort`. Infrastructure implements these contracts.

## Setup with Docker

### 1. Prerequisites

- Git.
- Docker with Docker Compose.
- An OpenAI API key with access to the configured model.
- A Hunter API key for B2B discovery.
- A Google Places API key if you intend to run local-business searches.

Laravel is optional for direct HTTP requests. It is required when using the callback workflow.

### 2. Clone and configure

Replace the repository URL with your GitHub repository URL:

```bash
git clone <your-github-repository-url> leads_find_intelligence
cd leads_find_intelligence
cp .env.example .env
```

Edit `.env` and replace the placeholder values:

```dotenv
OPENAI_API_KEY=your-real-openai-api-key
OPENAI_MODEL=gpt-4o-mini
HUNTER_API_KEY=your-real-hunter-api-key
# Required only for Google Places discovery:
GOOGLE_PLACES_API_KEY=
```

Use a model available to your account that supports the function-calling schemas used by this project. Keep `.env` private; it is excluded by `.gitignore`.

Hunter contact enrichment is attempted after qualification, including for Google Places results. Contact lookup failures return empty contact information without discarding the qualified prospect.

### 3. Start the service

```bash
docker compose up --build
```

The API is available at `http://localhost:8990`. Interactive API documentation is available at `http://localhost:8990/docs`.

### 4. Check health

```bash
curl http://localhost:8990/health
```

Expected response:

```json
{"status":"ok","service":"lead-intelligence-agent"}
```

Health confirms that the service is running; it does not validate external provider credentials.

### 5. Run the agent

```bash
curl -X POST http://localhost:8990/api/v1/agent/run \
  -H 'Content-Type: application/json' \
  -d '{
    "run_id": 1,
    "client": {
      "product": "Recruitment Management Software",
      "target_industries": ["Software", "Logistics"],
      "location": "Egypt",
      "company_size": {"min": 50, "max": 300},
      "ideal_customer_description": "Companies actively growing their teams"
    }
  }'
```

This request waits for research to finish and returns `run_id` and a `prospects` array. Each prospect contains:

- `company_name` and `website`.
- `icp_fit` and `product_relevance` classifications.
- `why_now`.
- `buying_signals`, each with `type`, `evidence`, `source_url`, and `strength`.
- `contact_info`, containing available company emails, phone numbers, and people.

No final numeric lead score is returned. Evidence quality is used internally for qualification and is not included in the prospect response.

To request Google Places discovery, use recognized local categories such as `"Dental clinic"` and supply `"company_size": {"min": null, "max": null}`.

### 6. Logs and shutdown

```bash
docker compose logs -f agent
docker compose down
```

## Run locally without Docker

Use Python 3.12 to match the Docker image. Create `.env` as described above, then run:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8990 --reload
```

The activation command above is for Linux/macOS. On Windows PowerShell, use `.venv\Scripts\Activate.ps1`.

## Tests

After installing `requirements-dev.txt`, run:

```bash
python -m pytest -q
```

Automated tests use fakes and mocked external requests. They do not demonstrate that your live provider credentials or quotas work.

## Configuration

Settings are loaded from environment variables and `.env` using `pydantic-settings`.

| Variable | Default / purpose |
| --- | --- |
| `OPENAI_API_KEY` | Required for agent runs |
| `OPENAI_MODEL` | `gpt-4o-mini` |
| `HUNTER_API_KEY` | B2B discovery and contact enrichment |
| `GOOGLE_PLACES_API_KEY` | Local-business discovery |
| `AGENT_MAX_CANDIDATES` | `10` discovered candidates to consider |
| `AGENT_MAX_RESEARCH` | `5` candidates selected for research |
| `RESEARCH_MAX_PAGES` | `4` pages per company |
| `RESEARCH_MAX_EVIDENCE` | `8` evidence items per company |
| `CONTACT_MAX_PEOPLE` | `3` people per contact lookup |
| `LARAVEL_CALLBACK_BASE_URL` | `http://host.docker.internal:8092` |

## Laravel callback workflow

Add an optional `callback` object to the run request:

```json
{
  "url": "http://host.docker.internal:8092/api/v1/agent/runs/1/result",
  "token": "replace-with-a-real-token-of-at-least-32-characters"
}
```

The URL must exactly match `LARAVEL_CALLBACK_BASE_URL` followed by `/api/v1/agent/runs/{run_id}/result`. The token must contain 32–256 characters.

FastAPI returns HTTP `202` with `{"run_id":1,"status":"running"}` and performs the work in an in-process background task. It then posts either the completed result or a failure payload to Laravel using bearer authentication. Callback delivery makes up to three attempts for network errors or server failures.

When running without Docker, set `LARAVEL_CALLBACK_BASE_URL` to the Laravel address reachable from your local process, such as `http://localhost:8092`.

Background tasks are not durable jobs. Restarting the service can interrupt a run, and exhausted callback delivery attempts are logged without persistent recovery.

## Troubleshooting

- **HTTP 422:** Check request validation, company-size ranges, supported discovery filters, and the exact callback URL.
- **HTTP 503:** Check provider configuration or provider rate limits.
- **HTTP 502:** Check logs for external request failures or invalid LLM evidence output.
- **No prospects:** Candidates may lack retrievable evidence or fail qualification. Empty results are allowed.
- **Port 8990 unavailable:** Stop the conflicting process or change the Docker host-port mapping.

For implementation details, see [agent orchestration](docs/agent-orchestration.md), [company discovery](docs/company-discovery.md), and [LLM analysis](docs/llm-analysis.md).
