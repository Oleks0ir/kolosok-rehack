from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date
from urllib.parse import urlparse

from app.models import EvidenceItem
from app.settings import env


def _reliability(url: str, search_score: float) -> float:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if host.endswith(("bmwgroup.com", "bmw.com", "bmw.de")):
        authority = 0.92
    elif host.endswith(("gov", "europa.eu", "edu")):
        authority = 0.9
    elif host.endswith(("adac.de", "whatcar.com", "autocar.co.uk", "caranddriver.com")):
        authority = 0.8
    elif host.endswith(("reddit.com", "forum", "forums")):
        authority = 0.48
    else:
        authority = 0.65
    score = min(1.0, max(0.0, search_score))
    return round(min(0.95, max(0.3, authority * 0.65 + score * 0.35)), 2)


def search_web(queries: list[str], profile: dict) -> tuple[list[EvidenceItem], str]:
    key = env("TAVILY_API_KEY")
    if not key:
        return [], "Tavily is not configured; web enrichment was skipped."
    output: list[EvidenceItem] = []
    seen: set[str] = set()
    for query in queries[:3]:
        body = json.dumps({
            "query": query,
            "max_results": 4,
            "search_depth": "basic",
            "include_raw_content": True,
        }).encode()
        request = urllib.request.Request(
            "https://api.tavily.com/search",
            data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                results = json.loads(response.read().decode("utf-8")).get("results", [])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return output, "Tavily request failed; saved results are retained."
        for result in results:
            url = str(result.get("url", "")).strip()
            if not url or url in seen:
                continue
            seen.add(url)
            text = str(result.get("raw_content") or result.get("content") or "").strip()[:6000]
            if not text:
                continue
            try:
                score = float(result.get("score", 0.5) or 0.5)
            except (TypeError, ValueError):
                score = 0.5
            output.append(EvidenceItem(
                source_type="web",
                source_ref=url,
                market=profile.get("market", "Germany"),
                model=profile.get("model", "BMW 5 Series"),
                date=str(result.get("published_date") or date.today().isoformat())[:32],
                text_or_value=f"{str(result.get('title') or '').strip()} — {text}",
                reliability=_reliability(url, score),
            ))
    return output, f"Added {len(output)} dated web sources from Tavily."
