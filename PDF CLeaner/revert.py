"""
Undo the repairs nothing could corroborate.

A repair is only believable if something independent says it is right:
either the paper produced nothing at all before, or the other side of the
same paper is sound and agrees. Where both sides were doubtful the target
itself was a guess, and guessing produced a Planning paper cut into three
because the apparatus list inside question 1(e) reads "1 Bunsen burner,
2 Crucible, 3 Measure mass".

Those papers go back to what the ordinary reading gives, and back to the
review folder where they were.
"""
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, r"e:\Photo Fuse tool\PDF CLeaner")
import pdfcleaner as pc

try:
    import fitz
except ImportError:
    import pymupdf as fitz

OUT = Path(r"D:\Papers\output questions and markschemes")
ROOT = Path(r"D:\Papers\all folders\all folders")
NAME = re.compile(r"^(\d{4})_([a-z]\d{2})_(qp|ms)_(\d+)$", re.I)
HARMLESS = {"shredded", "mixed-rotation"}
apply = "--apply" in sys.argv

rows = json.loads((OUT / "audit.json").read_text(encoding="utf-8"))
seen = set()
rows = [r for r in rows if not (r["name"] in seen or seen.add(r["name"]))]
by = {r["name"]: r for r in rows}


def partner(name):
    m = NAME.match(name)
    other = "ms" if m.group(3).lower() == "qp" else "qp"
    return f"{m.group(1)}_{m.group(2)}_{other}_{m.group(4)}"


changed = []
for kind in ("qp", "ms"):
    log = OUT / f"_repair_{kind}.jsonl"
    if not log.is_file():
        continue
    for line in log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["status"] in ("repaired", "improved"):
                changed.append(row)

keep, undo = [], []
for row in changed:
    mate = by.get(partner(row["name"]))
    mate_clean = mate and not (set(mate["faults"]) - HARMLESS)
    if not row["before"] and mate_clean:
        keep.append(row)
    elif mate_clean and len(row.get("after") or []) == len(mate.get("questions") or []):
        keep.append(row)
    else:
        undo.append(row)

print(f"{len(keep)} repairs corroborated, {len(undo)} to undo")
for row in undo:
    print(f"   undo {row['name']:<22} {row['before']} -> {row['after']}")

if not apply:
    print("\nreport only - pass --apply to undo them")
    raise SystemExit

restored = 0
for row in undo:
    name = row["name"]
    pdf = next(ROOT.rglob(name + ".pdf"), None)
    if pdf is None:
        continue
    stage = OUT / f"_undo_{name}"
    try:
        settings = pc.CleanSettings(dpi=400, split_questions=True, save_pdf=False)
        result = pc.clean_pdf(pdf, stage / "x.pdf", settings)
        where = OUT / ("markschemes_review" if "_ms_" in name else "questions_review")
        where.mkdir(exist_ok=True)
        for folder in ("questions_clean", "markschemes_clean",
                       "questions_review", "markschemes_review", "double check"):
            for old in (OUT / folder).glob(f"{name}_q*.png"):
                old.unlink()
        for png in sorted((result.questions_dir or stage).glob("*.png")):
            shutil.move(str(png), str(where / png.name))
            restored += 1
        print(f"   {name}: {len(result.questions)} images back in {where.name}")
    except Exception as exc:                          # noqa: BLE001
        print(f"   {name}: FAILED {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(stage, ignore_errors=True)

print(f"\n{restored} images restored to the review folders")
