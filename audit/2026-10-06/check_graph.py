"""Grounding audit of reference/knowledge_graph.json against the corpus and fresh official texts.

1. Structural validation (kg.validate).
2. Every quote (edge provenance, openings, unit bases, national implementations): provision exists,
   quote occurs in the local provision, and in the fresh official text of the same unit.
3. Pinpoint: the quote occurs inside the official paragraph its pinpoint names (first level, e.g.
   Art. 9(2) -> paragraph 2; 164.512(f) -> paragraph (f); s. 52(1) -> subsection (1)).
4. Bundles: every requirement has one and every ID exists. Reachability: every node is reached from a requirement.
5. Edge inventory by kind; which edges carry a quote and which are authored or intake-policy links.
"""
import json, re, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1])); sys.path.insert(0, str(HERE))
from app import kg, knowledge as kb
import check_corpus as cc

eu, _ = cc.eu_units(); cfr = cc.cfr_units(); rev = cc.ie_revised()
si = {k: cc.soup(f"ie_si_{k}.html").get_text("\n") for k in ("314_2018", "188_2019", "18_2021")}
mpa = cc.ie_mpa(); guide = {"2024": (cc.S / "mc_guide_2024.txt").read_text()}
N = cc.norm

def official_unit(pid):
    kind, unit = cc.unit_of(pid)
    return kind, {"gdpr": eu, "cfr": cfr, "ie_dpa": rev, "ie_si": si, "ie_mpa": mpa, "mc_guide": guide}[kind].get(unit, "")

def _sequential(text, pattern, labels):
    """Split at markers that appear in order (a, b, c ... or 1, 2, 3 ...), so "(i)" or "(v)" inside
    a paragraph is not mistaken for paragraph i or v."""
    spans, want = [], 0
    for m in re.finditer(pattern, text):
        if want < len(labels) and m.group(1) == labels[want]:
            spans.append((labels[want], m.start())); want += 1
    return {lab: text[st:(spans[i + 1][1] if i + 1 < len(spans) else len(text))] for i, (lab, st) in enumerate(spans)}

LETTERS = [chr(c) for c in range(ord("a"), ord("z") + 1)]
NUMBERS = [str(n) for n in range(1, 60)]

def paragraph(kind, text, pinpoint):
    """Text of the first-level paragraph a pinpoint names, or None if not determinable."""
    if not pinpoint: return None
    if kind == "gdpr":
        m = re.match(r"\d+\((\d+)\)", pinpoint)
        return m and _sequential(text, r"(?m)^\s*(\d+)\.\s", NUMBERS).get(m.group(1))
    if kind == "cfr":
        m = re.match(r"(?:\d+\.\d+)?\(([a-z])\)", pinpoint)
        return m and _sequential(text, r"(?m)^\(([a-z])\)", LETTERS).get(m.group(1))
    if kind == "ie_dpa":
        m = re.match(r"(?:s\.\s*)?\d+[A-Z]?\((\d+)\)", pinpoint)
        return m and _sequential(text, r"(?:^|\s)\((\d+)\)\s", NUMBERS).get(m.group(1))
    return None

def quotes():
    g = kg.graph()
    for e in g["edges"]:
        if e.get("provenance"):
            yield {"where": f"{e['source']} -{e['type']}-> {e['target']}", **e["provenance"]}
    for n in g["nodes"].values():
        for role, q in (("opening", n.get("opening")), ("unit", (n.get("unit") or {}).get("basis"))):
            if q: yield {"where": f"{n['id']} [{role}]", **q}

def main():
    g = kg.graph(); provs = kb.provisions()
    out = {"validate": kg.validate(), "quotes": [], "pinpoint_unchecked": 0}
    for q in quotes():
        pid = q["provision"]
        rec = {"where": q["where"], "provision": pid, "pinpoint": q.get("pinpoint"), "quote": q.get("text", "")}
        rec["in_corpus"] = pid in provs
        rec["local_match"] = rec["in_corpus"] and N(q.get("text", "")) in N(provs[pid]["text"])
        kind, text = official_unit(pid)
        rec["official_match"] = bool(text) and N(q.get("text", "")) in N(text)
        para = paragraph(kind, text, q.get("pinpoint"))
        if para is None:
            rec["pinpoint_match"] = None; out["pinpoint_unchecked"] += 1
        else:
            rec["pinpoint_match"] = N(q.get("text", "")) in N(para)
        out["quotes"].append(rec)
    reqs = [n for n in g["nodes"].values() if n["type"] == "requirement"]
    out["bundles"] = {}
    for r in reqs:
        b = kg.bundle(r["id"])
        out["bundles"][r["id"]] = {"size": len(b), "unknown_ids": [p for p in b if p not in provs]}
    reach, stack = set(), [r["id"] for r in reqs]
    while stack:
        cur = stack.pop()
        if cur in reach: continue
        reach.add(cur)
        stack += [e["target"] for e in g["edges"] if e["source"] == cur]
        stack += [e["source"] for e in g["edges"] if e["target"] == cur and e["type"] in ("implemented_by",)]
    out["unreached_nodes"] = sorted(n for n, v in g["nodes"].items()
                                    if n not in reach and v["type"] not in ("provision", "request_value"))
    ungrounded = [n["id"] for n in g["nodes"].values() if n["type"] in ("condition", "route", "requirement", "concept")
                  and not any(e.get("provenance") for e in g["edges"] if e["source"] == n["id"] and e["type"] in ("grounded_in", "defined_in"))]
    out["nodes_without_quoted_source"] = ungrounded
    kinds = Counter((e["type"], bool(e.get("provenance"))) for e in g["edges"])
    out["edges"] = {f"{k}{' (quoted)' if q else ''}": v for (k, q), v in sorted(kinds.items())}
    out["node_types"] = dict(Counter(v["type"] for v in g["nodes"].values()))
    Q = out["quotes"]
    out["summary"] = {
        "nodes": len(g["nodes"]), "edges": len(g["edges"]), "node_types": out["node_types"],
        "validate_issues": len(out["validate"]), "quotes": len(Q),
        "missing_provision": sum(not q["in_corpus"] for q in Q),
        "local_mismatch": sum(not q["local_match"] for q in Q),
        "official_mismatch": sum(not q["official_match"] for q in Q),
        "pinpoint_checked": sum(q["pinpoint_match"] is not None for q in Q),
        "pinpoint_mismatch": sum(q["pinpoint_match"] is False for q in Q),
        "bundles_with_unknown_ids": [k for k, v in out["bundles"].items() if v["unknown_ids"]],
        "unreached_nodes": len(out["unreached_nodes"]),
        "nodes_without_quoted_source": len(ungrounded),
        "edges": out["edges"]}
    (HERE / "graph_check.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out["summary"], indent=1))
    for q in Q:
        if not (q["in_corpus"] and q["local_match"] and q["official_match"]) or q["pinpoint_match"] is False:
            print("ISSUE", q["where"], q["provision"], q["pinpoint"], "local", q["local_match"], "off", q["official_match"], "pin", q["pinpoint_match"], "|", q["quote"][:90])
    print("UNREACHED", out["unreached_nodes"]); print("NO QUOTED SOURCE", ungrounded); print("VALIDATE", out["validate"][:10])

if __name__ == "__main__":
    main()
