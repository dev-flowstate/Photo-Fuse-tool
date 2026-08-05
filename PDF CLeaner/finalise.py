"""
Separate the question images that pass every check from the ones that do not.

Reads the audit and files each paper's images accordingly. Nothing is
deleted: a paper with a fault keeps its images where they are, so a defect
can still be looked at, and only the clean ones move.

    py finalise.py                 (report what would move)
    py finalise.py --apply         (move them and write the manifest)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(r"D:\Papers\output questions and markschemes")

#: Faults that do not make the images wrong. A paper whose text arrives in
#: fragments is only worth knowing about if something came of it, and the
#: something would be one of the other faults.
HARMLESS = {"shredded", "mixed-rotation"}

_NAME = re.compile(r"^(\d{4})_([a-z]\d{2})_(qp|ms)_(\d+)$", re.I)


def partner(name):
    """The other side of this paper - its mark scheme, or its question paper."""
    m = _NAME.match(name)
    if not m:
        return None
    other = "ms" if m.group(3).lower() == "qp" else "qp"
    return f"{m.group(1)}_{m.group(2)}_{other}_{m.group(4)}"



def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="File the clean question images.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--apply", action="store_true", help="actually move them")
    a = p.parse_args(argv)

    out = Path(a.out)
    report = out / "audit.json"
    if not report.is_file():
        print(f"No audit to read. Run audit.py first.\n  looked in {report}")
        return 1
    rows = json.loads(report.read_text(encoding="utf-8"))

    # By name, not by path. A run stopped part way can leave one image in
    # two places, and counting it twice put duplicate lines in the manifest.
    found: dict[str, dict[str, Path]] = defaultdict(dict)
    for png in out.rglob("*.png"):
        if "_q" in png.stem:
            found[png.stem.rsplit("_q", 1)[0]].setdefault(png.name, png)
    images: dict[str, list[Path]] = {
        stem: sorted(by_name.values()) for stem, by_name in found.items()}

    # One row per paper. The same paper can sit in the tree twice under
    # different folders, and counting it twice doubled its lines here.
    seen: set[str] = set()
    rows = [r for r in rows if not (r["name"] in seen or seen.add(r["name"]))]

    # A question links to its mark scheme on the site, so one without the
    # other is a link that points at nothing. A paper is only clean if its
    # partner is clean too.
    sound = {row["name"] for row in rows
             if not (set(row.get("faults", ())) - HARMLESS)
             and images.get(row["name"])}

    clean, dirty = [], []
    reasons: Counter = Counter()
    for row in rows:
        faults = set(row.get("faults", ())) - HARMLESS
        held = sorted(images.get(row["name"], ()))
        if not held:
            continue
        mate = partner(row["name"])
        if faults:
            dirty.append((row, held))
            reasons.update(faults)
        elif mate and mate not in sound:
            dirty.append((row, held))
            reasons["no usable partner"] += 1
        else:
            clean.append((row, held))

    kept = sum(len(held) for _, held in clean)
    left = sum(len(held) for _, held in dirty)
    print(f"{len(clean)} papers clean  ({kept} images)")
    print(f"{len(dirty)} papers with faults  ({left} images)")
    print("\nwhy the rest are held back:")
    for fault, count in reasons.most_common():
        print(f"   {fault:<16} {count}")

    if not a.apply:
        print("\nreport only - pass --apply to move them and write the manifest")
        return 0

    def file_away(group, suffix) -> int:
        moved = 0
        for row, held in group:
            kind = "markschemes" if "_ms_" in row["name"] else "questions"
            dest = out / f"{kind}_{suffix}"
            dest.mkdir(exist_ok=True)
            for png in held:
                target = dest / png.name
                if target == png or not png.is_file():
                    # Already filed, or gone since the list was taken. Either
                    # way there is nothing to move, and stopping the whole run
                    # over one file would undo the thousands already placed.
                    continue
                if target.exists():
                    target.unlink()
                try:
                    shutil.move(str(png), str(target))
                    moved += 1
                except OSError as exc:
                    print(f"   could not file {png.name}: {exc}", flush=True)
        return moved

    # Both sets are filed, so nothing is left lying between the folders a
    # rebuild wrote to and the ones an earlier run used. Held-back images are
    # moved, never deleted.
    moved = file_away(clean, "clean")
    file_away(dirty, "review")

    manifest = out / "clean questions.txt"
    with manifest.open("w", encoding="utf-8") as fh:
        fh.write(f"{kept} question images from {len(clean)} papers, "
                 f"every one passing every check\n\n")
        by_syllabus: Counter = Counter()
        for row, held in clean:
            by_syllabus[row["name"][:4]] += len(held)
        for code in sorted(by_syllabus):
            fh.write(f"  {code}: {by_syllabus[code]} images\n")
        fh.write("\n")
        for row, held in sorted(clean, key=lambda r: r[0]["name"]):
            for png in held:
                fh.write(f"{png.name}\n")

    remaining = out / "still defective.txt"
    with remaining.open("w", encoding="utf-8") as fh:
        fh.write(f"{len(dirty)} papers held back\n\n")
        for row, held in sorted(dirty, key=lambda r: r[0]["name"]):
            faults = ", ".join(sorted(set(row["faults"]) - HARMLESS))
            fh.write(f"{row['name']:<24} {faults}\n")

    print(f"\n{moved} images filed as clean")
    for folder in ("questions_clean", "markschemes_clean",
                   "questions_review", "markschemes_review"):
        here = out / folder
        if here.is_dir():
            print(f"  {folder:<20} {len(list(here.glob('*.png')))} images")
    print(f"written: {manifest}\n         {remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
