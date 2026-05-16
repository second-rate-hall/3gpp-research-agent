from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass


USER_AGENT = "3gpp-research-agent-patent-tool/0.1"


@dataclass
class PatentHit:
    title: str
    url: str
    snippet: str = ""


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_tags(text: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def search_patents(query: str, limit: int = 5) -> list[dict[str, str]]:
    xhr = "https://patents.google.com/xhr/query?url=q%3D" + urllib.parse.quote(query)
    try:
        data = json.loads(fetch_url(xhr))
        results: list[PatentHit] = []
        for cluster in data.get("results", {}).get("cluster", []):
            for item in cluster.get("result", []):
                patent = item.get("patent", {})
                patent_id = item.get("id", "")
                if not patent_id:
                    continue
                url = urllib.parse.urljoin("https://patents.google.com/", patent_id)
                results.append(
                    PatentHit(
                        title=strip_tags(patent.get("title", "")),
                        url=url,
                        snippet=strip_tags(patent.get("snippet", "")),
                    )
                )
                if len(results) >= limit:
                    return [asdict(hit) for hit in results]
    except Exception:
        pass

    page = fetch_url("https://patents.google.com/?q=" + urllib.parse.quote(query))
    hits: list[PatentHit] = []
    for match in re.finditer(r'<a[^>]+href="(/patent/[^"]+)"[^>]*>(.*?)</a>', page, flags=re.I | re.S):
        href, title_html = match.groups()
        title = strip_tags(title_html)
        if not title or len(title) < 8:
            continue
        patent_url = urllib.parse.urljoin("https://patents.google.com", href)
        if any(hit.url == patent_url for hit in hits):
            continue
        hits.append(PatentHit(title=title, url=patent_url))
        if len(hits) >= limit:
            break
    return [asdict(hit) for hit in hits]


def extract_background(page: str) -> str:
    patterns = [
        r'<section[^>]+itemprop="description"[^>]*>(.*?)</section>',
        r'<heading[^>]*>\s*Background\s*</heading>(.*?)(?:<heading|</section>)',
        r'BACKGROUND(?: OF THE INVENTION)?(.*?)(?:SUMMARY|BRIEF DESCRIPTION|DETAILED DESCRIPTION)',
    ]
    for pattern in patterns:
        match = re.search(pattern, page, flags=re.I | re.S)
        if match:
            text = strip_tags(match.group(1))
            if len(text) > 120:
                return text[:5000]
    text = strip_tags(page)
    idx = text.lower().find("background")
    if idx >= 0:
        return text[idx : idx + 5000]
    return text[:3000]


def fetch_patent_background(url: str) -> dict[str, str]:
    page = fetch_url(url)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.I | re.S)
    title = strip_tags(title_match.group(1)) if title_match else url
    return {
        "url": url,
        "title": title,
        "background": extract_background(page),
        "evidence_status": "auxiliary_background_not_3gpp_standard_evidence",
    }


def dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
