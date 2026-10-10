"""Fetch fresh official texts for the 6 Oct 2026 corpus audit. Never touches laws/."""
import hashlib, json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
SOURCES = {
    # EU Publications Office (Cellar), the service behind EUR-Lex
    "gdpr_consolidated": "http://publications.europa.eu/resource/celex/02016R0679-20160504",
    "gdpr_oj": "http://publications.europa.eu/resource/celex/32016R0679",
    # eCFR (Office of the Federal Register): current XML and the API's latest-date index
    "ecfr_titles": "https://www.ecfr.gov/api/versioner/v1/titles.json",
    "ecfr_160": "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-45.xml?part=160",
    "ecfr_164": "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-45.xml?part=164",
    "ecfr_160_versions": "https://www.ecfr.gov/api/versioner/v1/versions/title-45.json?part=160",
    "ecfr_164_versions": "https://www.ecfr.gov/api/versioner/v1/versions/title-45.json?part=164",
    # Irish Statute Book (Office of the Attorney General) and Law Reform Commission revised Act
    "ie_dpa_enacted": "https://www.irishstatutebook.ie/eli/2018/act/7/enacted/en/print",
    "ie_dpa_revised": "https://revisedacts.lawreform.ie/eli/2018/act/7/revised/en/html",
    "ie_dpa_affecting": "https://www.irishstatutebook.ie/eli/isbc/2018_7.html",
    "ie_si_314_2018": "https://www.irishstatutebook.ie/eli/2018/si/314/made/en/print",
    "ie_si_188_2019": "https://www.irishstatutebook.ie/eli/2019/si/188/made/en/print",
    "ie_si_18_2021": "https://www.irishstatutebook.ie/eli/2021/si/18/made/en/print",
    # Added for audit finding 1 (Art. 9(3)): Medical Practitioners Act 2007 revised, Medical Council guide
    "ie_mpa_revised": "https://revisedacts.lawreform.ie/eli/2007/act/25/revised/en/html",
}
# The guide PDF is fetched with curl (see scripts/fetch_laws.py): Python's certificate store rejects the
# publisher's chain on some machines. Then: pdftotext -layout sources/mc_guide_2024.pdf sources/mc_guide_2024.txt
GUIDE_PDF = "https://www.medicalcouncil.ie/news-and-publications/publications/guide-to-professional-conduct-and-ethics-for-registered-medical-practitioners-2024.pdf"


def fetch(key, url):
    headers = {"User-Agent": "Mozilla/5.0 (thesis corpus audit)"}
    if key.startswith("ecfr"):
        headers["Accept-Encoding"] = "gzip"  # the eCFR full-text endpoint refuses uncompressed responses (HTTP 406)
    if key.startswith("gdpr"):
        headers.update({"Accept": "application/xhtml+xml", "Accept-Language": "eng"})
    rec = {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(url, headers=headers), timeout=90) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                import gzip
                body = gzip.decompress(body)
            rec.update(final_url=r.url, content_type=r.headers.get("Content-Type"))
        if b"Request Access" in body[:15000] or "unblock" in rec["final_url"]:
            raise ValueError("publisher access challenge")
        ext = ".json" if url.endswith(".json") or "json" in (rec["content_type"] or "") else \
              ".xml" if "xml" in url.split("?")[0][-4:] or "xml" in (rec["content_type"] or "") and "xhtml" not in (rec["content_type"] or "") else ".html"
        (HERE / "sources" / (key + ext)).write_bytes(body)
        rec.update(file=key + ext, sha256=hashlib.sha256(body).hexdigest(), bytes=len(body), status="retrieved")
    except Exception as exc:
        rec.update(status="failed", error=str(exc))
    print(key, rec["status"], rec.get("bytes", rec.get("error")), flush=True)
    return key, rec


if __name__ == "__main__":
    results = dict([fetch("ecfr_titles", SOURCES["ecfr_titles"])])
    titles = json.loads((HERE / "sources" / "ecfr_titles.json").read_text())
    date = next(t for t in titles["titles"] if t["number"] == 45)["up_to_date_as_of"]
    jobs = [(k, u.format(date=date)) for k, u in SOURCES.items() if k != "ecfr_titles"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results.update(pool.map(lambda j: fetch(*j), jobs))
    results["_ecfr_date"] = date
    (HERE / "sources.json").write_text(json.dumps(results, indent=2) + "\n")
