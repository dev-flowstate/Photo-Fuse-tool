"""
Check every repaired paper on its own before it is trusted.

repair.py works out what a paper should contain and cuts it again, but
being told what to look for makes it willing, and a willing search can
find a number that was never a question. So nothing it produces goes
straight into the clean set: each paper is checked here first, on the
pictures themselves.

A repaired paper passes only if:

  * its questions run 1, 2, 3... with nothing skipped
  * it agrees with the other side of the same paper, where that side is
    already trusted
  * no image opens or closes through the middle of a line
  * no image is empty

    py doublecheck.py                (report)
    py doublecheck.py --accept       (move what passes into the clean set)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit as auditor
import pdfcleaner as pc

try:
    import fitz
except ImportError:                                  # pragma: no cover
    import pymupdf as fitz

OUT = Path(r"D:\Papers\output questions and markschemes")
ROOT = Path(r"D:\Papers\all folders\all folders")
CHECK = "double check"

_IMG = re.compile(r"^(.*)_q(\d+)$")
_NAME = re.compile(r"^(\d{4})_([a-z]\d{2})_(qp|ms)_(\d+)$", re.I)
HARMLESS = {"shredded", "mixed-rotation"}


def bare_starts(name: str, numbers: list[int]) -> list[int]:
    """
    Which of these questions open on a bare number rather than a part label.

    A mark scheme lists every part in its Question column - 1(a), 2(b)(ii) -
    so a real question there begins "2(". A bare "2" down the left of the
    page is a numbered list inside somebody's answer.
    """
    pdf = next(Path(ROOT).rglob(name + ".pdf"), None)
    if pdf is None:
        return []
    try:
        doc = fitz.open(str(pdf))
    except Exception:                                  # noqa: BLE001
        return []
    try:
        labelled: set[int] = set()
        for index in range(doc.page_count):
            for _, _, _, text in pc.body_spans(doc[index]):
                body = text.strip()
                m = re.match(r"^(\d{1,2})\s*\(", body)
                if m:
                    labelled.add(int(m.group(1)))
        return [n for n in numbers if n not in labelled]
    finally:
        doc.close()


def partner(name: str) -> str | None:
    m = _NAME.match(name)
    if not m:
        return None
    other = "ms" if m.group(3).lower() == "qp" else "qp"
    return f"{m.group(1)}_{m.group(2)}_{other}_{m.group(4)}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Check repaired papers one at a time.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--accept", action="store_true",
                   help="move what passes into the clean set")
    a = p.parse_args(argv)

    out = Path(a.out)
    here = out / CHECK
    if not here.is_dir():
        print(f"Nothing to check - {here} does not exist.")
        return 1

    rows = json.loads((out / "audit.json").read_text(encoding="utf-8"))
    seen: set[str] = set()
    rows = [r for r in rows if not (r["name"] in seen or seen.add(r["name"]))]
    by = {r["name"]: r for r in rows}

    # What is already trusted, so a repaired paper can be held to it.
    trusted: dict[str, int] = {}
    for folder in ("questions_clean", "markschemes_clean"):
        for png in (out / folder).glob("*.png"):
            m = _IMG.match(png.stem)
            if m:
                trusted[m.group(1)] = trusted.get(m.group(1), 0) + 1

    papers: dict[str, list[Path]] = defaultdict(list)
    for png in sorted(here.glob("*.png")):
        m = _IMG.match(png.stem)
        if m:
            papers[m.group(1)].append(png)

    verdicts: Counter = Counter()
    passed, failed = [], []
    for name, images in sorted(papers.items()):
        numbers = sorted(int(_IMG.match(p.stem).group(2)) for p in images)
        why = []

        if numbers != list(range(1, len(numbers) + 1)):
            why.append(f"numbers skip: {numbers}")

        mate = partner(name)
        if mate and mate in trusted and trusted[mate] != len(numbers):
            why.append(f"partner has {trusted[mate]}, this has {len(numbers)}")

        # A mark scheme labels every part - 2(a), 2(b)(i) - so a question
        # there opens with "2(" and never with a bare "2". A bare number is
        # what a numbered list inside an answer looks like, and one Planning
        # paper came back as three questions because the apparatus list in
        # 1(e) reads "1 Bunsen burner, 2 Crucible, 3 Measure mass...".
        if "_ms_" in name:
            bare = bare_starts(name, numbers)
            if bare:
                why.append(f"opens on a bare number, not a part label: {bare}")

        for png in images:
            edge = auditor.edge_ink(png)
            if edge is None:
                why.append(f"{png.name} is empty")
            elif max(edge) > 0.5:
                why.append(f"{png.name} cut through a line")

        if why:
            failed.append((name, why))
            verdicts["failed"] += 1
        else:
            passed.append((name, images))
            verdicts["passed"] += 1

    print(f"{len(papers)} repaired papers in {here.name}")
    print(f"   passed : {verdicts['passed']}")
    print(f"   failed : {verdicts['failed']}")
    for name, why in failed[:20]:
        print(f"      {name:<22} {'; '.join(why[:2])}")

    if not a.accept:
        print("\nreport only - pass --accept to move what passed into the clean set")
        return 0

    moved = 0
    for name, images in passed:
        kind = "markschemes_clean" if "_ms_" in name else "questions_clean"
        dest = out / kind
        for old in dest.glob(f"{name}_q*.png"):
            old.unlink()
        for other in ("questions_review", "markschemes_review"):
            for old in (out / other).glob(f"{name}_q*.png"):
                old.unlink()
        for png in images:
            shutil.move(str(png), str(dest / png.name))
            moved += 1

    print(f"\n{moved} images accepted into the clean set from {len(passed)} papers")
    print(f"{verdicts['failed']} papers stay in {here.name} for a closer look")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
