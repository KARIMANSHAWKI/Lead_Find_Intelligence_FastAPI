import asyncio
import ipaddress
import logging
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.core.exceptions import ProviderError, ProviderResponseError, ProviderTimeoutError
from app.domain.models.company import Company
from app.domain.models.company_research import CompanyResearch, ResearchEvidence
from app.domain.ports.web_research import WebResearchPort

logger = logging.getLogger(__name__)

# Patterns that indicate buying signals
SIGNAL_PATTERNS = {
    "hiring_growth": [
        r"we.?re\s+hiring",
        r"join\s+our\s+team",
        r"career\s+opportunities",
        r"open\s+positions?",
        r"\d+\s+(?:new\s+)?(?:job|position|role)s?\s+(?:available|open)",
        r"growing\s+(?:our\s+)?team",
    ],
    "expansion": [
        r"new\s+(?:office|location|branch|headquarters)",
        r"expand(?:ing|ed|s)?\s+(?:to|into|our)",
        r"open(?:ing|ed)?\s+(?:a\s+)?new",
        r"launching\s+in",
        r"entering\s+(?:the\s+)?(?:\w+\s+)?market",
    ],
    "funding": [
        r"(?:raised|secured|closed)\s+\$?\d+",
        r"series\s+[a-e]\s+(?:funding|round)",
        r"(?:seed|venture)\s+(?:funding|capital|investment)",
        r"investor[s]?\s+(?:include|led\s+by)",
    ],
    "growth": [
        r"year[- ]over[- ]year\s+growth",
        r"(?:revenue|sales)\s+(?:growth|increase)",
        r"(?:\d+%|\d+\s+percent)\s+growth",
        r"fastest[- ]growing",
        r"doubled\s+(?:our|the)",
    ],
    "product_launch": [
        r"(?:launching|introducing|announcing)\s+(?:our\s+)?(?:new|latest)",
        r"new\s+product\s+(?:line|launch|release)",
        r"(?:product|service)\s+announcement",
    ],
}


class _Page(HTMLParser):
    """HTML parser that extracts text content and links."""
    
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self.hidden = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)
        if tag in {"p", "div", "li", "h1", "h2", "h3", "br", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()
        if not self.hidden:
            self.parts.append(data)


async def _public_ip(host: str, port: int) -> str:
    records = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = [ipaddress.ip_address(record[4][0]) for record in records]
    if not addresses or any(not address.is_global for address in addresses):
        raise ProviderResponseError("Research requires a public website address.")
    return str(addresses[0])


class WebSearchResearchProvider(WebResearchPort):
    """Bounded official-site retrieval; no search engine or social scraping.
    
    This provider crawls company websites to extract evidence for buying signals.
    It prioritizes careers pages, news/press releases, and about pages.
    """

    def __init__(self, max_pages: int = 4, max_evidence: int = 8,
                 client: httpx.AsyncClient | None = None, resolver=None) -> None:
        self._max_pages = max_pages
        self._max_evidence = max_evidence
        self._client = client
        self._resolver = resolver or _public_ip
        self._signal_patterns = {
            signal_type: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for signal_type, patterns in SIGNAL_PATTERNS.items()
        }

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> tuple[str, str]:
        current_url = url
        visited: set[str] = set()

        for _ in range(4):
            if current_url in visited:
                raise ProviderResponseError("Research redirect loop detected.")
            visited.add(current_url)

            parsed = urlsplit(current_url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.port not in {None, 80, 443}
            ):
                raise ProviderResponseError(
                    "Research URL must be a public HTTP website."
                )
            if any(
                parsed.hostname == host or parsed.hostname.endswith("." + host)
                for host in ("linkedin.com", "facebook.com", "instagram.com")
            ):
                raise ProviderResponseError("Social sites are excluded from research.")

            try:
                literal_address = ipaddress.ip_address(parsed.hostname)
            except ValueError:
                literal_address = None
            if literal_address is not None and not literal_address.is_global:
                raise ProviderResponseError(
                    "Research requires a public website address."
                )

            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            address = await asyncio.wait_for(
                self._resolver(parsed.hostname, port), timeout=10
            )
            # Pin every redirect hop to a freshly validated public IP.
            authority = f"[{address}]" if ":" in address else address
            pinned = parsed._replace(
                netloc=f"{authority}:{port}", fragment=""
            ).geturl()
            async with client.stream(
                "GET",
                pinned,
                headers={
                    "Host": parsed.netloc,
                    "User-Agent": "LeadIntelligenceResearch/1.0",
                },
                extensions={"sni_hostname": parsed.hostname},
                timeout=10,
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ProviderResponseError(
                            "Research redirect is missing a destination."
                        )
                    current_url = urljoin(current_url, location)
                    continue

                response.raise_for_status()
                chunks = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 250_000:
                        raise ProviderResponseError(
                            "Research page exceeds the size budget."
                        )
                    chunks.append(chunk)
                return (
                    b"".join(chunks).decode("utf-8", errors="replace"),
                    response.headers.get("content-type", ""),
                )

        raise ProviderResponseError("Research exceeded the redirect limit.")

    async def research(self, company: Company) -> CompanyResearch:
        result = CompanyResearch(company_name=company.name, website=company.website)
        if not company.website:
            return result
        try:
            if self._client is not None:
                return await self._research(self._client, company, result)
            async with httpx.AsyncClient(trust_env=False) as client:
                return await self._research(client, company, result)
        except (httpx.TimeoutException, TimeoutError):
            raise ProviderTimeoutError("Company website research timed out.") from None
        except (httpx.HTTPError, OSError, ValueError):
            raise ProviderError("Company website research failed.") from None

    async def _research(self, client, company, result):
        """Research a company website to extract evidence for buying signals."""
        root = company.website
        origin = urlsplit(root)
        robots_url = urljoin(root, "/robots.txt")
        
        logger.info("web_research_started", extra={
            "company": company.name,
            "website": root,
        })
        
        try:
            robots_text, _ = await self._fetch(client, robots_url)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 404:
                raise
            robots_text = ""
        
        robots = RobotFileParser()
        robots.parse(robots_text.splitlines())
        
        urls = [root]
        visited = set()
        seen_text = set()
        page_failures = 0
        successful_pages = 0
        homepage_evidence: list[ResearchEvidence] = []
        priority_evidence: list[ResearchEvidence] = []
        
        while urls and len(visited) < self._max_pages:
            url = urls.pop(0)
            if url in visited:
                continue
            visited.add(url)
            
            if not robots.can_fetch("LeadIntelligenceResearch", url):
                continue
            
            try:
                html, content_type = await self._fetch(client, url)
            except httpx.HTTPStatusError as error:
                if error.response.status_code not in {404, 410}:
                    page_failures += 1
                continue
            except ProviderResponseError:
                continue
            
            if "text/html" not in content_type:
                continue
            
            successful_pages += 1
            page = _Page()
            page_evidence_count = 0
            page.feed(html)
            
            path = urlsplit(url).path.casefold()
            source_type = self._determine_source_type(path)
            collected = homepage_evidence if path in {"", "/"} else priority_evidence
            full_text = "".join(page.parts)

            for line in full_text.splitlines():
                text = " ".join(line.split())
                if len(text) < 40 or text in seen_text:
                    continue
                seen_text.add(text)
                collected.append(ResearchEvidence(
                    text=text[:1500],
                    source_url=url,
                    source_type=source_type,
                ))
                page_evidence_count += 1
                if page_evidence_count >= self._max_evidence:
                    break
            
            # Extract and prioritize links
            links = self._extract_priority_links(page.links, url, origin)
            urls.extend(link for link in links if link not in visited and link not in urls)
        
        if page_failures and not successful_pages:
            raise ProviderError("Company research pages were unavailable.")
        
        ordered = self._prioritize_evidence(priority_evidence)
        remaining = self._max_evidence - len(ordered)
        if remaining > 0:
            ordered.extend(self._prioritize_evidence(homepage_evidence)[:remaining])
        result.evidence = ordered[: self._max_evidence]
        
        logger.info("web_research_completed", extra={
            "company": company.name,
            "evidence_count": len(result.evidence),
            "pages_visited": successful_pages,
        })
        
        return result

    def _determine_source_type(self, path: str) -> str:
        """Determine the source type based on URL path."""
        if any(word in path for word in ("career", "jobs", "hiring", "join-us", "work-with-us")):
            return "careers"
        if any(word in path for word in ("news", "press", "blog", "announcement", "release")):
            return "announcement"
        if any(word in path for word in ("about", "company", "team", "leadership")):
            return "company_info"
        if any(word in path for word in ("location", "office", "contact", "branch")):
            return "locations"
        return "company_website"

    def _score_evidence(self, text: str) -> int:
        """Score evidence text by matching signal patterns."""
        score = 0
        for signal_type, patterns in self._signal_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    score += 1
                    break  # Only count once per signal type
        return score

    def _extract_priority_links(self, links: list[str], base_url: str, origin) -> list[str]:
        """Extract and prioritize links from a page."""
        processed = []
        for link in links:
            full_url = urljoin(base_url, link).split("#")[0]
            parsed = urlsplit(full_url)
            
            # Only follow links on the same origin
            if parsed.netloc != origin.netloc or parsed.scheme != origin.scheme:
                continue
            
            # Skip URLs with query strings (often dynamic/duplicate content)
            if parsed.query:
                continue
            
            processed.append(full_url)
        
        # Prioritize signal-relevant pages
        priority_words = ("career", "jobs", "hiring", "news", "press", "about", 
                         "team", "locations", "office", "blog", "announcement")
        processed.sort(
            key=lambda link: not any(word in link.casefold() for word in priority_words)
        )
        
        return processed[:20]

    def _prioritize_evidence(self, evidence: list[ResearchEvidence]) -> list[ResearchEvidence]:
        """Prioritize evidence by source type and signal relevance."""
        def sort_key(item: ResearchEvidence) -> tuple:
            # Priority order: careers, announcements, company_info, locations, other
            type_priority = {
                "careers": 0,
                "announcement": 1,
                "company_info": 2,
                "locations": 3,
                "company_website": 4,
            }
            type_score = type_priority.get(item.source_type, 5)
            
            # Higher signal score = lower sort value (comes first)
            signal_score = -self._score_evidence(item.text)
            
            return (type_score, signal_score)
        
        return sorted(evidence, key=sort_key)
