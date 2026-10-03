# Lead Intelligence Agent — Hackathon MVP

## Project Goal

Build a FastAPI-based AI agent service for a B2B Lead Intelligence platform.

The agent helps companies find high-potential business prospects that match their Ideal Customer Profile (ICP).

The main value proposition is:

> Find companies worth contacting now — and explain WHY NOW.

The agent should not simply return random companies.

It must:

1. Search for candidate companies.
2. Research each candidate.
3. Check ICP fit.
4. Detect buying signals.
5. Collect supporting evidence.
6. Evaluate product relevance.
7. Return structured qualified opportunities.

The Laravel application is responsible for persistence, database models, scoring, authentication, and the Filament dashboard.

FastAPI is responsible only for AI reasoning, research, and external AI/search integrations.

---

# Architecture

The system architecture is:

```text
Filament Dashboard
        ↓
Laravel Application
        ↓ REST API
FastAPI Agent Service
        ↓
OpenAI SDK
        ↓
Agent Tools
        ↓
External Data Sources
```

Laravel owns:

- PostgreSQL database
- Client profiles
- ICP configuration
- Prospects
- Buying signals
- Lead scores
- Agent runs
- Agent actions
- Authentication
- Filament dashboard
- Business rules
- Deterministic scoring

FastAPI owns:

- Lead Intelligence Agent
- OpenAI integration
- Company search integrations
- Web research
- Buying signal detection
- AI-based interpretation
- Structured research results

FastAPI must NOT directly access the Laravel database.

Laravel sends the required context to FastAPI through HTTP.

FastAPI returns structured JSON.

Laravel validates and stores the result.

---

# Hackathon Constraints

This is a hackathon MVP.

Do NOT over-engineer.

We have limited time.

Prioritize:

1. Working end-to-end flow
2. Reliable demo
3. Clear architecture
4. Structured outputs
5. Explainable agent decisions

Avoid unnecessary infrastructure.

---

# MVP Workflow

The core flow is:

```text
Client Profile
      ↓
ICP Configuration
      ↓
Run Lead Agent
      ↓
Search Candidate Companies
      ↓
Research Candidates
      ↓
Detect Buying Signals
      ↓
Evaluate ICP Fit
      ↓
Evaluate Product Relevance
      ↓
Return Qualified Prospects
      ↓
Laravel Calculates Final Score
      ↓
Filament Displays Results
```

The FastAPI MVP stops after returning structured prospect intelligence.

---

# Current FastAPI Responsibilities

FastAPI should expose:

```text
GET /health

POST /api/v1/agent/run
```

The agent endpoint receives client context and returns researched prospects.

Example request:

```json
{
  "run_id": 1,
  "client": {
    "product": "Recruitment Management Software",
    "target_industries": [
      "Software",
      "Logistics"
    ],
    "location": "Egypt",
    "company_size": {
      "min": 50,
      "max": 300
    },
    "ideal_customer_description": "Companies actively growing their teams"
  }
}
```

Example response:

```json
{
  "run_id": 1,
  "prospects": [
    {
      "company_name": "ABC Logistics",
      "website": "https://example.com",
      "icp_fit": "high",
      "product_relevance": "high",
      "why_now": "The company is actively hiring and expanding its operations.",
      "buying_signals": [
        {
          "type": "hiring_growth",
          "evidence": "The company currently advertises 18 open positions.",
          "source_url": "https://example.com/jobs",
          "strength": "high"
        }
      ]
    }
  ]
}
```

---

# Important Separation of Responsibilities

The AI agent must NOT calculate the final numeric lead score.

Laravel owns deterministic scoring.

For example:

```text
ICP Match            40 points
Buying Signals       30 points
Product Relevance    20 points
Evidence Quality     10 points
                     ─────────
                     100 points
```

FastAPI may return classifications such as:

```text
icp_fit = high

product_relevance = high

buying_signal strength = high

evidence quality = strong
```

Laravel converts these classifications into numeric scores.

Do not ask the LLM:

> Give this company a score from 0 to 100.

---

# Agent Architecture

For the MVP use:

```text
ONE Lead Intelligence Agent
+
Tools
```

Do NOT implement a multi-agent system unless explicitly requested.

Do NOT create:

- Supervisor Agent
- Research Agent
- Qualification Agent
- Scoring Agent
- Outreach Agent

The MVP should use one orchestrator agent.

Conceptually:

```text
LeadIntelligenceAgent
        │
        ├── search_companies()
        │
        ├── research_company()
        │
        ├── search_web()
        │
        └── extract_buying_signals()
```

---

# Agent Goal

The Lead Intelligence Agent's goal is:

> Find high-potential companies matching the client's ICP and identify evidence explaining why each company may need the client's product now.

The agent must prefer quality over quantity.

Returning 5 strongly researched opportunities is better than returning 100 weak company names.

---

# Agent Reasoning Flow

The agent should approximately follow:

```text
Load client ICP
      ↓
Search candidate companies
      ↓
For each candidate:
      ↓
Check basic ICP compatibility
      ↓
If clearly incompatible:
      → Skip

If potentially relevant:
      ↓
Research company
      ↓
Search for buying signals
      ↓
Collect evidence
      ↓
Evaluate product relevance
      ↓
Enough evidence?
      /       \
    No         Yes
    ↓           ↓
  Skip       Return Prospect
```

The exact tool sequence may vary.

The agent is allowed to decide whether deeper research is necessary.

---

# Buying Signals

Buying signals depend on what the client sells.

Examples include:

- Hiring growth
- New office
- New branch
- Geographic expansion
- New market entry
- Large recruitment activity
- New management hire
- New product launch
- Funding announcement
- Ecommerce expansion
- New warehouse
- New operational location
- Technology migration
- Rapid team growth

Do not hardcode all signals as universally relevant.

Interpret them relative to the client's product.

Example:

Client product:

```text
Recruitment Software
```

Relevant signal:

```text
Company hiring 25 employees
```

Client product:

```text
POS Software
```

Relevant signal:

```text
Restaurant opening three new branches
```

---

# WHY NOW

Every qualified opportunity should answer:

> Why is this company worth contacting now?

Example:

```text
Company:
ABC Logistics

WHY NOW:

The company is currently hiring across multiple departments and recently opened a new office. This indicates increasing recruitment and workforce-management complexity.
```

The `why_now` field is one of the most important outputs of the system.

---

# Evidence Rules

Never invent company information.

Every meaningful buying signal must have supporting evidence.

Prefer outputs with:

```text
signal
+
evidence
+
source
```

Example:

```json
{
  "type": "hiring_growth",
  "evidence": "The company lists 18 active job openings.",
  "source_url": "https://example.com/careers",
  "strength": "high"
}
```

If evidence cannot be verified:

```text
do not claim the signal as fact
```

Insufficient evidence is a valid result.

---

# Hallucination Guardrails

The agent must:

- Never invent companies.
- Never invent job openings.
- Never invent company size.
- Never invent branches.
- Never invent expansion announcements.
- Never invent funding.
- Never invent employee counts.
- Never invent website content.

If information is uncertain, explicitly mark it as uncertain or skip the claim.

---

# Outreach Scope

The MVP does NOT contact prospects.

Do not implement:

- Email sending
- WhatsApp sending
- LinkedIn messages
- SMS
- Automated outreach
- Follow-up sequences
- Calendar booking

The MVP stops at:

```text
Qualified Opportunity
```

Optionally return:

```text
recommended_sales_angle
```

but do not contact anyone and if mpv done i will say you to contact them.

---

# Search Providers

External company discovery must be behind the `CompanySearchPort` abstraction.

The supported company discovery providers are:

- Hunter Discover
- Google Places

Do NOT use Hunter in this project.

For the hackathon MVP, start with Hunter only.

Hunter is the primary provider for B2B company discovery where the ICP depends on attributes such as:

- industry
- headquarters location
- company size
- B2B company characteristics

Google Places should be added after the Hunter flow works end-to-end.

Google Places is intended for local-business ICPs such as:

- restaurants
- clinics
- gyms
- salons
- training centers
- retail stores
- hotels
- other location-based SMEs

Both providers must implement the same domain abstraction:

```python
CompanySearchPort
```

The Lead Intelligence Agent must never depend directly on Hunter or Google Places.

The intended architecture is:

```text
LeadIntelligenceAgent
        ↓
CompanySearchPort
        ↓
Provider Resolver
   ├── HunterCompanySearchProvider
   └── GooglePlacesCompanySearchProvider
```

For the current implementation phase:

```text
CompanySearchPort
        ↓
HunterCompanySearchProvider
```

Do not implement the Google Places provider until the Hunter integration and the complete lead-intelligence flow are working.

Later, provider selection may be based on the ICP:

```text
B2B / firmographic ICP
→ Hunter

Local-business / location-oriented ICP
→ Google Places
```

Do not let the LLM directly choose or call external provider APIs.

Provider selection belongs in application/infrastructure code.

---

# Web Research

Research may use:

- Company website
- Public web search
- News
- Careers pages
- Public job postings

Research must return structured evidence.

---

# OpenAI Usage

Use the official OpenAI Python SDK.

Prefer structured outputs using Pydantic models.

The model should return structured data whenever possible.

Avoid parsing arbitrary free-form text if a structured schema can be used.

Example conceptual response:

```python
class ProspectResearch(BaseModel):
    company_name: str
    website: str | None
    icp_fit: Literal["high", "medium", "low"]
    product_relevance: Literal["high", "medium", "low"]
    why_now: str
    buying_signals: list[BuyingSignal]
```

---

# FastAPI Project Structure

Follow a simplified Clean Architecture approach with SOLID principles.

The architecture should clearly separate:

- API / delivery layer
- Application use cases
- Domain models and contracts
- Agent orchestration
- Infrastructure integrations
- Configuration

Prefer this structure:

```text
app/
├── __init__.py
├── main.py
│
├── api/
│   ├── __init__.py
│   └── v1/
│       ├── __init__.py
│       └── agent_routes.py
│
├── application/
│   ├── __init__.py
│   │
│   ├── use_cases/
│   │   └── run_lead_intelligence.py
│   │
│   └── dto/
│       ├── request.py
│       └── response.py
│
├── domain/
│   ├── __init__.py
│   │
│   ├── models/
│   │   ├── company.py
│   │   ├── prospect.py
│   │   └── buying_signal.py
│   │
│   └── ports/
│       ├── company_search.py
│       ├── web_research.py
│       └── llm.py
│
├── agents/
│   ├── __init__.py
│   └── lead_intelligence_agent.py
│
├── infrastructure/
│   ├── __init__.py
│   │
│   ├── llm/
│   │   └── openai_client.py
│   │
│   ├── company_search/
│   │   ├── hunter_provider.py
│   │   └── google_places_provider.py
│   │
│   └── research/
│       └── web_search_provider.py
│
└── core/
    ├── __init__.py
    ├── config.py
    └── exceptions.py
```

## Layer Responsibilities

### API Layer

```text
app/api/
```

Responsible only for HTTP concerns.

Examples:

- FastAPI routes
- Request validation
- Response formatting
- Dependency wiring

The API layer must not contain:

- OpenAI logic
- Company search implementation
- Lead qualification logic
- Agent orchestration

Example flow:

```text
POST /api/v1/agent/run
        ↓
RunLeadIntelligenceUseCase
```

---

### Application Layer

```text
app/application/
```

Contains application-specific workflows and use cases.

The primary use case is:

```text
RunLeadIntelligence
```

Its responsibility is to coordinate the application flow.

Conceptually:

```text
API Request
    ↓
RunLeadIntelligence
    ↓
LeadIntelligenceAgent
    ↓
Structured Result
```

The application layer may depend on domain abstractions.

It must not depend directly on:

- Hunter
- Google Places
- OpenAI SDK
- Google APIs
- External HTTP providers

---

### Domain Layer

```text
app/domain/
```

Contains the core models and contracts of the FastAPI service.

Domain models include:

```text
Company
Prospect
BuyingSignal
```

These models should represent business concepts without depending on external providers.

The domain layer also defines ports/interfaces such as:

```text
CompanySearchPort
WebResearchPort
LLMPort
```

Example:

```python
from abc import ABC, abstractmethod

from app.domain.models.company import Company


class CompanySearchPort(ABC):

    @abstractmethod
    async def search(
        self,
        industry: str,
        location: str,
        min_size: int | None = None,
        max_size: int | None = None,
    ) -> list[Company]:
        ...
```

Application and agent code must depend on these abstractions instead of directly depending on vendor-specific integrations.

---

### Agent Layer

```text
app/agents/
```

Contains agent orchestration only.

The main agent is:

```text
LeadIntelligenceAgent
```

Its responsibility is to coordinate the reasoning process.

Conceptually:

```text
Client ICP
    ↓
Search companies
    ↓
Research candidate
    ↓
Collect evidence
    ↓
Interpret buying signals
    ↓
Evaluate relevance
    ↓
Return structured prospect intelligence
```

The agent should depend on abstractions:

```python
class LeadIntelligenceAgent:

    def __init__(
        self,
        company_search: CompanySearchPort,
        web_research: WebResearchPort,
        llm: LLMPort,
    ):
        self.company_search = company_search
        self.web_research = web_research
        self.llm = llm
```

The agent must not directly instantiate:

- Hunter clients
- Google Places clients
- OpenAI clients
- HTTP clients
- vendor-specific integrations

Avoid putting infrastructure-specific logic inside the agent.

---

### Infrastructure Layer

```text
app/infrastructure/
```

Contains implementations for external integrations.

Examples:

```text
OpenAI
Hunter
Google Places
Web Search
```

Infrastructure implementations must implement domain ports.

Example:

```text
CompanySearchPort
        ↑
HunterCompanySearchProvider
```

and:

```text
LLMPort
        ↑
OpenAIClient
```

This allows integrations to change without modifying the application or agent layers.

For example:

```text
HunterCompanySearchProvider
      ↓ selected/replaced by
GooglePlacesCompanySearchProvider
```

without changing:

```text
LeadIntelligenceAgent
```

---

# Dependency Direction

Follow this dependency direction:

```text
API
 ↓
Application
 ↓
Domain

Infrastructure
 ↑ implements Domain Ports
```

Core business/application code should not depend directly on infrastructure.

Infrastructure depends on domain contracts.

---

# SOLID Principles

## Single Responsibility Principle

Each component should have one clear responsibility.

Examples:

```text
LeadIntelligenceAgent
→ agent orchestration

RunLeadIntelligence
→ application use case

HunterCompanySearchProvider
→ Hunter B2B company discovery

WebSearchProvider
→ web research

OpenAIClient
→ LLM integration
```

Do not create large service classes responsible for unrelated functionality.

---

## Open / Closed Principle

The system should be extendable without modifying core logic.

For example:

```text
CompanySearchPort
        ↑
HunterProvider
```

can later become:

```text
CompanySearchPort
        ↑
HunterProvider
        ↑
GooglePlacesProvider
```

without changing the Lead Intelligence Agent.

---

## Liskov Substitution Principle

Any implementation of a domain port should honor its contract. `OpenAIClient`
implements:

```text
LLMPort
```

The application should not care which implementation is currently configured.

---

## Interface Segregation Principle

Prefer small focused interfaces.

Use:

```text
CompanySearchPort
WebResearchPort
LLMPort
```

Avoid creating a large interface such as:

```text
AIService
```

with unrelated responsibilities.

---

## Dependency Inversion Principle

High-level modules such as:

```text
LeadIntelligenceAgent
RunLeadIntelligence
```

must depend on abstractions.

They must not depend directly on:

```text
Hunter API
Google Places API
OpenAI SDK
```

---

# Buying Signal Responsibility

Do not create a separate infrastructure tool such as:

```text
buying_signals.py
```

unless it represents a real externally callable tool.

Buying signal identification is part of the research and reasoning process.

The preferred flow is:

```text
Research company
      ↓
Collect verified evidence
      ↓
LLM interprets evidence
      ↓
Identify relevant buying signals
      ↓
Return structured BuyingSignal objects
```

A buying signal must always contain evidence.

Example:

```json
{
  "type": "hiring_growth",
  "evidence": "The company currently lists 18 open positions.",
  "source_url": "https://example.com/careers",
  "strength": "high"
}
```

---

# Provider Strategy

Production runtime should use real providers.

Do not include mock providers inside:

```text
app/infrastructure/
```

The MVP must start with one real company search provider:

```text
HunterCompanySearchProvider
```

Hunter is the initial implementation and must implement:

```text
CompanySearchPort
```

Google Places is the second supported provider:

```text
GooglePlacesCompanySearchProvider
```

but it should NOT be implemented until the Hunter-based end-to-end flow is working.

Both implementations must satisfy:

```text
CompanySearchPort
```

The agent must not know which concrete provider is active.

Provider choice should eventually be determined from ICP characteristics.

Preferred selection rule:

```text
B2B company ICP
with industry / location / company size filters
→ HunterCompanySearchProvider

Local-business ICP
with business category / geographic location filters
→ GooglePlacesCompanySearchProvider
```

For the current hackathon implementation:

```text
Always start with HunterCompanySearchProvider.
```

Do not add automatic provider resolution until it is needed.

A working Hunter implementation is higher priority than supporting multiple providers.

---

# Testing Strategy

Mocks/fakes may still be used for automated tests.

Test doubles belong under:

```text
tests/
├── fakes/
│   ├── fake_company_search.py
│   ├── fake_web_research.py
│   └── fake_llm.py
│
├── unit/
└── integration/
```

Do not put testing mocks inside production application code.

This allows unit tests to be:

- deterministic
- fast
- independent from Hunter
- independent from Google Places
- independent from OpenAI
- independent from external network availability

---

# Laravel Boundary

FastAPI must remain stateless regarding business persistence.

FastAPI must NOT directly access Laravel's PostgreSQL database.

The integration remains:

```text
Laravel
   ↓ HTTP request
FastAPI
   ↓
Lead Intelligence Agent
   ↓
External providers
   ↓
Structured result
   ↓ HTTP response
Laravel
   ↓
Validate
Score
Persist
Display in Filament
```

Laravel remains responsible for:

- persistence
- final numeric lead score
- prospects
- buying signals
- agent runs
- agent actions
- authentication
- dashboard

FastAPI remains responsible for:

- AI reasoning
- company discovery
- company research
- evidence collection
- buying signal interpretation
- product relevance
- WHY NOW

---

# General Structure Rules

Keep modules small and focused.

Avoid putting agent logic in:

```text
main.py
```

Avoid putting OpenAI code in:

```text
agent_routes.py
```

Avoid putting Hunter- or Google-Places-specific logic in:

```text
lead_intelligence_agent.py
```

Avoid generic classes such as:

```text
AIService
HelperService
UtilityService
```

when a more specific abstraction can be used.

Prefer explicit names that describe responsibility.

Do not add abstractions unless they protect an actual architectural boundary.

Remember that this is still a hackathon MVP.

Apply SOLID principles pragmatically.

Do not turn the project into unnecessary enterprise architecture.
-----

# Company Search Implementation Priority

For the current development milestone:

```text
Use Hunter first.
```

Do not implement Hunter.

Do not implement Google Places yet.

The current production infrastructure should contain:

```text
app/infrastructure/company_search/hunter_provider.py
```

The future Google Places implementation should be added as:

```text
app/infrastructure/company_search/google_places_provider.py
```

only after the Hunter-based flow works end-to-end.

The domain contract remains:

```text
CompanySearchPort
```

This allows switching providers without changing:

```text
LeadIntelligenceAgent
RunLeadIntelligence
```

---

# Configuration

Configuration must come from environment variables.

Examples:

```text
OPENAI_API_KEY

APP_ENV

LARAVEL_API_URL

HUNTER_API_KEY

GOOGLE_PLACES_API_KEY
```

Use `pydantic-settings`.

Do not hardcode secrets.

Do not commit `.env`.

---

# Docker

The FastAPI application runs inside Docker.

Development service:

```text
FastAPI
localhost:8990
```

Required endpoints:

```text
GET /health

POST /api/v1/agent/run
```

The project should work with:

```bash
docker compose up --build
```

---

# Development Strategy

Implement features incrementally.

Do NOT implement the entire architecture at once.

Mil

# OpenAI LLM

The FastAPI service uses only the official OpenAI Python SDK and OpenAI API.
Configuration consists only of `OPENAI_API_KEY` and `OPENAI_MODEL`.

---

# OpenAI SDK as the Common Client

Use:

```python id="m6ojs7"
from openai import AsyncOpenAI
```

Use the default OpenAI API endpoint.

Conceptually:

```text id="3d2ppr"
LeadIntelligenceAgent
        ↓
LLMPort
        ↓
OpenAI API
```

The agent depends on `LLMPort`; infrastructure owns the OpenAI SDK client.

---

# OpenAI Configuration

Use only:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```


# Company Search Implementation Priority

For the current development milestone:

```text
Use Hunter first.
```

Do not implement Hunter.

Do not implement Google Places yet.

The current production infrastructure should contain:

```text
app/infrastructure/company_search/hunter_provider.py
```

The future Google Places implementation should be added as:

```text
app/infrastructure/company_search/google_places_provider.py
```

only after the Hunter-based flow works end-to-end.

The domain contract remains:

```text
CompanySearchPort
```

This allows switching providers without changing:

```text
LeadIntelligenceAgent
RunLeadIntelligence
```

---

# Configuration Example

Environment configuration may look like:

```env id="6dwvpe"
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

Use a valid OpenAI model ID supported by the project account.

# LLM Runtime Strategy

The project uses the OpenAI Python SDK and the default OpenAI API endpoint.

The architecture should optimize for:

- reliability
- portability
- low latency
- hackathon delivery speed

Do not add alternate LLM providers unless explicitly requested.

---

# Required LLM Capabilities

The core Lead Intelligence Agent should depend only on a minimum shared capability set.

Required capabilities:

```text
- Text generation
- Tool / function calling
- Structured JSON output
- Reasoning over retrieved evidence
```

These capabilities are required for the main agent workflow.

Optional provider-specific capabilities include:

```text
- Native web search
- Code execution
- Provider-managed conversation state
- Prompt caching
- Advanced reasoning controls
- Provider-specific built-in tools
```

The core agent must not depend on optional capabilities.

---

# Provider Strategy

The project supports OpenAI only. Model selection comes from configuration.

Example:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

---

# Provider Independence

The Lead Intelligence Agent must depend only on:

```text
LLMPort
```

and never directly on OpenAI SDK configuration details.

Conceptually:

```text
LeadIntelligenceAgent
        ↓
      LLMPort
        ↓
OpenAI client
```

OpenAI client construction belongs in the infrastructure layer.

---

# External Tools Strategy

Do not rely on provider-native built-in web search for the core agent workflow.

Use application-owned tools.

Preferred architecture:

```text
LeadIntelligenceAgent
        │
        ├── LLMPort
        │
        ├── CompanySearchPort
        │
        └── WebResearchPort
```

Responsibilities:

```text
LLMPort
→ reasoning
→ evidence interpretation
→ ICP evaluation
→ buying signal interpretation
→ WHY NOW generation

CompanySearchPort
→ discover candidate companies

WebResearchPort
→ research websites
→ search public information
→ collect evidence
```

This keeps OpenAI-specific client details outside the agent.

---

# Company Discovery

Company discovery must be handled through:

```text
CompanySearchPort
```

The supported implementations are:

```text
HunterCompanySearchProvider
GooglePlacesCompanySearchProvider
```

Implementation priority:

```text
1. HunterCompanySearchProvider
2. Complete the full end-to-end agent workflow
3. Add GooglePlacesCompanySearchProvider only if time remains
```

Hunter should be used first for B2B company discovery.

Typical Hunter-oriented ICP:

```text
Industry:
Software / Logistics

Location:
Egypt

Company size:
50–300 employees
```

Google Places should later be used for local-business ICPs.

Typical Google Places-oriented ICP:

```text
Business category:
Dental clinic

Location:
Cairo
```

The LLM provider must not be responsible for discovering company records.

The LLM may reason about the ICP, but application/infrastructure code owns provider selection and API execution.

The Lead Intelligence Agent should only depend on:

```text
CompanySearchPort
```

and should remain unchanged when the concrete provider changes.

---

# Web Research

Web research must be handled through:

```text
WebResearchPort
```

The provider may search:

```text
- Company websites
- Careers pages
- Public job postings
- News
- Public web search
```

It must return evidence that can be interpreted by the LLM.

The core agent should not depend on OpenAI-specific built-in browser tools.

---

# Buying Signal Detection

Buying signal detection should be split between evidence retrieval and LLM reasoning.

Workflow:

```text
WebResearchPort
        ↓
Verified evidence
        ↓
LLM
        ↓
Interpret relevance
        ↓
Structured BuyingSignal
```

Example:

```json
{
  "type": "hiring_growth",
  "evidence": "The company currently lists 18 open positions.",
  "source_url": "https://example.com/careers",
  "strength": "high"
}
```

The LLM must never invent buying signals without supporting evidence.

---

# Structured Output Strategy

Use Pydantic schemas for LLM outputs.

Prefer:

```text
LLM
↓
structured object
↓
Pydantic validation
```

over:

```text
LLM
↓
free-form text
↓
manual string parsing
```

The application must validate all LLM-generated structured outputs.

If a provider does not support strict schema enforcement natively, request JSON output and validate the response locally with Pydantic.

---

# Lead Scoring

The LLM must not calculate the final numeric lead score.

FastAPI returns classifications such as:

```text
ICP fit
Buying signal strength
Product relevance
Evidence quality
```

Laravel remains responsible for deterministic numeric scoring.

Example:

```text
ICP Match            40 points
Buying Signals       30 points
Product Relevance    20 points
Evidence Quality     10 points
```

This logic must remain outside the LLM.

---

# OpenAI Feature Compatibility

Before depending on an OpenAI feature, verify that the configured model supports:

```text
- Tool calling
- Structured output
- Responses API behavior
- Streaming
- Conversation state
- Reasoning controls
- Built-in tools
```

If an optional feature is unavailable, use application-owned tools instead.

---

# Hackathon Implementation Rule

Do not build all provider integrations before the MVP works.

The implementation priority is:

```text
Working end-to-end agent
        ↓
Reliable company search
        ↓
Reliable web research
        ↓
Structured prospect output
        ↓
Laravel integration
        ↓
OpenAI integration reliability
```

A working single-provider implementation is better than three incomplete provider integrations.

---

# Final Architecture

The preferred architecture is:

```text
                    FastAPI
                      │
               LeadIntelligenceAgent
                      │
          ┌───────────┼────────────┐
          ▼           ▼            ▼
       LLMPort   CompanySearch   WebResearch
          │           │            │
          ▼           ▼            ▼
   OpenAI SDK    Hunter / Google Places    Search Provider
          │
          ▼
       OpenAI API
```

Laravel remains responsible for:

```text
- Database
- Persistence
- Final scoring
- Client profiles
- ICP configuration
- Prospects
- Buying signals
- Agent run history
- Filament dashboard
```

FastAPI remains responsible for:

```text
- Agent orchestration
- LLM reasoning
- Company discovery
- Web research
- Evidence interpretation
- Buying signal interpretation
- Product relevance
- WHY NOW generation
```

The main design principle is:

> Keep the core agent provider-independent and own critical tools at the application level instead of depending on provider-specific built-in features.