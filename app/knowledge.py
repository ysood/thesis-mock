"""Supporting layer: the law corpus, a small knowledge graph, vector search
and reference facts about countries.

Nothing here decides a legal question. It only stores and finds the official
texts, and records structure that can be read off the texts themselves
(which provision cites which, which GDPR provisions mention Member State law).
"""

import hashlib
import json
import re
import threading
from functools import lru_cache
from pathlib import Path

import pycountry

ROOT = Path(__file__).resolve().parent.parent
LAWS = ROOT / "laws"
CHROMA_DIR = ROOT / ".chroma"
EMBEDDING_TOKEN_LIMIT = 256  # Chroma's default all-MiniLM-L6-v2, including special tokens
CHUNKING_VERSION = "legal-boundaries-v1"

# Which file feeds which knowledge base. "IE" is the only national (local) law.
LAW_FILES = {
    "gdpr.md": "GDPR",
    "hipaa.md": "HIPAA",
    "ie_health_research_regulations.md": "IE",
    "ie_data_protection_act_2018.md": "IE",
    "ie_medical_practitioners_act_2007.md": "IE",
    "ie_health_identifiers_act_2014.md": "IE",
    "ie_medical_practitioners_definitions_2007.md": "IE",
    "ie_medical_council_guide_2024.md": "IE",  # a competent body's rules (GDPR Art. 9(3)), not legislation
    "ie_dpc_dpia_list_2018.md": "IE",  # supervisory-authority list under GDPR Art. 35(4)
}
LOCAL_LAW_COUNTRIES = {"IE"}


# ------------------------------------------------------------- provisions

@lru_cache
def provisions():
    """All provisions, keyed by citation ID, e.g. "GDPR Art. 9"."""
    result = {}
    for filename, regime in LAW_FILES.items():
        text = (LAWS / filename).read_text(encoding="utf-8")
        source = re.search(r"^> Official text: (.+)$", text, re.M).group(1)
        for match in re.finditer(r"^## \[(.+?)\] (.+?)\n(.*?)(?=^## \[|\Z)", text, re.M | re.S):
            pid, title, body = match.group(1), match.group(2), match.group(3).strip()
            result[pid] = {"id": pid, "title": title, "text": body, "regime": regime, "source": source, "file": filename}
    return result


def normalise_text(text):
    """Comparable form of a quote or law text: case, quotes, dashes and spacing ignored."""
    text = text.lower().replace("\xa0", " ")
    text = re.sub(r"[‘’´`]", "'", text)
    text = re.sub(r"[“”]", '"', text)
    text = re.sub(r"[‐‑‒–—]", "-", text)
    # Source scrapes sometimes break a line inside a linked reference ("section 42\n,"); spacing
    # around punctuation is not meaningful when comparing a quote with the text.
    text = re.sub(r"\s+([,.;:)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    return re.sub(r"\s+", " ", text).strip(" .;,")


def normalise_id(citation):
    """Tidy common variations, e.g. "Article 9(2)" -> "Art. 9(2)"."""
    text = citation.strip().strip("[]").replace("§", "")
    text = re.sub(r"\bArticle\s+", "Art. ", text)
    text = re.sub(r"\bArt\.?\s*", "Art. ", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower()


@lru_cache
def legal_status_notes():
    """Dated publisher notices affecting the operation of retained statutory text."""
    return json.loads((ROOT / "reference" / "legal_status.json").read_text())["notes"]


def source_status_notes(ids):
    wanted = set(ids)
    return [note for note in legal_status_notes()
            if any(wanted & set(resolve(pid, provisions())) for pid in note["provisions"])]


def resolve(citation, allowed_ids):
    """Map a citation to the provision IDs it refers to, within allowed_ids.

    "GDPR Art. 9(2)(j)" resolves to "GDPR Art. 9"; "45 CFR 164.514" resolves
    to every allowed chunk of that section. Returns [] if nothing matches.
    """
    wanted = normalise_id(citation)
    allowed = {normalise_id(pid): pid for pid in allowed_ids}
    if wanted in allowed:
        return [allowed[wanted]]
    # A sub-paragraph of an allowed provision: "... art. 9" + "(2)(j)".
    for key in sorted(allowed, key=len, reverse=True):
        if wanted.startswith(key) and wanted[len(key):].startswith("("):
            return [allowed[key]]
    # A whole section when only its chunks are allowed.
    return [pid for key, pid in allowed.items()
            if key.startswith(wanted) and key[len(wanted):].startswith((" [", "(", " ("))]


# ------------------------------------------------------------- knowledge graph

@lru_cache
def legal_relationships():
    return json.loads((ROOT / "reference" / "legal_relationships.json").read_text())


def article_references(text):
    """Expand numbered Article lists/ranges without reading paragraph numbers as articles."""
    references = set()
    number = r"\d+(?:\([0-9a-z]+\))*"
    pattern = rf"\bArticles?\s+({number}(?:\s*(?:,|and|or|to|[-–])\s*{number})*)"
    for expression in re.findall(pattern, text):
        references.update(re.findall(number, expression))
        plain = re.sub(r"\([0-9a-z]+\)", "", expression)
        for first, last in re.findall(r"(\d+)\s*(?:to|[-–])\s*(\d+)", plain):
            if 1 <= int(first) <= int(last) <= 99:
                references.update(str(n) for n in range(int(first), int(last) + 1))
    return references

def curated_links(links, all_ids, label):
    """(source, target) pairs from relationships.json, rejecting links to provisions not in the corpus."""
    for link in links:
        source, target = link["source"], link["target"]
        if source not in all_ids or target not in all_ids:
            raise ValueError(f"{label} references a missing provision: {source} -> {target}")
        yield source, target


def gdpr_citations(text, all_ids):
    # "Article 89(1)", "Articles 45 and 46", "Articles 15 to 22": keep the
    # article numbers, not the paragraph numbers in brackets.
    # Art. 4 is split into definitions; retain all matching chunks.
    return {t for number in article_references(text) for t in resolve(f"GDPR Art. {number}", all_ids)}


def hipaa_citations(text, all_ids):
    return {t for section, para in re.findall(r"(16[04]\.\d{3})(\([a-z]\))?", text)
            for t in resolve(f"45 CFR {section}{para}", all_ids)}


def ie_citations(pid, text, all_ids, amending, relationships):
    targets = set()
    for number in re.findall(r"Regulations? (\d+[A-Z]?)", text):
        instrument = pid.split(" Reg.")[0] if " Reg." in pid else "IE S.I. 314/2018"
        # References in the curated amending provisions concern the
        # principal instrument, including text inserted into that law.
        if amending:
            instrument = relationships["principal_instruments"].get(instrument, instrument)
        target = f"{instrument} Reg. {number}"
        targets.add(relationships["inserted_provisions"].get(target, target))
    for number in re.findall(r"section (\d+)", text):
        instrument = pid.split(' s. ')[0] if ' s. ' in pid else 'IE DPA 2018'
        targets.add(f"{instrument} s. {number}")
    return targets & all_ids


@lru_cache
def graph():
    """Edges read off the texts: cites[a] = provisions that a's text refers to."""
    all_ids = set(provisions())
    cites = {pid: set() for pid in all_ids}
    defers_to_national_law = set()
    relationships = legal_relationships()
    amends = {pid: set() for pid in all_ids}
    amended_by = {pid: set() for pid in all_ids}
    dependencies = {pid: set() for pid in all_ids}
    for source, target in curated_links(relationships.get('definitions', []), all_ids, 'Definition link'):
        dependencies[source].add(target)
        cites[source].add(target)
    for source, target in curated_links(relationships["amendments"], all_ids, 'Curated amendment link'):
        amends[source].add(target)
        amended_by[target].add(source)
        cites[source].add(target)

    for pid, p in provisions().items():
        text, regime = p["text"], p["regime"]
        if regime in ("GDPR", "IE"):
            cites[pid] |= gdpr_citations(text, all_ids)
        if regime == "GDPR" and re.search(r"Member State law", text):
            defers_to_national_law.add(pid)
        if regime == "HIPAA":
            cites[pid] |= hipaa_citations(text, all_ids)
        if regime == "IE":
            cites[pid] |= ie_citations(pid, text, all_ids, amends[pid], relationships)
        cites[pid].discard(pid)

    cited_by = {pid: set() for pid in all_ids}
    for source, targets in cites.items():
        for target in targets:
            cited_by[target].add(source)
    return {"cites": cites, "cited_by": cited_by, "amends": amends, "amended_by": amended_by,
            "definitions": dependencies,
            "defers_to_national_law": defers_to_national_law}


def include_amendments(ids):
    """Keep a retrieved provision and its known amendment family together.

    This may exceed the base source-count cap. Do not silently truncate required
    amendments. These structural links do not settle effective-date questions.
    """
    result = list(dict.fromkeys(ids))
    relations = graph()
    for pid in result:
        related = relations["amends"][pid] | relations["amended_by"][pid]
        for target in sorted(related):
            if target not in result:
                result.append(target)
    return result


def include_supporting_sources(ids):
    """Include amendments and explicitly curated definition dependencies, with cycle protection.

    This follows legal source links, never case predicates. It does not expand
    every citation, and it cannot fetch a law missing from the local corpus.
    """
    result = include_amendments(ids)
    definitions = graph()['definitions']
    for pid in result:
        for target in sorted(definitions[pid]):
            for related in include_amendments([target]):
                if related not in result:
                    result.append(related)
    return result


# ------------------------------------------------------------- vector search

_store = None
_store_lock = threading.Lock()  # the parallel specialists must not open the store twice


def vector_store():
    """Chroma collection of bounded legal-text chunks, each tagged with its provision."""
    global _store
    with _store_lock:
        if _store is None:
            _store = open_store()
        return _store


def open_store():
    from langchain_chroma import Chroma

    store = Chroma(collection_name="laws", persist_directory=str(CHROMA_DIR))
    windows = list(text_windows())
    fingerprint = hashlib.sha256(json.dumps(
        [CHUNKING_VERSION, windows], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    metadata = store._collection.metadata or {}
    if store._collection.count() != len(windows) or metadata.get("chunk_fingerprint") != fingerprint:
        store.reset_collection()
        for start in range(0, len(windows), 200):
            batch = windows[start:start + 200]
            store.add_texts(
                texts=[w["text"] for w in batch],
                metadatas=[{k: w[k] for k in ("provision", "title", "regime", "kind")} for w in batch],
                ids=[w["window_id"] for w in batch],
            )
        # Mark complete only after every batch succeeds. A partial build is retried next time.
        store._collection.modify(metadata={**metadata, "chunk_fingerprint": fingerprint})
    return store


@lru_cache
def embedding_tokenizer():
    """Count with the same tokenizer as Chroma, without silently truncating the count."""
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

    model = ONNXMiniLM_L6_V2()
    # Reuse Chroma's model cache and first-use downloader; no paid model call.
    model._download_model_if_not_exists()
    tokenizer = model.tokenizer  # separate instance from the one Chroma uses for embedding
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return tokenizer


# Preserve paragraphs/numbered clauses first, then sentences, then words. Separators
# are zero-width so splitting and rejoining cannot drop punctuation or whitespace.
CHUNK_BOUNDARIES = (
    r"(?<=\n)(?=\n|\s*(?:\([A-Za-z0-9]+\)|\d+(?:\.\d+)*\.?\s))",
    r"(?<=[.!?])(?=\s+[A-Z])",
    r"(?<=\s)(?=\S)",
)


def split_legal_text(text, fits, level=0):
    """Pack complete units; only split a unit further when it exceeds the token budget."""
    if fits(text):
        return [text]
    if level > len(CHUNK_BOUNDARIES):
        raise ValueError("A character cannot fit beside the provision ID and title.")
    parts = re.split(CHUNK_BOUNDARIES[level], text) if level < len(CHUNK_BOUNDARIES) else list(text)
    units = [unit for part in parts if part for unit in split_legal_text(part, fits, level + 1)]
    chunks, current = [], ""
    for unit in units:
        if current and not fits(current + unit):
            chunks.append(current)
            current = ""
        current += unit
    if current:
        chunks.append(current)
    return chunks


def text_windows():
    """Keep short provisions whole; split long ones at legal boundaries within 256 tokens."""
    tokenizer = embedding_tokenizer()
    for pid, p in provisions().items():
        heading = f"{pid} {p['title']}\n"

        def fits(body):
            return len(tokenizer.encode(heading + body.strip()).ids) <= EMBEDDING_TOKEN_LIMIT

        if not fits(""):
            raise ValueError(f"Provision ID and title exceed the embedding token limit: {pid}")
        for n, chunk in enumerate(split_legal_text(p["text"], fits)):
            yield {"window_id": f"{pid}#{n}", "provision": pid, "regime": p["regime"],
                   "title": p["title"],
                   "kind": "recital" if "Recital" in pid else "provision",
                   "text": heading + chunk.strip()}


def search(query, regime, k=6):
    """Top provisions for a query within one regime, as (provision_id, distance).

    For the GDPR, at most two results are recitals so the operative articles are not crowded out.
    """
    if regime == "GDPR":
        return (search_where(query, {"$and": [{"regime": "GDPR"}, {"kind": "provision"}]}, k - 2)
                + search_where(query, {"$and": [{"regime": "GDPR"}, {"kind": "recital"}]}, 2))
    return search_where(query, {"regime": regime}, k)


def search_where(query, where, k):
    hits = vector_store().similarity_search_with_score(query, k=k * 3, filter=where)
    best = {}
    for doc, distance in hits:
        pid = doc.metadata["provision"]
        if pid not in best or distance < best[pid]:
            best[pid] = distance
    return sorted(best.items(), key=lambda item: item[1])[:k]


# ------------------------------------------------------------- reference facts

@lru_cache
def countries():
    return json.loads((ROOT / "reference" / "countries.json").read_text())


def country_facts(code):
    """Facts about a country from the reference file. No legal conclusions."""
    ref = countries()
    country = pycountry.countries.get(alpha_2=code)
    adequacy = next((a["scope"] for a in ref["adequacy_decisions"] if a["country"] == code), None)
    in_eea = code in ref["eu_member_states"] or code in ref["other_eea_states"]
    return {
        "code": code,
        "name": country.name if country else "unknown code",
        "eu_member": code in ref["eu_member_states"],
        "eea_member": in_eea,
        "eu_adequacy_decision": adequacy if not in_eea else "not needed (EEA)",
        "local_law_in_knowledge_base": code in LOCAL_LAW_COUNTRIES,
    }
