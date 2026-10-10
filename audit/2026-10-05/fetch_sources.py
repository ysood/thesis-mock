"""Fetch immutable audit evidence; never overwrite the runtime law corpus."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
SOURCES = {
    "gdpr_articles": "http://publications.europa.eu/resource/celex/02016R0679-20160504",
    "gdpr_recitals": "http://publications.europa.eu/resource/celex/32016R0679",
    "hipaa_160": "https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-160",
    "hipaa_164": "https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164",
    "ie_dpa_revised": "https://revisedacts.lawreform.ie/eli/2018/act/7/revised/en/html",
    "ie_314_2018": "https://www.irishstatutebook.ie/eli/2018/si/314/made/en/print",
    "ie_188_2019": "https://www.irishstatutebook.ie/eli/2019/si/188/made/en/print",
    "ie_18_2021": "https://www.irishstatutebook.ie/eli/2021/si/18/made/en/print",
    "ie_amendment_index": "https://www.irishstatutebook.ie/eli/isbc/2018_7.html",
    "hhs_vacatur": "https://www.hhs.gov/hipaa/for-professionals/special-topics/reproductive-health/final-rule-fact-sheet/index.html",
    "hipaa_160_annual": "https://www.govinfo.gov/content/pkg/CFR-2025-title45-vol2/xml/CFR-2025-title45-vol2-part160.xml",
    "hipaa_164_annual": "https://www.govinfo.gov/content/pkg/CFR-2025-title45-vol2/xml/CFR-2025-title45-vol2-part164.xml",
}


def fetch(item):
    key, url = item
    headers = {"User-Agent": "Mozilla/5.0"}
    if key.startswith("gdpr"):
        headers.update({"Accept": "application/xhtml+xml", "Accept-Language": "eng"})
    result = {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(url, headers=headers), timeout=45) as response:
            body = response.read()
            result.update(final_url=response.url, content_type=response.headers.get("Content-Type"))
        # HTTP 200 can be a challenge page, which is not evidence of the statute.
        if "unblock.federalregister.gov" in result["final_url"] or b"Request Access" in body[:15000]:
            raise ValueError("Publisher access challenge, no legal text retrieved")
        suffix = ".xml" if key.endswith("_annual") else ".html"
        (HERE / "sources" / (key + suffix)).write_bytes(body)
        soup = BeautifulSoup(body, "html.parser")
        for el in soup(["script", "style"]):
            el.decompose()
        text = soup.get_text(" ", strip=True)
        (HERE / "sources" / (key + ".txt")).write_text(text)
        result.update(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body), status="retrieved")
    except Exception as exc:
        result.update(status="failed", error=str(exc))
    print(key, result["status"], result.get("bytes", result.get("error")), flush=True)
    return key, result


if __name__ == "__main__":
    (HERE / "sources").mkdir(parents=True, exist_ok=True)
    manifest = HERE / "sources.json"
    results = json.loads(manifest.read_text()) if manifest.exists() else {}
    pending = [(key, url) for key, url in SOURCES.items() if results.get(key, {}).get("status") != "retrieved"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results.update(pool.map(fetch, pending))
    (HERE / "sources.json").write_text(json.dumps(results, indent=2) + "\n")
