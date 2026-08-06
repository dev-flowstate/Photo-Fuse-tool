"""
Cut a named paper to a question list given by hand.

A handful of mark schemes read wrongly for reasons of their own, and each
would need its own rule to read right - rules that then misfire on the
hundreds of papers that are already correct. Where the question paper reads
cleanly it says what its mark scheme must contain, so the mark scheme is
searched for exactly those numbers instead of being asked to work them out.

Searching for a number known to be there can be far more willing than
finding one from nothing: it only has to open its line, sit in the column
the other labels sit in, and come after the question before it.

    py byhand.py --list
    py byhand.py --apply
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pdfcleaner as pc
import repair

try:
    import fitz
except ImportError:                                      # pragma: no cover
    import pymupdf as fitz

OUT = Path(r"D:\Papers\output questions and markschemes")
ROOT = Path(r"D:\Papers\all folders\all folders")

#: Mark schemes that read wrongly, and how many questions they hold. Each
#: number was taken from the question paper of the same session, which reads
#: cleanly, and checked against the PDF by eye.
BY_HAND = {
    # Reads ten: the marking points listed inside one answer count 1 to 10
    # down the same margin, and no rule separates them from the real column
    # without breaking the maths mark schemes, which number a question with
    # parts "3(a)" and one without a bare "5".
    "9700_s25_ms_51": 2,
    # Reads two to seven: question 1 sits alone at the head of its page and
    # nothing else in its column reaches up that far.
    "9709_w23_ms_43": 7,
}


def cut(name: str, wanted: int, out: Path, root: Path, dpi: int) -> dict:
    """Find the wanted numbers in this paper and cut it to them."""
    row = {"name": name, "wanted": list(range(1, wanted + 1))}
    source = next(root.rglob(name + ".pdf"), None)
    if source is None:
        row["status"] = "no PDF"
        return row
    kind, spans, searchable = repair.read(source)
    before = (pc.find_questions_ms(searchable) if kind == "ms"
              else pc.find_questions_qp(searchable))
    row["before"] = [n for _, _, n in before]

    band = repair.column_of(searchable, before)
    found = repair.hunt(searchable, row["wanted"], band)

    # Where a label cannot be found at all, look at the page before the
    # furniture came off it. An older mark scheme rules its header as a table
    # and prints the first question a few points beneath; the sweep that
    # clears the header reaches down and takes the number with it, so the
    # label is missing from the text long before anything tries to read it.
    # Searching the untouched page cannot let the header back in: a candidate
    # still has to open its line and sit in the column the others sit in.
    if [n for _, _, n in found] != row["wanted"]:
        row["reread"] = True
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
        found = repair.hunt(raw, row["wanted"], band)
        searchable = raw
    row["after"] = [n for _, _, n in found]
    if row["after"] != row["wanted"]:
        row["status"] = "could not find them all"
        return row

    settings = pc.profile_for(kind, pc.CleanSettings(
        dpi=dpi, split_questions=True, save_pdf=False))
    stage = out / f"_hand_{name}"
    written = pc.clean_pdf(source, stage / "x.pdf", settings, marks=found)
    moved = 0
    for png in sorted((written.questions_dir or stage).glob("*.png")):
        shutil.move(str(png), str(out / png.name))
        moved += 1
    shutil.rmtree(stage, ignore_errors=True)
    row["images"] = moved
    row["status"] = "cut"
    return row


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cut named papers to a given list.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--root", default=str(ROOT))
    p.add_argument("--dpi", type=int, default=400)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    out, root = Path(a.out), Path(a.root)

    print(f"{len(BY_HAND)} papers to cut by hand")
    for name, wanted in BY_HAND.items():
        print(f"   {name:<20} to 1..{wanted}")
    if not a.apply:
        print("\nreport only - pass --apply to do it")
        return 0

    print()
    for name, wanted in BY_HAND.items():
        # Clear what is there before writing, or a paper that used to yield
        # more pictures leaves the extra ones behind.
        for png in out.rglob(f"{name}_q*.png"):
            if "already done" not in str(png):
                png.unlink()
        row = cut(name, wanted, out, root, a.dpi)
        print(f"   {row['name']:<20} {row['status']:<24} "
              f"{row.get('before')} -> {row.get('after')}"
              f"   {row.get('images', 0)} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
