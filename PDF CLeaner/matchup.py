"""
Bring a mark scheme up to the question paper it belongs to.

The two documents are read completely independently, so where the question
paper counts 1..n with nothing skipped it is telling the truth about how
many questions there are - and a mark scheme that disagrees is the one at
fault. Cambridge publishes a mark scheme covering every question of its
paper, so the paper's list is what the mark scheme must contain.

Knowing what to look for is most of the battle. Ordinary detection has to
work the column out from the page and refuse anything that does not fit,
because one stray number wrecks the whole paper. Searching for a number
known to be there can be far more willing: it only has to open its line,
sit in the column the other labels sit in, and follow the one before it.

Where a label cannot be found at all, the page is read again before its
furniture came off - some layouts print the first question inside the band
the header sweep clears, so the label is gone long before anything reads it.

    py matchup.py                (say what it would do)
    py matchup.py --apply --workers 4
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pdfcleaner as pc
import repair

try:
    import fitz
except ImportError:                                      # pragma: no cover
    import pymupdf as fitz

OUT = Path(r"D:\Papers\output questions and markschemes")
ROOT = Path(r"D:\Papers\all folders\all folders")
_NAME = re.compile(r"^(\d{4})_([a-z]\d{2})_(qp|ms)_(\d+)$", re.I)


def partner(name: str) -> str | None:
    """The other side of this paper."""
    m = _NAME.match(name)
    if not m:
        return None
    other = "ms" if m.group(3).lower() == "qp" else "qp"
    return f"{m.group(1)}_{m.group(2)}_{other}_{m.group(4)}"


def sound(row: dict) -> bool:
    """Whether this reading can be believed enough to teach the other side."""
    if set(row.get("faults", ())) - {"pair-mismatch", "shredded",
                                     "mixed-rotation", "clipped", "stale"}:
        return False
    numbers = row.get("questions") or []
    return bool(numbers) and numbers == list(range(1, len(numbers) + 1))


def bring_up(job) -> dict:
    """Cut one paper to the list its partner gives."""
    name, source_text, target, out_text, dpi = job
    row = {"name": name, "target": target}
    try:
        source, out = Path(source_text), Path(out_text)
        kind, spans, searchable = repair.read(source)
        before = (pc.find_questions_ms(searchable) if kind == "ms"
                  else pc.find_questions_qp(searchable))
        row["before"] = [n for _, _, n in before]
        if row["before"] == target:
            row["status"] = "already right"
            return row

        band = repair.column_of(searchable, before)
        found = repair.hunt(searchable, target, band)

        # Read the page before its furniture came off, where a label is
        # missing entirely. The sweep that clears a header reaches down to
        # the content, and some layouts open question 1 inside that band.
        if [n for _, _, n in found] != target:
            doc = fitz.open(str(source))
            stamps = pc.stamp_rects(doc)
            raw = []
            for index in range(doc.page_count):
                page = doc[index]
                pc.whiten(page, stamps.get(index, ()))
                raw.append(pc.body_spans(page))
            answers = pc.first_answer_table_page(doc)
            doc.close()
            if answers:
                raw = [[] if i < answers else sp for i, sp in enumerate(raw)]
            found = repair.hunt(raw, target, band)

        row["after"] = [n for _, _, n in found]
        if row["after"] != target:
            row["status"] = "could not find them all"
            return row

        settings = pc.profile_for(kind, pc.CleanSettings(
            dpi=dpi, split_questions=True, save_pdf=False))
        stage = out / f"_up_{name}"
        written = pc.clean_pdf(source, stage / "x.pdf", settings, marks=found)
        made = sorted((written.questions_dir or stage).glob("*.png"))
        if len(made) != len(target):
            shutil.rmtree(stage, ignore_errors=True)
            row["status"] = f"cut gave {len(made)} pictures for {len(target)}"
            return row

        # Only now is what is on disk replaced, so a failure part way through
        # cannot leave a paper with half its pictures from each reading.
        #
        # Named folders, not a walk of the whole tree. Walking it matched the
        # pictures this run had just made, sitting in their staging folder
        # underneath it - so they were deleted a line before being moved, and
        # every paper failed with a missing file.
        for folder in (out, out / "questions_clean", out / "markschemes_clean",
                       out / "questions_review", out / "markschemes_review"):
            for old in folder.glob(f"{name}_q*.png"):
                old.unlink(missing_ok=True)
        for png in made:
            shutil.move(str(png), str(out / png.name))
        shutil.rmtree(stage, ignore_errors=True)
        row["images"] = len(made)
        row["status"] = "brought up"
    except Exception as exc:                              # noqa: BLE001
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"[:160]
    return row


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Cut each paper to the list its partner gives.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--root", default=str(ROOT))
    p.add_argument("--dpi", type=int, default=400)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    out, root = Path(a.out), Path(a.root)

    rows = json.loads((out / "audit.json").read_text(encoding="utf-8"))
    seen: set[str] = set()
    rows = [r for r in rows if not (r["name"] in seen or seen.add(r["name"]))]
    by = {r["name"]: r for r in rows}
    handed = {png.stem.rsplit("_q", 1)[0]
              for png in (out / "already done").rglob("*.png")}

    jobs = []
    stuck = []
    for row in rows:
        if "pair-mismatch" not in row.get("faults", ()):
            continue
        if row["name"] in handed:
            continue
        mate = by.get(partner(row["name"]) or "")
        if mate is None:
            continue
        if sound(row) or not sound(mate):
            # This side is the sound one, or neither is - nothing to learn.
            if not sound(mate) and not sound(row):
                stuck.append(row["name"])
            continue
        pdf = next(root.rglob(row["name"] + ".pdf"), None)
        if pdf is None:
            continue
        jobs.append((row["name"], str(pdf), list(mate["questions"]),
                     str(out), a.dpi))

    print(f"{len(jobs)} papers can be brought up to their partner")
    if stuck:
        print(f"{len(set(stuck))} disagree with neither side sound: "
              f"{sorted(set(stuck))[:6]}")
    for name, _, target, _, _ in jobs[:10]:
        print(f"   {name:<20} to {target}")
    if not a.apply or not jobs:
        print("\nreport only - pass --apply to do it" if jobs else "")
        return 0

    print(f"\nrunning {a.workers} at a time", flush=True)
    started, good = time.time(), 0
    log = out / "_matchup.jsonl"
    with log.open("a", encoding="utf-8") as fh, \
            ProcessPoolExecutor(max_workers=a.workers) as pool:
        for done, row in enumerate(pool.map(bring_up, jobs, chunksize=1), 1):
            good += row.get("status") == "brought up"
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            rate = (time.time() - started) / done
            print(f"[{done}/{len(jobs)}] {row['name']:<20} "
                  f"{row['status']:<26} {row.get('before')} -> "
                  f"{row.get('after')}   ~{(len(jobs)-done)*rate/60:.0f} min left",
                  flush=True)

    print(f"\n{good} of {len(jobs)} brought up to their partner")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
