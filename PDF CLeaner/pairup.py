"""
Leave only questions that have their mark scheme, and mark schemes that
have their question.

A question on the site links to its mark scheme, so a question whose mark
scheme was held back is a link that points at nothing. Those go to the
review folders with their partners rather than out to the web.

Nothing is deleted - an image only moves, so restoring the other side of a
paper later brings both back.

    py pairup.py             (report)
    py pairup.py --apply     (move the unpaired ones to review)
"""

from __future__ import annotations

import argparse
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(r"D:\Papers\output questions and markschemes")
_NAME = re.compile(r"^(\d{4})_([a-z]\d{2})_(qp|ms)_(\d+)$", re.I)
SUBJ = {"9700": "Biology", "9701": "Chemistry", "9702": "Physics", "9709": "Maths"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Keep only paired questions.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)

    out = Path(a.out)
    held: dict[tuple, dict[str, list[Path]]] = defaultdict(dict)
    for folder in ("questions_clean", "markschemes_clean"):
        for png in sorted((out / folder).glob("*.png")):
            m = _NAME.match(png.stem.rsplit("_q", 1)[0])
            if m:
                key = (m.group(1), m.group(2), m.group(4))
                held[key].setdefault(m.group(3).lower(), []).append(png)

    lonely = {k: v for k, v in held.items() if len(v) == 1}
    images = [png for sides in lonely.values() for group in sides.values()
              for png in group]
    kinds: Counter = Counter(k for sides in lonely.values() for k in sides)
    subjects: Counter = Counter(SUBJ.get(k[0], k[0]) for k in lonely)

    print(f"{len(held)} combinations in the clean set")
    print(f"   fully paired : {len(held) - len(lonely)}")
    print(f"   unpaired     : {len(lonely)}   ({len(images)} images)")
    print(f"      question papers with no mark scheme : {kinds.get('qp', 0)}")
    print(f"      mark schemes with no question paper : {kinds.get('ms', 0)}")
    print("   by subject:", dict(subjects))

    if not a.apply:
        print("\nreport only - pass --apply to move them to review")
        return 0

    moved = 0
    for key, sides in lonely.items():
        for side, group in sides.items():
            where = out / ("questions_review" if side == "qp" else "markschemes_review")
            where.mkdir(exist_ok=True)
            for png in group:
                target = where / png.name
                if target.exists():
                    target.unlink()
                shutil.move(str(png), str(target))
                moved += 1

    print(f"\nmoved {moved} images to the review folders")
    for folder in ("questions_clean", "markschemes_clean",
                   "questions_review", "markschemes_review"):
        here = out / folder
        if here.is_dir():
            print(f"   {folder:<20} {len(list(here.glob('*.png'))):>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
