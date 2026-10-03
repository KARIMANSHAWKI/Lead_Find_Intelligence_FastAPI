# LLM analysis

The service uses the official `AsyncOpenAI` SDK and OpenAI API.

## Configuration

```env
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o-mini
```

`OPENAI_API_KEY` is only required by the agent endpoint, so `/health` remains
available without provider credentials.

## Hybrid tool workflow

Application code discovers candidates and applies deterministic ICP filters.
The LLM then calls `research_companies` to select at most
`AGENT_MAX_RESEARCH` filtered candidates. Application code executes that
research through `WebResearchPort`; the model never calls a vendor API
directly.

For each researched candidate, the LLM must call
`submit_prospect_analysis`. Its arguments follow the `ProspectAnalysis` schema.
The agent verifies that every buying signal uses an exact supplied evidence
quote and matching source URL, then applies deterministic qualification rules.

The LLM never calculates a numeric score. Laravel owns deterministic scoring.

Run tests with:

```bash
.venv/bin/python -m pytest -q
```
