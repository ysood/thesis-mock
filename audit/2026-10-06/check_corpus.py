"""Compare every provision in laws/*.md with the fresh official texts in sources/.

Matching ignores case, spacing and punctuation but keeps word and number order. Each local
provision is split into lines; a line matches if it occurs inside the official unit it claims to be.
Completeness: for whole units (GDPR articles/recitals, CFR sections, Irish sections) the official
paragraphs are checked against the local text too, so omissions show up.
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from app import knowledge as kb

S = HERE / "sources"
def norm(t):
    t = kb.normalise_text(t)
    return re.sub(r"[^a-z0-9]", "", t)

def soup(name):
    return BeautifulSoup((S / name).read_bytes(), "html.parser")

def eu_units():
    cons, oj = soup("gdpr_consolidated.html"), soup("gdpr_oj.html")
    units = {}
    for el in cons.find_all(id=re.compile(r"^art_\d+$")):
        units[f"Art. {el['id'][4:]}"] = el.get_text("\n", strip=True)
    for el in oj.find_all(id=re.compile(r"^rct_\d+$")):
        units[f"Recital {el['id'][4:]}"] = el.get_text("\n", strip=True)
    oj_articles = {f"Art. {el['id'][4:]}": el.get_text("\n", strip=True) for el in oj.find_all(id=re.compile(r"^art_\d+$"))}
    return units, oj_articles

def cfr_units():
    units = {}
    for p in (160, 164):
        for sec in ET.parse(S / f"ecfr_{p}.xml").getroot().iter("DIV8"):
            units[sec.get("N")] = "\n".join(t.strip() for t in sec.itertext() if t.strip())
    return units

def ie_revised():
    s = soup("ie_dpa_revised.html")
    return {el["id"][3:]: el.get_text("\n", strip=True) for el in s.find_all(id=re.compile(r"^SEC\d+[A-Z]?$"))}

def unit_of(pid):
    if pid.startswith("GDPR"):
        m = re.match(r"GDPR (Art\. \d+|Recital \d+)", pid); return "gdpr", m.group(1)
    if pid.startswith("45 CFR"):
        return "cfr", re.match(r"45 CFR (\d+\.\d+)", pid).group(1)
    if pid.startswith("IE DPA"):
        return "ie_dpa", re.search(r"s\. (\d+[A-Z]?)", pid).group(1)
    if pid.startswith("IE MPA"):
        return "ie_mpa", re.search(r"s\. (\d+[A-Z]?)", pid).group(1)
    if pid.startswith("IE MC Guide"):
        return "mc_guide", "2024"
    m = re.search(r"S\.I\. (\d+)/(\d{4})", pid); return "ie_si", f"{m.group(1)}_{m.group(2)}"

def ie_mpa():
    """Revised sections with the LRC amendment markers (F21 [ ... ]) removed: they annotate, not legislate."""
    s = soup("ie_mpa_revised.html")
    return {el["id"][3:]: re.sub(r"\bF\d+\s*\[", "", el.get_text("\n", strip=True))
            for el in s.find_all(id=re.compile(r"^SEC\d+[A-Z]?$"))}

def lines(text):
    out = []
    for ln in text.split("\n"):
        ln = re.sub(r"^\s*>.*$", "", ln).strip()
        if ln.startswith("**[Footnote") or not ln:
            continue
        out.append(ln)
    return out

def main():
    eu, eu_oj_art = eu_units(); cfr = cfr_units(); rev = ie_revised()
    enacted = norm(soup("ie_dpa_enacted.html").get_text("\n"))
    si = {k: norm(soup(f"ie_si_{k}.html").get_text("\n")) for k in ("314_2018", "188_2019", "18_2021")}
    mpa = ie_mpa(); guide = norm((S / "mc_guide_2024.txt").read_text())
    provs = kb.provisions()
    report = {"provisions": {}, "unit_coverage": {}, "missing_units": {}}
    by_unit = defaultdict(list)
    for pid, p in provs.items():
        kind, unit = unit_of(pid)
        by_unit[(kind, unit)].append(pid)
        if kind == "gdpr": official = norm(eu.get(unit, ""))
        elif kind == "cfr": official = norm(cfr.get(unit, ""))
        elif kind == "ie_dpa": official = enacted
        elif kind == "ie_mpa": official = norm(mpa.get(unit, ""))
        elif kind == "mc_guide": official = guide
        else: official = si[unit]
        ls = lines(p["text"])
        bad = [l for l in ls if norm(l) and norm(l) not in official]
        rec = {"lines": len(ls), "unmatched": bad[:5], "unmatched_count": len(bad)}
        if kind == "ie_dpa":  # also against the revised (amended) text of the same section
            r = norm(rev.get(unit, ""))
            rec["unmatched_vs_revised"] = [l for l in ls if norm(l) and norm(l) not in r][:8]
            rec["unmatched_vs_revised_count"] = sum(1 for l in ls if norm(l) and norm(l) not in r)
        report["provisions"][pid] = rec
    # Completeness: every official paragraph of a covered unit appears in the local text.
    for (kind, unit), pids in by_unit.items():
        local = norm("\n".join(provs[p]["text"] for p in pids) + "\n" + "\n".join(provs[p]["title"] for p in pids))
        if kind == "gdpr": src = eu.get(unit, "")
        elif kind == "cfr": src = cfr.get(unit, "")
        elif kind == "ie_dpa": src = rev.get(unit, "")
        else: continue
        paras = [l for l in src.split("\n") if len(norm(l)) > 25]
        miss = [l for l in paras if norm(l) not in local]
        report["unit_coverage"][f"{kind}:{unit}"] = {"official_paragraphs": len(paras), "not_in_local": len(miss), "examples": miss[:4]}
    # Units in the official instrument that the corpus lacks.
    have = {u for k, u in by_unit if k == "gdpr"}
    report["missing_units"]["gdpr"] = sorted(set(eu) - have, key=lambda x: (x.split()[0], int(x.split()[1])))
    have = {u for k, u in by_unit if k == "cfr"}
    report["missing_units"]["cfr"] = sorted(u for u in set(cfr) - have)
    report["gdpr_oj_vs_consolidated_articles_differ"] = [a for a in eu_oj_art if norm(eu_oj_art[a]) != norm(eu.get(a, ""))]
    bad = {k: v for k, v in report["provisions"].items() if v["unmatched_count"]}
    summary = {"provisions": len(provs), "provisions_with_unmatched_lines": len(bad),
               "units": len(report["unit_coverage"]),
               "units_with_official_text_missing_locally": {k: v["not_in_local"] for k, v in report["unit_coverage"].items() if v["not_in_local"]},
               "missing_units": {k: len(v) for k, v in report["missing_units"].items()},
               "ie_dpa_changed_since_enactment": {k: v["unmatched_vs_revised_count"] for k, v in report["provisions"].items() if v.get("unmatched_vs_revised_count")}}
    report["summary"] = summary
    (HERE / "corpus_check.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1))
    for k, v in bad.items(): print("UNMATCHED", k, v["unmatched"][:2])

if __name__ == "__main__":
    main()
