"""Download official law texts and write them to laws/*.md.

Run once (needs internet):  .venv/bin/python scripts/fetch_laws.py

Every markdown section is one retrievable "provision". Its heading is
"## [ID] title", and the ID is what agents must cite.

Sources (official publishers only):
- GDPR: EU Publications Office (Cellar), the machine-access service behind
  EUR-Lex. Articles from the consolidated text (includes the 2018
  corrigendum); recitals from the Official Journal text (consolidated texts
  omit recitals).
- HIPAA: eCFR versioner API (ecfr.gov), 45 CFR Parts 160 and 164.
- Ireland: Irish Statute Book (irishstatutebook.ie); the Medical Practitioners Act 2007 s. 7 from the
  Law Reform Commission revised Act; the Medical Council's own guide (medicalcouncil.ie).
"""

import datetime
import re
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

LAWS = Path(__file__).resolve().parent.parent / "laws"
TODAY = datetime.date.today().isoformat()

GDPR_ARTICLES_URL = "http://publications.europa.eu/resource/celex/02016R0679-20160504"
GDPR_RECITALS_URL = "http://publications.europa.eu/resource/celex/32016R0679"
GDPR_READER_URL = "https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng"
ECFR_DATE = "2026-09-29"
ECFR_URL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-45.xml?part={part}"
IE = "https://www.irishstatutebook.ie/eli/"


def download(url, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            import gzip
            data = gzip.decompress(data)
        return data.decode("utf-8")


def clean(text):
    text = text.replace("\xa0", " ")  # non-breaking spaces become plain spaces
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def block_text(element):
    """Text of an EU HTML element, one line per paragraph or list item."""
    for skip in element.find_all(["p", "hr"], class_=["footnote", "modref", "separator-short"]):
        skip.decompose()
    lines = [""]

    def walk(node):
        for child in node.children:
            if isinstance(child, str):
                lines[-1] += str(child)
            elif child.name in ("p", "div", "tr", "table", "li"):
                lines.append("")
                walk(child)
                lines.append("")
            else:
                walk(child)  # inline tags such as span or a

    walk(element)
    lines = [clean(line) for line in lines if clean(line)]
    # Numbers and list markers ("1.", "(a)") sit in their own block: join them
    # to the text that follows.
    joined = []
    for line in lines:
        if joined and re.fullmatch(r"\(?[a-z0-9]+\)|\d+\.", joined[-1]):
            joined[-1] = joined[-1] + " " + line
        else:
            joined.append(line)
    return "\n".join(joined)


def write_md(filename, title, source_lines, sections):
    out = [f"# {title}", ""]
    out += [f"> {line}" for line in source_lines]
    out += [f"> Retrieved: {TODAY}", ""]
    for section_id, heading, text in sections:
        out += [f"## [{section_id}] {heading}", "", text.strip(), ""]
    (LAWS / filename).write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {filename}: {len(sections)} provisions")


# ---------------------------------------------------------------- GDPR

def gdpr():
    accept = {"Accept": "application/xhtml+xml", "Accept-Language": "eng"}
    articles = BeautifulSoup(download(GDPR_ARTICLES_URL, accept), "html.parser")
    recitals = BeautifulSoup(download(GDPR_RECITALS_URL, accept), "html.parser")
    sections = []

    for number in range(1, 100):
        div = articles.find("div", id=f"art_{number}")
        title_div = div.find("div", class_="eli-title")
        title = clean(title_div.get_text(" ")) if title_div else ""
        if title_div:
            title_div.decompose()
        heading = div.find("p", class_="title-article-norm")
        if heading:
            heading.decompose()
        text = block_text(div)
        if number == 4:
            # Article 4 holds 26 definitions: one provision per definition.
            for point in re.split(r"\n(?=\(\d+\) )", "\n" + text):
                match = re.match(r"\((\d+)\) ", point.strip())
                if match:
                    sections.append((f"GDPR Art. 4({match.group(1)})", f"Article 4 - {title}", point.strip()))
            continue
        sections.append((f"GDPR Art. {number}", f"Article {number} - {title}", text))

    for number in range(1, 174):
        div = recitals.find("div", id=f"rct_{number}")
        text = block_text(div)
        text = re.sub(rf"^\({number}\)\s*", "", text)
        sections.append((f"GDPR Recital {number}", f"Recital {number}", text))

    write_md(
        "gdpr.md",
        "GDPR - Regulation (EU) 2016/679 (General Data Protection Regulation)",
        [
            f"Official text: {GDPR_READER_URL}",
            f"Articles: consolidated version 2016-05-04 (includes corrigendum), {GDPR_ARTICLES_URL}",
            f"Recitals: Official Journal L 119, 4.5.2016, {GDPR_RECITALS_URL}",
            "Publisher: Publications Office of the European Union. Text unchanged; HTML converted to plain text.",
        ],
        sections,
    )


# ---------------------------------------------------------------- HIPAA

def xml_text(fragment):
    return clean(BeautifulSoup(fragment, "html.parser").get_text(""))


def hipaa():
    sections = []
    for part, subparts in (("160", None), ("164", ("A", "C", "D", "E"))):
        xml = download(ECFR_URL.format(date=ECFR_DATE, part=part), {"Accept-Encoding": "gzip"})
        for subpart in re.finditer(r'<DIV6 N="(\w+)" TYPE="SUBPART".*?</DIV6>', xml, re.S):
            if subparts and subpart.group(1) not in subparts:
                continue
            for section in re.finditer(r'<DIV8 N="([\d.]+)" TYPE="SECTION".*?</DIV8>', subpart.group(0), re.S):
                number = section.group(1)
                body = section.group(0)
                head = xml_text(re.search(r"<HEAD>(.*?)</HEAD>", body, re.S).group(1))
                paragraphs = re.findall(r"<P>(.*?)</P>", body, re.S)
                if not paragraphs:
                    continue  # reserved section
                sections += split_cfr_section(number, head, paragraphs)
    write_md(
        "hipaa.md",
        "HIPAA Administrative Simplification - 45 CFR Part 160 and Part 164 (Subparts A, C, D, E)",
        [
            f"Official text: eCFR (Electronic Code of Federal Regulations), current as of {ECFR_DATE}",
            "Source API: https://www.ecfr.gov/api/versioner/v1/full/{date}/title-45.xml?part=160 and part=164",
            "Reader: https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C",
            "Publisher: Office of the Federal Register / GPO. Text unchanged; XML converted to plain text.",
            "Note: eCFR is an editorial compilation; check court rulings affecting recent amendments.",
        ],
        sections,
    )


def split_cfr_section(number, head, paragraphs):
    """Split a long CFR section at its top-level (a), (b), ... paragraphs."""
    texts = [xml_text(p) for p in paragraphs]
    whole = "\n".join(texts)
    if len(whole.split()) < 1200:
        return [(f"45 CFR {number}", head, whole)]

    chunks, current, label, expected = [], [], None, "a"
    for raw, text in zip(paragraphs, texts):
        # A top-level paragraph is the next lowercase letter in sequence, e.g.
        # "(e)" or "(e)(1)". Letters that are also roman numerals (i, v, x)
        # must open with a "Standard"/"Implementation" heading to count.
        marker = rf"^\({expected}\)(\(\d+\))?\s*"
        is_top = bool(re.match(marker, raw)) and (
            expected not in "ivx" or bool(re.match(marker + r"<I>(Standard|Implementation)", raw))
        )
        reserved = re.match(rf"^\({expected}\)-\(([a-z])\) \[Reserved\]", raw)
        if reserved:  # e.g. "(b)-(d) [Reserved]": skip ahead in the sequence
            expected = chr(ord(reserved.group(1)) + 1)
            continue
        if is_top:
            if current:
                chunks.append((label, current))
            current, label = [text], expected
            expected = chr(ord(expected) + 1)
        else:
            current.append(text)
    chunks.append((label, current))

    if len(chunks) == 1:  # no lettered paragraphs, e.g. a definitions section
        return split_definitions(number, head, texts)
    out = []
    for label, lines in chunks:
        suffix = f"({label})" if label else " (introduction)"
        out.append((f"45 CFR {number}{suffix}", head, "\n".join(lines)))
    return out


def split_definitions(number, head, texts):
    """Definitions sections: one provision per defined term."""
    out, intro = [], []
    for text in texts:
        match = re.match(r"^([A-Z][^.:]{1,80}?)(?: means|:)", text)
        if match and not text.startswith("(") and "following" not in match.group(1):
            out.append([match.group(1).strip(), [text]])
        elif out:
            out[-1][1].append(text)
        else:
            intro.append(text)
    result = [(f"45 CFR {number} [{term}]", head, "\n".join(lines)) for term, lines in out]
    if intro:
        result.insert(0, (f"45 CFR {number} (introduction)", head, "\n".join(intro)))
    return result


# ---------------------------------------------------------------- Ireland

def statute_paragraphs(url):
    soup = BeautifulSoup(download(url), "html.parser")
    return [clean(p.get_text("")) for p in soup.find_all("p") if clean(p.get_text(""))]


def ireland_regulations():
    instruments = [
        ("314/2018", "2018/si/314/made/en/print",
         "Data Protection Act 2018 (Section 36(2)) (Health Research) Regulations 2018"),
        ("188/2019", "2019/si/188/made/en/print",
         "Data Protection Act 2018 (Section 36(2)) (Health Research) (Amendment) Regulations 2019"),
        ("18/2021", "2021/si/18/made/en/print",
         "Data Protection Act 2018 (Section 36(2)) (Health Research) (Amendment) Regulations 2021"),
    ]
    sections = []
    for number, path, name in instruments:
        paragraphs = statute_paragraphs(IE + path)
        start = next(i for i, p in enumerate(paragraphs) if p.startswith("1. (1)") or p.startswith("1. These"))
        regs, current, reg_no = [], [], None
        for p in paragraphs[start:]:
            if p.startswith("GIVEN under") or p.startswith("EXPLANATORY NOTE"):
                break
            match = re.match(r"^(\d+)\.\s", p)
            if match and (reg_no is None or int(match.group(1)) == int(reg_no) + 1):
                if current:
                    regs.append((reg_no, current))
                reg_no, current = match.group(1), [p]
            else:
                current.append(p)
        regs.append((reg_no, current))
        for reg_no, lines in regs:
            sections.append((f"IE S.I. {number} Reg. {reg_no}", f"{name} - Regulation {reg_no}", "\n".join(lines)))
    write_md(
        "ie_health_research_regulations.md",
        "Ireland - Health Research Regulations 2018 (S.I. No. 314/2018) and amendments (S.I. No. 188/2019, S.I. No. 18/2021)",
        [
            "Official text: Irish Statute Book (Office of the Attorney General)",
            *[f"S.I. {n}: {IE}{p.replace('/print', '')}" for n, p, _ in instruments],
            "These are the instruments as made. The 2019 and 2021 amendments modify the 2018 text; read them together.",
        ],
        sections,
    )


def ireland_act():
    url = IE + "2018/act/7/enacted/en/print"
    html = download(url)
    wanted = [36, 37, 38, 41, 42, 45, 52, 53, 54]
    sections = []
    for number in wanted:
        start = html.find(f'name="sec{number}"')
        end = html.find(f'name="sec{number + 1}"', start)
        soup = BeautifulSoup(html[start:end], "html.parser")
        title = clean(soup.find("b").get_text("")) if soup.find("b") else ""
        lines = [clean(p.get_text("")) for p in soup.find_all("p") if clean(p.get_text(""))]
        if lines and lines[0] == title:
            lines = lines[1:]
        sections.append((f"IE DPA 2018 s. {number}", f"Data Protection Act 2018 - Section {number} - {title}", "\n".join(lines)))
    write_md(
        "ie_data_protection_act_2018.md",
        "Ireland - Data Protection Act 2018 (No. 7 of 2018), selected sections",
        [
            f"Official text: Irish Statute Book, {IE}2018/act/7/enacted/en/html",
            "As enacted. Later amendments are not applied; check the Law Reform Commission revised Act.",
            "Selected sections: 36-38 (measures, transfers, public interest), 41-42 (further processing, research), 45 and 52-54 (special categories: health, public health, research).",
        ],
        sections,
    )


MPA_REVISED_URL = "https://revisedacts.lawreform.ie/eli/2007/act/25/revised/en/html"
GUIDE_PAGE_URL = ("https://www.medicalcouncil.ie/news-and-publications/publications/overview/"
                  "guide-to-professional-conduct-and-ethics.html")
GUIDE_PDF_URL = ("https://www.medicalcouncil.ie/news-and-publications/publications/"
                 "guide-to-professional-conduct-and-ethics-for-registered-medical-practitioners-2024.pdf")


def ireland_medical_practitioners_act():
    """Medical Practitioners Act 2007, s. 7 only (the Medical Council's functions, including s. 7(2)(i):
    standards of practice and guidance on professional conduct and ethics). Revised text, because the
    Act has been amended (e.g. by the Regulated Professions (Health and Social Care) (Amendment) Act 2020)."""
    soup = BeautifulSoup(download(MPA_REVISED_URL), "html.parser")
    section = soup.find(id="SEC7")
    lines = [re.sub(r"\s+", " ", clean(p.get_text(" "))) for p in section.find_all("p") if clean(p.get_text(" "))]
    # Keep the operative text; the LRC annotations (Amendments, Modifications, Editorial Notes) follow it.
    text = []
    for line in lines:
        if re.match(r"^(Annotations|Amendments:|Modifications|Editorial Notes)", line):
            break
        text.append(line)
    text = [t for t in text if t not in ("7", "Functions of Council.")]
    text = [re.sub(r"\bF\d+\s*\[\s*", "", t).replace(" ]", "") for t in text]  # amendment markers, not text
    text = [re.sub(r"\s+([,.;)])", r"\1", re.sub(r"\(\s+", "(", t)) for t in text]
    write_md(
        "ie_medical_practitioners_act_2007.md",
        "Ireland - Medical Practitioners Act 2007 (No. 25 of 2007), section 7",
        [
            f"Official text: Law Reform Commission Revised Acts, {MPA_REVISED_URL}#SEC7",
            "As enacted: https://www.irishstatutebook.ie/eli/2007/act/25/enacted/en/html",
            "Revised text (as amended), not the as-enacted text: s. 7 has been amended since 2007. "
            "LRC amendment markers (F-notes) are removed; the words they mark are kept.",
            "Selected because s. 7(2)(i) is the Medical Council's function to specify standards of practice and "
            "guidance on professional conduct and ethics, the source of the guide in ie_medical_council_guide_2024.md.",
        ],
        [("IE MPA 2007 s. 7", "Medical Practitioners Act 2007 - Section 7 - Functions of Council", "\n".join(text))],
    )


HIA_DEFINITIONS_URL = "https://revisedacts.lawreform.ie/eli/2014/act/15/section/2/revised/en/html"
MPA_DEFINITIONS_URL = "https://revisedacts.lawreform.ie/eli/2007/act/25/section/2/revised/en/html"


def revised_definition(html, name):
    """One complete definition, including its lettered limbs, from an LRC section 2.

    Remove annotation markers, keeping the operative amended words. Stop before
    annotations so superseded text cannot enter the corpus.
    """
    section = BeautifulSoup(html, "html.parser").find(id="SEC2")
    lines, collecting = [], False
    for p in section.find_all('p'):
        text = re.sub(r'\s+', ' ', clean(p.get_text(' ')))
        if text.startswith(('Annotations', 'Amendments:', 'Modifications', 'Editorial Notes')):
            break
        text = re.sub(r'\bF\d+\s*\[\s*', '', text).replace(' ]', '')
        text = re.sub(r'([“"])\s+', r'\1', text)
        text = re.sub(r'\s+([”",.;)])', r'\1', text)
        text = re.sub(r'\(\s+', '(', text)
        match = re.match(r'^[“"]([^”"]+)[”"]', text)
        if match:
            if collecting:
                break
            collecting = match.group(1) == name
        if collecting:
            lines.append(text)
    if not lines:
        raise ValueError(f'Missing operative definition: {name}')
    return '\n'.join(lines)


def ireland_health_definitions():
    """Only the incorporated definition chain needed by DPA 2018 s. 52(3)."""
    hia = download(HIA_DEFINITIONS_URL)
    mpa = download(MPA_DEFINITIONS_URL)
    write_md('ie_health_identifiers_act_2014.md',
             'Ireland - Health Identifiers Act 2014, section 2(1), health practitioner definition',
             [f'Official text: Law Reform Commission Revised Acts, {HIA_DEFINITIONS_URL}',
              'Selected complete definition (all limbs), not the complete Act. Incorporated by DPA 2018 s. 52(3).'],
             [('IE HIA 2014 s. 2 [health practitioner]', 'Section 2(1) - health practitioner',
               revised_definition(hia, 'health practitioner'))])
    names = ('register', 'registered medical practitioner')
    write_md('ie_medical_practitioners_definitions_2007.md',
             'Ireland - Medical Practitioners Act 2007, section 2, selected definitions',
             [f'Official text: Law Reform Commission Revised Acts, {MPA_DEFINITIONS_URL}',
              'Selected complete definitions, not the complete Act. Registered medical practitioner is subject to section 56A.',
              'LRC amendment markers are removed; the operative amended words and qualifications are retained.'],
             [(f'IE MPA 2007 s. 2 [{name}]', f'Section 2 - {name}', revised_definition(mpa, name)) for name in names])


def medical_council_guide():
    """Medical Council, Guide to Professional Conduct and Ethics (9th edition, 2024): the Introduction and
    paragraph 25 (Confidentiality - General principles) only. Needs the pdftotext command (poppler)."""
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf") as pdf:
        # curl, because Python's certificate store rejects medicalcouncil.ie's chain on some machines.
        subprocess.run(["curl", "-sSfL", "-A", "Mozilla/5.0", "-o", pdf.name, GUIDE_PDF_URL], check=True)
        raw = subprocess.run(["pdftotext", "-layout", pdf.name, "-"], capture_output=True, text=True, check=True).stdout
        import hashlib
        digest = hashlib.sha256(Path(pdf.name).read_bytes()).hexdigest()

    def paragraphs(block):
        """Join wrapped lines; a numbered item (25.1) or a footnote starts a new paragraph."""
        out, new = [], True
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("Medical Council |") or re.fullmatch(r"\d+", line):
                new = True  # a blank line or page furniture ends a paragraph
                continue
            if new or re.match(r"^(\d+\.\d+|\d+\s{2,}\S)", line):
                out.append(line)
            else:
                out[-1] += " " + line
            new = False
        return [re.sub(r"\s+", " ", p) for p in out]

    intro = raw[raw.index("\nIntroduction\n") + 1: raw.index("Medical Council | Guide", raw.index("\nIntroduction\n"))]
    intro_lines = paragraphs(intro.replace("Introduction\n", "", 1))
    # The body heading stands alone on its line; the table of contents line ends with a page number.
    start = re.search(r"(?m)^25\. Confidentiality - General principles\s*$", raw).start()
    para = raw[start: re.search(r"(?m)^26\. Confidentiality", raw[start:]).start() + start]
    para_lines = paragraphs(para.replace("25. Confidentiality - General principles", "", 1))
    write_md(
        "ie_medical_council_guide_2024.md",
        "Ireland - Medical Council, Guide to Professional Conduct and Ethics for Registered Medical Practitioners "
        "(9th edition, 2024), selected parts",
        [
            f"Official text: Medical Council (Comhairle na nDochtúirí Leighis), {GUIDE_PDF_URL}",
            f"Publication page: {GUIDE_PAGE_URL} (9th edition, launched November 2023; current edition on retrieval)",
            f"Retrieved PDF SHA-256: `{digest}`",
            "Issued under the Medical Council's function in Medical Practitioners Act 2007 s. 7(2)(i).",
            "Not legislation: the guide states 'It is not a legal code.' Whether it is a rule 'established by "
            "national competent bodies' for GDPR Art. 9(3) is an interpretation recorded in the knowledge graph.",
            "Selected parts: Introduction (with footnote 1) and paragraph 25 (with footnotes 40-42). PDF converted "
            "to plain text; wrapped lines joined, page furniture removed.",
        ],
        [("IE MC Guide 2024 Introduction", "Medical Council Guide (2024) - Introduction", "\n".join(intro_lines)),
         ("IE MC Guide 2024 para. 25", "Medical Council Guide (2024) - Paragraph 25 - Confidentiality - General principles",
          "\n".join(para_lines))],
    )


if __name__ == "__main__":
    LAWS.mkdir(exist_ok=True)
    gdpr()
    hipaa()
    ireland_regulations()
    ireland_act()
    ireland_medical_practitioners_act()
    ireland_health_definitions()
    medical_council_guide()
