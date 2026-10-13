"""Measure ICD-10-CM suggestion accuracy on labelled diagnoses.

    python scripts/eval_code_suggestions.py [labels.tsv]

Uses the real code file and the real local embedding model (builds or loads
the phrase-vector cache, which takes minutes the first time). Prints
top-1 and top-5 accuracy and every miss.

Without an argument it runs the built-in set: 24 diagnoses worded as in the
demo records, labelled by the developer, not a clinical coder. Once the old
cards are imported, export real diagnosis -> code pairs the doctor confirmed
(one per line: diagnosis<TAB>code[,code...]) and pass that file instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.services import codes  # noqa: E402

BUILT_IN = {
    "Right lower lobe pneumonia, community acquired": {"J18.1", "J18.9"},
    "Acute gastroenteritis with moderate dehydration": {"A09", "K52.9"},
    "Acute diarrhoeal illness, likely food borne": {"A09", "A05.9", "K52.9"},
    "Food poisoning with dehydration": {"A05.9"},
    "Left lower lobe pneumonia": {"J18.1", "J18.9"},
    "Acute lower respiratory tract infection with bronchiolitis": {"J22", "J21.9"},
    "Chest infection with bronchitis": {"J20.9", "J22", "J40"},
    "Dengue fever with warning signs": {"A90", "A91"},
    "Febrile illness with thrombocytopenia, dengue IgM positive": {"A90", "A91"},
    "Enteric fever": {"A01.00"},
    "Typhoid fever, Widal positive": {"A01.00"},
    "Acute pyelonephritis": {"N10"},
    "Urinary tract infection with fever": {"N39.0"},
    "Acute exacerbation of bronchial asthma": {"J45.901", "J45.21", "J45.31", "J45.41", "J45.51"},
    "Diabetic ketoacidosis, new-onset type 1 diabetes": {"E10.10"},
    "Cellulitis of left leg": {"L03.116"},
    "Febrile seizure (simple), resolved": {"R56.00"},
    "Acute viral fever": {"B34.9", "R50.9"},
    "Severe iron deficiency anemia": {"D50.9"},
    "Acute otitis media": {"H66.90", "H66.91", "H66.92", "H66.93", "H65.90", "H65.199"},
    "Bronchiolitis": {"J21.9"},
    "Simple febrile seizure": {"R56.00"},
    "Snake bite, viper envenomation": {"T63.001A", "T63.011A", "T63.031A", "T63.061A", "T63.091A"},
    "Hand foot and mouth disease": {"B08.4"},
}


def read_labels(path: Path) -> dict[str, set[str]]:
    labels = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            diagnosis, code_list = line.split("\t")
            labels[diagnosis] = {codes.normalize(c) for c in code_list.split(",")}
    return labels


def main() -> int:
    labels = read_labels(Path(sys.argv[1])) if len(sys.argv) > 1 else BUILT_IN
    titles = codes.load().titles
    for good in labels.values():
        unknown = good - set(titles)
        if unknown:
            print(f"label codes not in the code file: {sorted(unknown)}")
            return 2
    codes.build_index()
    if codes.index.state != "ready":
        print(f"code index not ready: {codes.index.snapshot()}")
        return 1
    db = SessionLocal()
    top1 = top5 = 0
    try:
        for diagnosis, good in labels.items():
            items, _ = codes.suggest(db, diagnosis, limit=5)
            got = [s.code for s in items]
            top1 += bool(got) and got[0] in good
            top5 += bool(set(got) & good)
            if not set(got) & good:
                print(f"miss  {diagnosis!r}: wanted {sorted(good)}, got {got}")
    finally:
        db.close()
    n = len(labels)
    print(f"top-1 {top1}/{n} ({top1 / n:.0%})   top-5 {top5}/{n} ({top5 / n:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
