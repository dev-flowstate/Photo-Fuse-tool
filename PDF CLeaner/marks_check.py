"""
Does every question picture still say what it is worth?

The pictures cannot answer this on their own. A question cut above its
mark allocation looks exactly like a question that ended there, and one
sliced through the bracket still has its full white margin underneath,
because the margin is added after the slice. Both faults destroy their own
evidence.

So the paper is asked instead. Every part of a question paper closes with
its marks in brackets, and the last of those before the next question
begins is the one the picture has to reach. If the window the page is
rendered through would cut it - at either edge - the picture is short.

    py marks_check.py                       (report)
    py marks_check.py --workers 6 --limit 200
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pdfcleaner as pc

try:
    import fitz
except ImportError:                                      # pragma: no cover
    import pymupdf as fitz

ROOT = Path(r"D:\Papers\all folders\all folders")
OUT = Path(r"D:\Papers\output questions and markschemes")

#: "[3]" and "[Total: 12]", which is how a paper says what a part is worth.
MARKS = re.compile(r"\[\s*(?:Total:\s*)?\d{1,2}\s*\]")
_COPY = re.compile(r" \(\d+\)$")


def check(path_text) -> dict:
    """Whether any mark allocation falls outside the window of its page."""
    path = Path(path_text)
    row = {"name": path.stem, "lost": [], "marks": 0}
    try:
        doc = fitz.open(str(path))
    except Exception as exc:                              # noqa: BLE001
        return {"name": path.stem, "error": f"{type(exc).__name__}: {exc}"[:90]}
    try:
        s = pc.profile_for(pc.detect_kind(path, doc),
                           pc.CleanSettings(dpi=400, split_questions=True))
        stamps = pc.stamp_rects(doc)
        bands = pc.header_footer_bands(doc)
        for index in range(doc.page_count):
            page = doc[index]
            pc.whiten(page, stamps.get(index, ()))
            if s.strip_furniture:
                pc.strip_furniture(page, bands)
            clip = pc._clip_for(page, s)
            for block in page.get_text("blocks"):
                body = " ".join(block[4].split())
                if not MARKS.search(body):
                    continue
                box = pc._as_shown(page, fitz.Rect(*block[:4]))
                row["marks"] += 1
                # Wholly outside, or cut by an edge.
                if box.y1 <= clip.y0 or box.y0 >= clip.y1:
                    row["lost"].append({"page": index, "text": body[:40],
                                        "why": "outside the window"})
                elif box.y0 < clip.y0 or box.y1 > clip.y1:
                    row["lost"].append({"page": index, "text": body[:40],
                                        "why": "cut by the window"})
    finally:
        doc.close()
    return row


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Check every question still shows what it is worth.")
    p.add_argument("--root", default=str(ROOT))
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args(argv)

    papers = [q for q in sorted(Path(a.root).rglob("*.pdf"))
              if not _COPY.search(q.stem)]
    if a.limit:
        papers = papers[:a.limit]
    print(f"checking {len(papers)} papers", flush=True)

    hit, seen, marks, why = [], 0, 0, Counter()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for done, row in enumerate(pool.map(check, [str(q) for q in papers],
                                            chunksize=6), 1):
            if "error" in row:
                continue
            seen += 1
            marks += row["marks"]
            if row["lost"]:
                hit.append(row)
                for item in row["lost"]:
                    why[item["why"]] += 1
            if done % 300 == 0:
                print(f"  {done}/{len(papers)}  {len(hit)} affected", flush=True)

    print(f"\n{marks} mark allocations across {seen} papers")
    if not hit:
        print("every one of them falls inside the window it is rendered through")
    else:
        print(f"{len(hit)} papers have one that does not:")
        for reason, count in why.most_common():
            print(f"   {count:>5}  {reason}")
        print("by syllabus:", dict(Counter(r["name"][:4] for r in hit)))
        for row in hit[:12]:
            first = row["lost"][0]
            print(f"   {row['name']:<20} page {first['page']:<3} "
                  f"{first['why']:<20} {first['text']!r}")
        target = Path(a.out) / "_marks_missing.txt"
        target.write_text("\n".join(r["name"] for r in hit) + "\n",
                          encoding="utf-8")
        print(f"\nwritten {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
