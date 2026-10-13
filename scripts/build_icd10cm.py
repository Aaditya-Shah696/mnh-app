"""Build app/data/icd10cm_<year>.tsv from CMS's ICD-10-CM release files.

    python -I scripts/build_icd10cm.py <code-descriptions.zip> <code-tables-tabular-index.zip> [--year 2027]

Sources, both from https://www.cms.gov/medicare/coding-billing/icd-10-codes
(ICD-10-CM is public domain):

- "Code Descriptions in Tabular Order" ZIP: icd10cm_order_<year>.txt, the
  fixed-width code list (layout in CMS icd10OrderFiles.pdf):
      cols  1-5   order number
      cols  7-13  code, no dot
      col  15     1 = billable (valid for coding), 0 = header
      cols 17-76  short description
      cols 78-    long description
- "Code Tables, Tabular and Index" ZIP: icd10cm_index_<year>.xml (the
  Alphabetic Index: clinical wording -> code) and icd10cm_tabular_<year>.xml
  (inclusion terms: official synonyms listed under a code).

Codes kept: billable only, minus chapter XX external causes (V00-Y99) and
injury/poisoning codes (S, T) whose 7th character is not "A" (initial
encounter): a discharge from an admission is the initial encounter, and the
subsequent/sequela variants would otherwise be two thirds of the list.

Output rows, tab separated: code, kind, text. Every code has exactly one
"title" row (the long description), followed by its "index" phrases (index
term paths such as "Fever, enteric") and "inclusion" terms, deduplicated.
Suggestions embed every row; the title is what the record stores and shows.

Re-run with each year's files; the app uses the newest TSV in app/data.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "app" / "data"


def dotted(code: str) -> str:
    return code if len(code) <= 3 else code[:3] + "." + code[3:]


def parse_order_file(text: str) -> list[tuple[str, bool, str]]:
    rows = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        code, flag, long_desc = line[6:13].strip(), line[14:15], line[77:].strip()
        if not re.fullmatch(r"[A-Z][0-9A-Z]{2,6}", code) or flag not in "01" or not long_desc:
            raise ValueError(f"line {line_no} does not match the CMS order-file layout: {line[:40]!r}")
        rows.append((code, flag == "1", long_desc))
    return rows


def keep(code: str, billable: bool) -> bool:
    if not billable or code[0] in "VWXY":
        return False
    if code[0] in "ST" and len(code) == 7 and code[6] != "A":
        return False
    return True


def _text(el) -> str:
    return " ".join("".join(el.itertext()).split())


def index_phrases(xml_bytes: bytes) -> list[tuple[str, str]]:
    """(phrase, dotted code) for every Alphabetic Index term that carries a
    code. The phrase is the path of term titles ("Pneumonia, lobar"), with
    nonessential modifiers (the parenthesised <nemod>) left out."""
    out = []

    def walk(term, path):
        title_el = term.find("title")
        title = _text(title_el) if title_el is not None else ""
        if title_el is not None:
            for nemod in title_el.findall("nemod"):
                title = title.replace(_text(nemod), "").strip()
        phrase = path + [title] if title else path
        code_el = term.find("code")
        if code_el is not None and code_el.text and phrase:
            out.append((", ".join(phrase), code_el.text.strip()))
        for child in term.findall("term"):
            walk(child, phrase)

    root = ET.fromstring(xml_bytes)
    for letter in root.findall("letter"):
        for main in letter.findall("mainTerm"):
            walk(main, [])
    return out


def inclusion_terms(xml_bytes: bytes) -> list[tuple[str, str]]:
    """(term, dotted code) for each inclusion term listed under a code."""
    root = ET.fromstring(xml_bytes)
    return [
        (_text(note), diag.findtext("name"))
        for diag in root.iter("diag")
        for note in diag.findall("inclusionTerm/note")
    ]


def build(order_text: str, index_xml: bytes, tabular_xml: bytes) -> list[tuple[str, str, str]]:
    titles = {dotted(code): desc for code, billable, desc in parse_order_file(order_text)
              if keep(code, billable)}
    extra: dict[str, list[tuple[str, str]]] = {code: [] for code in titles}
    seen = {code: {desc.lower()} for code, desc in titles.items()}
    for kind, pairs in (("index", index_phrases(index_xml)), ("inclusion", inclusion_terms(tabular_xml))):
        for phrase, code in pairs:
            phrase = " ".join(phrase.split())
            if code in titles and phrase and phrase.lower() not in seen[code]:
                seen[code].add(phrase.lower())
                extra[code].append((kind, phrase))
    rows = []
    for code, title in titles.items():
        rows.append((code, "title", title))
        rows.extend((code, kind, phrase) for kind, phrase in extra[code])
    for row in rows:
        if any("\t" in part or "\n" in part for part in row):
            raise ValueError(f"tab or newline inside a field: {row!r}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("descriptions_zip", type=Path)
    parser.add_argument("tables_zip", type=Path)
    parser.add_argument("--year", default="2027")
    args = parser.parse_args()

    with zipfile.ZipFile(args.descriptions_zip) as zf:
        order_text = zf.read(f"Code Descriptions/icd10cm_order_{args.year}.txt").decode("ascii")
    with zipfile.ZipFile(args.tables_zip) as zf:
        index_xml = zf.read(f"Table and Index/icd10cm_index_{args.year}.xml")
        tabular_xml = zf.read(f"Table and Index/icd10cm_tabular_{args.year}.xml")
    rows = build(order_text, index_xml, tabular_xml)

    sha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.descriptions_zip, args.tables_zip)}
    out = OUT_DIR / f"icd10cm_{args.year}.tsv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# ICD-10-CM FY{args.year} from CMS (public domain). Built by scripts/build_icd10cm.py from:\n")
        for name, digest in sha.items():
            fh.write(f"#   {name} sha256 {digest}\n")
        fh.write("# Columns: code, kind (title | index | inclusion), text.\n")
        for row in rows:
            fh.write("\t".join(row) + "\n")
    codes = sum(1 for _, kind, _ in rows if kind == "title")
    print(f"{codes} codes, {len(rows) - codes} index/inclusion phrases written to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
