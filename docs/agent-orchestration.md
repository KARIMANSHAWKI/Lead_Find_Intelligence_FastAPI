# Evidence-based agent orchestration

`POST /api/v1/agent/run` calls `RunLeadIntelligence`, then one
`LeadIntelligenceAgent` depending on `CompanySearchPort`, `WebResearchPort`,
and `LLMPort`. Routes contain no discovery or qualification logic.

The agent searches Hunter, deduplicates candidates and skips known ICP
mismatches. Remaining companies are researched sequentially. Official-site
evidence with public source URLs is passed to the configured LLM along with
company data and client ICP through the OpenAI API.

Every signal must quote a retrieved evidence item exactly and match its URL.
Unsupported analysis is rejected. Qualification requires high ICP fit, high
or medium product relevance, medium or high evidence quality, and at least one
medium or high verified signal. No evidence means rejection without an LLM call.
WHY NOW publishes the verified signal quotes in the context of the client product,
rather than arbitrary generated urgency claims. No numeric score is produced.

After a prospect qualifies, Hunter Domain Search enriches it with up to
`CONTACT_MAX_PEOPLE` decision-maker contacts plus available generic company
emails and phone numbers. Contact lookup failures leave `contact_info` empty and
do not discard the qualified prospect.

Per-company research/analysis errors are logged by type and processing continues.
Global configuration/authentication/rate-limit errors propagate. If all attempted
work fails operationally, the run fails instead of returning a misleading empty
result. Logs contain counts and reasons, never credentials or provider payloads.

Limits: `AGENT_MAX_CANDIDATES=10`, `RESEARCH_MAX_PAGES=4`,
`RESEARCH_MAX_EVIDENCE=8`. Research reads up to four official HTML pages plus
robots.txt. It respects robots.txt, excludes social sites, pins public DNS
addresses, refuses redirects, and caps response bytes. Careers/news pages are
prioritized. This implementation does not use a search engine, execute JavaScript,
or parse publication dates; undated or old content must not imply recent urgency.
