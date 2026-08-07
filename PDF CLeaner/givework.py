"""
Set aside a batch of finished papers to hand over.

Whoever is loading the site needs work now, so a number of papers are taken
out of the set and put in a folder of their own. Taking them out is the
point: what is left in the web folders is then by definition still to give,
and nothing gets handed over twice.

Only papers that are verified are eligible - their question paper and mark
scheme carry the same question numbers, running from one with nothing
skipped, and neither is waiting on a rebuild. A paper that might still
change is no use to somebody about to load it.

The web pictures are moved. The 400 dpi originals are copied, since those
folders are the archive everything else is made from.

    py givework.py --syllabus 9709 --papers 10
    py givework.py --syllabus 9709 --papers 10 --apply
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

OUT = Path(r"D:\Papers\output questions and markschemes")
DEST = "given for work"
_NAME = re.compile(r"^(\d{4})_([a-z]\d{2})_(qp|ms)_(\d+)$", re.I)

#: Faults that say nothing about whether the pictures are right.
HARMLESS = {"shredded", "mixed-rotation", "stale"}


def pending(out: Path) -> set[str]:
    """Papers waiting on a rebuild, which must not be handed over yet."""
    names: set[str] = set()
    for leaf in ("_sidecut.txt", "_footcut.txt", "_recut.txt"):
        here = out / leaf
        if here.is_file():
            names |= set(here.read_text(encoding="utf-8").split())
    return names


def gather(out: Path, syllabus: str):
    """Every combination of this syllabus, with where its pictures live."""
    web: dict = defaultdict(lambda: defaultdict(dict))
    big: dict = defaultdict(lambda: defaultdict(dict))
    for folder, store in (("questions_clean_web", web),
                          ("markschemes_clean_web", web),
                          ("questions_clean", big),
                          ("markschemes_clean", big)):
        here = out / folder
        if not here.is_dir():
            continue
        for png in here.glob("*.png"):
            stem, _, tail = png.stem.rpartition("_q")
            m = _NAME.match(stem)
            if m and m.group(1) == syllabus and tail.isdigit():
                store[(m.group(2), m.group(4))][m.group(3).lower()][int(tail)] = png
    return web, big


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Set aside papers to hand over.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--syllabus", default="9709")
    p.add_argument("--papers", type=int, default=10)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    out = Path(a.out)

    rows = json.loads((out / "audit.json").read_text(encoding="utf-8"))
    seen: set[str] = set()
    rows = [r for r in rows if not (r["name"] in seen or seen.add(r["name"]))]
    by = {r["name"]: r for r in rows}
    waiting = pending(out)

    web, big = gather(out, a.syllabus)
    ready = []
    for key in sorted(web):
        side, other = web[key], big.get(key, {})
        if set(side) != {"qp", "ms"} or set(other) != {"qp", "ms"}:
            continue
        numbers = sorted(side["qp"])
        if sorted(side["ms"]) != numbers or numbers != list(range(1, len(numbers) + 1)):
            continue
        if sorted(other["qp"]) != numbers or sorted(other["ms"]) != numbers:
            continue
        names = [f"{a.syllabus}_{key[0]}_qp_{key[1]}",
                 f"{a.syllabus}_{key[0]}_ms_{key[1]}"]
        if any(n in waiting for n in names):
            continue
        if any(set(by.get(n, {}).get("faults", ())) - HARMLESS for n in names):
            continue
        ready.append((key, numbers, names))

    # A spread rather than the first ten alphabetically, so the batch covers
    # several papers of the syllabus and several sessions.
    chosen, taken = [], defaultdict(int)
    for want in (1, 2, 3):
        for key, numbers, names in ready:
            if len(chosen) >= a.papers:
                break
            if taken[key[1]] < want and (key, numbers, names) not in chosen:
                chosen.append((key, numbers, names))
                taken[key[1]] += 1
    chosen = chosen[:a.papers]

    total = sum(len(n) for _, n, _ in chosen) * 2
    print(f"{len(ready)} {a.syllabus} combinations are verified and settled")
    print(f"handing over {len(chosen)} of them, {total} pictures:\n")
    for key, numbers, _ in chosen:
        print(f"   {a.syllabus} {key[0]} paper {key[1]:<4} "
              f"{len(numbers)} questions")
    if not a.apply:
        print("\nreport only - pass --apply to move them")
        return 0

    dest = out / DEST
    for leaf in ("questions", "markschemes", "400 dpi/questions",
                 "400 dpi/markschemes"):
        (dest / leaf).mkdir(parents=True, exist_ok=True)

    moved = copied = 0
    for key, numbers, _ in chosen:
        for side, leaf in (("qp", "questions"), ("ms", "markschemes")):
            for number in numbers:
                small = web[key][side][number]
                shutil.move(str(small), str(dest / leaf / small.name))
                moved += 1
                large = big[key][side][number]
                shutil.copy2(str(large), str(dest / "400 dpi" / leaf / large.name))
                copied += 1

    lines = [f"{len(chosen)} {a.syllabus} papers handed over for loading",
             "",
             "questions/ and markschemes/ are the web-sized pictures - these",
             "are the ones for the site. 400 dpi/ holds the originals.",
             "",
             "Every one of these was checked before it went out: the question",
             "paper and the mark scheme carry the same question numbers,",
             "running from one with nothing skipped, and neither was waiting",
             "on a rebuild. They will not change.",
             "",
             f"{moved} web pictures, {copied} at 400 dpi.",
             ""]
    for key, numbers, _ in chosen:
        lines.append(f"   {a.syllabus}_{key[0]}_*_{key[1]}   "
                     f"questions 1 to {len(numbers)}")
    (dest / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n{moved} web pictures moved to {dest}")
    print(f"{copied} originals copied alongside")
    for folder in ("questions_clean_web", "markschemes_clean_web"):
        left = len(list((out / folder).glob("*.png")))
        print(f"   {folder:<24} {left} left to give")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
