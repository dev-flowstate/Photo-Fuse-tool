"""
Work through the papers the audit held back and try to put them right.

A question paper and its mark scheme are two views of one paper, so where
one of them is sound it knows how many questions there are and which
numbers they carry. That is the target the other is held to. Where both
are doubtful the target is the obvious one - 1 up to the highest number
either of them found.

Knowing what to look for is most of the battle. Ordinary detection has to
work out the question column from the page and refuse anything that does
not fit, because a stray number read as a question wrecks the whole
paper. Searching for a number that is known to be there can be far more
willing: it only has to sit after the question before it and before the
one after, and be somewhere down the left of the page.

Anything repaired is written to a "double check" folder rather than
straight into the clean set, so it can be looked at on its own before it
is trusted.

    py repair.py --kind qp --workers 2
    py repair.py --kind ms --workers 2
    py repair.py --status
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdfcleaner as pc

try:
    import fitz
except ImportError:                                  # pragma: no cover
    import pymupdf as fitz

OUT = Path(r"D:\Papers\output questions and markschemes")
ROOT = Path(r"D:\Papers\all folders\all folders")
CHECK = "double check"

#: Faults that come from reading the paper wrongly, which is what this can
#: do something about. A cut through a line is a different problem.
FIXABLE = {"pair-mismatch", "missing-part", "gap", "foreign-label",
           "no-questions", "no-output"}
HARMLESS = {"shredded", "mixed-rotation"}

_NAME = re.compile(r"^(\d{4})_([a-z]\d{2})_(qp|ms)_(\d+)$", re.I)


def partner(name: str) -> str | None:
    """The other side of this paper - its mark scheme, or its question paper."""
    m = _NAME.match(name)
    if not m:
        return None
    other = "ms" if m.group(3).lower() == "qp" else "qp"
    return f"{m.group(1)}_{m.group(2)}_{other}_{m.group(4)}"


def read(path: Path):
    """The page spans and the kind, ready to search."""
    doc = fitz.open(str(path))
    answers_from = pc.first_answer_table_page(doc)
    kind = pc.detect_kind(path, doc)
    stamps = pc.stamp_rects(doc)
    bands = pc.header_footer_bands(doc)
    spans = []
    for index in range(doc.page_count):
        page = doc[index]
        pc.whiten(page, stamps.get(index, ()))
        pc.strip_furniture(page, bands)
        spans.append(pc.body_spans(page))
    searchable = spans if not answers_from else [
        [] if i < answers_from else sp for i, sp in enumerate(spans)]
    doc.close()
    return kind, spans, searchable


def hunt(searchable, target: list[int], column: tuple[float, float]):
    """
    Find each wanted number in turn, taking the first that can be it.

    Each has to open its line, lie down the left of the page near where the
    others sit, and come after the one before it. Taking them in order stops
    a later question being matched by a number printed inside an earlier
    one.
    """
    low, high = column
    found: list[tuple[int, float, int]] = []
    floor = (-1, -1.0)
    for number in target:
        pattern = re.compile(rf"^{number}(?=$|[\s(.])")
        best = None
        for index, spans in enumerate(searchable):
            for left, centre, y, text in spans:
                if not (low <= left <= high):
                    continue
                if not pattern.match(text.strip()):
                    continue
                if (index, y) <= floor:
                    continue
                if best is None or (index, y) < best[:2]:
                    best = (index, y, number)
            if best is not None and best[0] == index:
                break                       # earliest on the earliest page
        if best is not None:
            found.append(best)
            floor = best[:2]
    return found


def column_of(searchable, found) -> tuple[float, float]:
    """Where the question numbers sit, widened enough to admit a stray one."""
    lefts = []
    for index, y, number in found:
        for left, _, y0, text in searchable[index]:
            if abs(y0 - y) < 0.5 and pc._question_number(text) == number:
                lefts.append(left)
                break
    if not lefts:
        return (0.0, 200.0)
    lefts.sort()
    middle = lefts[len(lefts) // 2]
    return (middle - 30.0, middle + 60.0)


def repair_one(job) -> dict:
    """Try to read one paper again, knowing what it should contain."""
    name, path, target, out_dir = job
    row = {"name": name, "target": target}
    try:
        source, out = Path(path), Path(out_dir)
        kind, spans, searchable = read(source)
        row["kind"] = kind
        before = (pc.find_questions_ms(searchable) if kind == "ms"
                  else pc.find_questions_qp(searchable))
        row["before"] = [n for _, _, n in before]

        want = target or list(range(1, max(row["before"] or [0]) + 1))
        row["target"] = want
        band = column_of(searchable, before)
        after = hunt(searchable, want, band)
        row["after"] = [n for _, _, n in after]

        if not after or row["after"] == row["before"]:
            row["status"] = "no better"
            return row
        if len(after) < len(before):
            row["status"] = "worse, kept the old reading"
            return row

        settings = pc.profile_for(kind, pc.CleanSettings(
            dpi=400, split_questions=True, save_pdf=False))
        stage = out / f"_rep_{name}"
        written = pc.clean_pdf(source, stage / "x.pdf", settings, marks=after)
        dest = out / CHECK
        dest.mkdir(parents=True, exist_ok=True)
        moved = 0
        for png in sorted((written.questions_dir or stage).glob("*.png")):
            shutil.move(str(png), str(dest / png.name))
            moved += 1
        shutil.rmtree(stage, ignore_errors=True)
        row["written"] = moved
        row["status"] = "repaired" if row["after"] == want else "improved"
    except Exception as exc:                          # noqa: BLE001 - reported
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return row


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Repair the papers the audit held back.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--root", default=str(ROOT))
    p.add_argument("--kind", choices=("qp", "ms", "both"), default="both")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--status", action="store_true")
    a = p.parse_args(argv)

    out, root = Path(a.out), Path(a.root)
    rows = json.loads((out / "audit.json").read_text(encoding="utf-8"))
    seen: set[str] = set()
    rows = [r for r in rows if not (r["name"] in seen or seen.add(r["name"]))]
    by = {r["name"]: r for r in rows}

    log = out / f"_repair_{a.kind}.jsonl"
    already: set[str] = set()
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                already.add(json.loads(line)["name"])

    jobs = []
    for row in rows:
        faults = set(row["faults"]) - HARMLESS
        if not faults or not (faults & FIXABLE):
            continue
        m = _NAME.match(row["name"])
        if not m:
            continue
        side = m.group(3).lower()
        if a.kind != "both" and side != a.kind:
            continue
        if row["name"] in already:
            continue
        pdf = next(root.rglob(row["name"] + ".pdf"), None)
        if pdf is None:
            continue
        # What the other side says, if the other side can be believed.
        mate = by.get(partner(row["name"]) or "")
        target = None
        if mate and not (set(mate["faults"]) - HARMLESS) and mate.get("questions"):
            target = list(mate["questions"])
        elif mate and mate.get("questions") and row.get("questions"):
            highest = max(max(mate["questions"], default=0),
                          max(row["questions"], default=0))
            target = list(range(1, highest + 1))
        jobs.append((row["name"], str(pdf), target, str(out)))

    if a.status or not jobs:
        print(f"{len(jobs)} papers to repair for kind={a.kind}"
              f" ({len(already)} already tried)")
        return 0
    if a.limit:
        jobs = jobs[:a.limit]

    print(f"repairing {len(jobs)} {a.kind} papers, {a.workers} at a time", flush=True)
    started, done, better = time.time(), 0, 0
    with log.open("a", encoding="utf-8") as fh, \
            ProcessPoolExecutor(max_workers=a.workers) as pool:
        for row in pool.map(repair_one, jobs, chunksize=1):
            done += 1
            if row.get("status") in ("repaired", "improved"):
                better += 1
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            rate = (time.time() - started) / done
            print(f"[{done}/{len(jobs)}] {row['name']:<22} {row['status']:<26} "
                  f"{row.get('before')} -> {row.get('after')}   "
                  f"~{(len(jobs)-done)*rate/60:.0f} min left", flush=True)

    print(f"\n{better} of {done} improved; images are in {out / CHECK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
