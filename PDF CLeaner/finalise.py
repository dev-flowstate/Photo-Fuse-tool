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
    #
    # Only the working folders are walked. The web copies are the same
    # pictures at a fraction of the size and the handover folders are copies
    # set aside for the database - all under the same names. Walking the whole
    # tree picked those up as if they were the originals and filed them
    # alongside, so twenty-eight pictures at 160 to 220 dpi ended up in the
    # review folders where everything else is 400.
    aside = ("already done", "already done replacements",
             "done highquality 400dpi")
    found: dict[str, dict[str, Path]] = defaultdict(dict)
    for png in out.rglob("*.png"):
        if "_q" not in png.stem or png.parent.name.endswith("_web"):
            continue
        if any(part in aside for part in png.relative_to(out).parts[:-1]):
            continue
        found[png.stem.rsplit("_q", 1)[0]].setdefault(png.name, png)
    images: dict[str, list[Path]] = {
        stem: sorted(by_name.values()) for stem, by_name in found.items()}

    # One row per paper. The same paper can sit in the tree twice under
    # different folders, and counting it twice doubled its lines here.
    seen: set[str] = set()
    rows = [r for r in rows if not (r["name"] in seen or seen.add(r["name"]))]

    # What each paper's pictures actually contain, which is not always what
    # reading the PDF again makes of it. Some papers are cut to a question
    # list taken from their partner or given by hand, precisely because
    # reading them does not work - so the audit, which reads afresh, reports
    # the wrong answer those repairs exist to override. Judging on the
    # reading held 38 pairs of perfectly good pictures out of the set.
    def numbers(name: str) -> list[int]:
        out = []
        for png in images.get(name, ()):
            tail = png.stem.rsplit("_q", 1)[-1]
            if tail.isdigit():
                out.append(int(tail))
        return sorted(out)

    #: Faults about the pictures themselves. These the pictures cannot answer
    #: for, so they still count however well a pair lines up.
    ABOUT_THE_IMAGES = {"clipped", "furniture"}

    #: Papers whose mark scheme, as Cambridge published it, does not cover
    #: every question the paper asks. Both were read page by page to be sure
    #: it is the source and not the reading: 9701_s24_ms_22 is thirteen pages
    #: holding questions 1 to 4 where the paper asks five, and 9709_s24_ms_33
    #: is nineteen pages holding 1 to 10 where the paper asks eleven. The
    #: questions are kept; the last one simply has no mark scheme to link to.
    SHORT_MARK_SCHEME = {"9701_s24_ms_22": 4, "9709_s24_ms_33": 10}

    def corroborated(name: str) -> bool:
        """
        Whether this paper's pictures and its partner's tell the same story.

        The two documents are read independently, so a paper and its mark
        scheme holding the same question numbers, running from one with
        nothing skipped, is two separate readings agreeing. That is better
        evidence than either reading on its own.
        """
        mine = numbers(name)
        mate = partner(name)
        if not mine or not mate:
            return False
        theirs = numbers(mate)
        if mine != list(range(1, len(mine) + 1)):
            return False
        if mine == theirs:
            return True
        # A mark scheme that is short in the source is allowed to be short
        # here. The question paper keeps all its questions; the ones past the
        # end of the mark scheme simply have nothing to link to.
        short = SHORT_MARK_SCHEME.get(name if "_ms_" in name else mate)
        if short is None:
            return False
        longer, shorter = (mine, theirs) if len(mine) > len(theirs) else (theirs, mine)
        return (shorter == list(range(1, short + 1))
                and longer[:short] == shorter)

    sound = {row["name"] for row in rows
             if images.get(row["name"])
             and not (set(row.get("faults", ())) & ABOUT_THE_IMAGES)
             and (corroborated(row["name"])
                  or not (set(row.get("faults", ())) - HARMLESS))}

    clean, dirty = [], []
    reasons: Counter = Counter()
    for row in rows:
        faults = set(row.get("faults", ())) - HARMLESS
        held = sorted(images.get(row["name"], ()))
        if not held:
            continue
        mate = partner(row["name"])
        if row["name"] not in sound:
            dirty.append((row, held))
            reasons.update(faults or {"pictures do not pair"})
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
