"""
Audit every paper and list the ones whose question images are wrong.

Works on the text layer and the cut positions rather than the pictures, so
it can tell that a question is missing its part (a) without reading the
image. Each paper collects zero or more faults:

  no-output      nothing was written for it at all
  missing-part   a question does not begin at its first part
  foreign-label  a later question's label sits inside this question's range
  gap            the question numbers are not 1..n
  clipped        an image opens or closes mid-line, so a cut split a line
  pair-mismatch  the paper and its mark scheme disagree on how many
  furniture      a banner or column heading survives onto a body page
  shredded       the text layer arrives in fragments, so labels are unreadable
  stale          the images on disk predate the current reading of the paper
  mixed-rotation the pages are not all the same way up

    py audit.py                    (scan everything, write audit.json)
    py audit.py --limit 200        (a quick sample)
    py audit.py --only 9701        (one syllabus)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pdfcleaner as pc
from PIL import Image

try:
    import fitz
except ImportError:                                  # pragma: no cover
    import pymupdf as fitz

ROOT = Path(r"D:\Papers\all folders\all folders")
OUT = Path(r"D:\Papers\output questions and markschemes")

#: "1(a)", "1 (a)", or a bare "(a)" where the number is elsewhere on the line.
_PART = re.compile(r"^(?:(\d{1,2})\s*)?\(([a-z])\)")

#: Page furniture that should never survive onto a page holding answers.
_BANNER = re.compile(
    r"Mark Scheme"
    r"|Cambridge (?:International|Assessment|University Press)"
    r"|Question\s+Answer\s+(?:Marks?|Mark)"
    r"|Page\s+\d+\s+of\s+\d+"
    r"|PUBLISHED")

#: A column heading can lose some of its words to the sweep and keep the
#: rest, so a lone "Question" at the head of a page is furniture too.
_COLUMN_WORDS = {"question", "answer", "answers", "mark", "marks",
                 "total", "totals", "guidance"}

_NAME = re.compile(r"^(\d{4})_([a-z]\d{2})_(qp|ms)_(\d+)$", re.I)


def shredded(doc: "fitz.Document", pages: range) -> bool:
    """
    Whether the text comes out in pieces rather than lines.

    Some papers hand back "Question" as "Que" + "estion" and "1(a)(i)" as
    "1(" + "(a)(i)". Nothing matches a label or a heading, so the question
    starts late and the header is never removed.
    """
    short = total = 0
    for index in pages:
        for block in doc[index].get_text("blocks"):
            body = " ".join(block[4].split())
            if not any(ch.isalpha() for ch in body):
                continue
            total += 1
            short += len(body) <= 6
    return total >= 20 and short > total * 0.5


def edge_ink(png: Path, kind: str = "") -> tuple[float, float] | None:
    """
    How much ink the first and last rows carry, against a full line's worth.

    A line sliced through the middle leaves its cross-section along the edge
    of the image; a line trimmed properly leaves only the tops of its tallest
    letters. The two differ by an order of magnitude, so this tells a cut
    apart from a genuinely short question.

    On a mark scheme an unbroken rule at the edge is the table boxing the
    question in, and is right. A question paper has no such table, so a solid
    line at its edge is a diagram cut in half - which is why the exemption
    only applies to one of them.
    """
    if not kind:
        kind = "ms" if "_ms_" in png.stem else "qp"
    try:
        with Image.open(png) as handle:
            mask = np.asarray(handle.convert("L")) < 200
    except Exception:                                 # noqa: BLE001 - skipped
        return None
    # The table's own vertical borders run the whole height of a mark scheme,
    # so they put ink and a separate piece into every row - including the
    # first and last. That made a clean opening line read as a cut one:
    # "1 | EITHER: | (B1, B1, B1) | OE" measured 1.92 of a line and 21 pieces
    # on a picture whose top is plainly whole. The borders are taken out
    # before anything is measured; they are furniture, not part of the text.
    if mask.shape[0] > 20:
        borders = mask.mean(axis=0) > 0.5
        if borders.any():
            mask = mask.copy()
            mask[:, borders] = False
    rows = mask.sum(axis=1)
    inked = np.flatnonzero(rows)
    if not len(inked):
        return None
    # A whole line of text, taken from the densest rows there are. The 90th
    # percentile was measured over every inked row, and a question paper is
    # mostly dotted answer rulings, so it came out at a fraction of a real
    # line and ordinary text measured above it.
    line = np.percentile(rows[inked], 98)
    if line <= 0:
        return None

    def runs(y: int) -> int:
        """How many separate pieces of ink lie along this row."""
        edges = np.flatnonzero(np.diff(
            np.concatenate(([0], mask[y].view(np.int8), [0]))))
        return len(edges) // 2

    def like_its_neighbours(y: int, inward: int) -> bool:
        """
        Whether this row looks like the rows just inside it.

        At a clean edge the picture opens on the tops of the tallest letters
        and the ink climbs steeply as the line fills out - the first row
        carries a fraction of what sits a few rows in. A line cut through the
        middle opens on the cross-section of every letter it crossed, so the
        edge row already carries what its neighbours carry.

        This is what tells the two apart. Measuring the edge against a "whole
        line" does not: the reference is taken over every inked row, and a
        question paper is mostly dotted answer rulings, so the reference
        comes out low and an ordinary opening line measures above it. That
        is why twenty-one pictures were called cut when every one of them
        opens on its question number and closes on its total.
        """
        near = [rows[y + inward * step] for step in range(3, 16)
                if 0 <= y + inward * step < len(rows)]
        near = [n for n in near if n > 0]
        if not near:
            return False
        return rows[y] > float(np.percentile(near, 75)) * 0.6

    def measure(y: int) -> float:
        # Two things have to be true at once, and neither says it alone.
        #
        # A line cut through the middle leaves a piece of ink for every
        # letter stroke it crossed - dozens of them - AND about as much ink
        # as a whole line. A table border leaves one or two long pieces,
        # however much ink they add up to; the top of a properly trimmed
        # line leaves many pieces but only the tips of its tallest letters,
        # a fraction of a line's worth.
        #
        # Measuring the ink alone called a clean mark scheme 6.82; counting
        # the pieces alone called a clean question paper 24.
        # Between a dozen and a hundred or so pieces is what letter strokes
        # look like. Hundreds of them is a dotted ruling - the answer space a
        # question ends on - which is where the question is meant to stop.
        pieces = runs(y)
        if pieces < 10 or pieces > 150:
            return 0.0
        inward = 1 if y == inked[0] else -1
        if not like_its_neighbours(y, inward):
            return 0.0
        ratio = float(rows[y] / line)
        return ratio if ratio >= 0.8 else 0.0

    return measure(inked[0]), measure(inked[-1])


def audit(path: Path) -> dict:
    """Every fault this paper shows, with enough detail to act on."""
    row: dict = {"name": path.stem, "faults": [], "detail": {}}
    doc = fitz.open(str(path))
    try:
        answers_from = pc.first_answer_table_page(doc)
        content_end = pc.last_content_page(doc)
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
        kind = pc.detect_kind(path, doc)
        row["kind"] = kind
        found = (pc.find_questions_ms(searchable) if kind == "ms"
                 else pc.find_questions_qp(searchable))
        numbers = [n for _, _, n in found]
        row["questions"] = numbers

        first = found[0][0] if found else (answers_from or 0)
        last = max(content_end, (found[-1][0] + 1) if found else 1)
        body = range(first, min(last, doc.page_count))

        if shredded(doc, body):
            row["faults"].append("shredded")

        # Only the pages that are actually used. A mark scheme's cover is
        # portrait while its answers are landscape, which is normal and is
        # skipped anyway - it is a mix among the body pages that goes wrong.
        rotations = {doc[i].rotation for i in body}
        if len(rotations) > 1:
            row["faults"].append("mixed-rotation")
            row["detail"]["rotations"] = sorted(rotations)

        if not found:
            row["faults"].append("no-questions")
            return row
        if numbers != list(range(1, len(numbers) + 1)):
            row["faults"].append("gap")

        # Where the question column sits, taken from the labels actually used.
        column = []
        for index, y, number in found:
            for left, _, y0, text in spans[index]:
                if abs(y0 - y) < 0.5 and pc._question_number(text) == number:
                    column.append(left)
                    break
        if column:
            low, high = min(column) - 6.0, max(column) + 6.0
        else:
            low, high = 0.0, 0.0

        bounds = [(p, y) for p, y, _ in found] + [(doc.page_count, 0.0)]
        for i, (index, y, number) in enumerate(found):
            start, stop = bounds[i], bounds[i + 1]
            parts, foreign = [], []
            # A couple of points of slack at each end. Spans on one line do
            # not share a y to the last decimal, and comparing exactly put
            # the "(a)" that sits beside the question number just outside its
            # own question - so every such paper read as starting at (b).
            slack = 2.0
            for page in range(index, min(stop[0] + 1, doc.page_count)):
                for left, _, y0, text in spans[page]:
                    if page == start[0] and y0 < start[1] - slack:
                        continue
                    if page == stop[0] and y0 >= stop[1] - slack:
                        continue
                    body_text = text.strip()
                    # A part label is set out near the question number. The
                    # same shape appears mid-line all over a chemistry paper
                    # as a state symbol - H2O(l), Cl2(g), S(s) - so anything
                    # away from the margin is not a part.
                    m = _PART.match(body_text) if left <= high + 40.0 else None
                    if m and (m.group(1) is None or int(m.group(1)) == number):
                        parts.append((page, y0, m.group(2)))
                    # Only the very next question counts. Any larger number
                    # in the column is usually a graph scale - 10, 20, 30 -
                    # and flagging those buried a real fault in noise.
                    if low <= left <= high and pc._LABEL_START.match(body_text):
                        if pc._question_number(body_text) == number + 1:
                            foreign.append((page + 1, number + 1))
            # Reading order, not the order the spans happen to come out in -
            # taking the first span as the first part reported whole, correct
            # questions as starting at (b).
            #
            # A question opens at (a) or, where the paper numbers its parts
            # in roman, at (i). Anything else means the range began part way
            # through - either the question lost its opening parts, or it
            # started inside the one before it.
            parts.sort()
            if parts and parts[0][2] not in ("a", "i"):
                row["faults"].append("missing-part")
                row["detail"].setdefault("missing_part", []).append(
                    {"question": number, "starts_at": parts[0][2]})
            if foreign:
                row["faults"].append("foreign-label")
                row["detail"].setdefault("foreign", []).append(
                    {"question": number, "found": foreign[:3]})

        for index in body:
            page = doc[index]
            hit = _BANNER.search(" ".join(page.get_text().split()))
            note = hit.group(0) if hit else None
            if note is None:
                edge = page.rect.height * 0.20
                for block in page.get_text("blocks"):
                    shown = pc._as_shown(page, fitz.Rect(*block[:4]))
                    word = " ".join(block[4].split()).lower().strip(":")
                    if shown.y0 < edge and word in _COLUMN_WORDS:
                        note = word
                        break
            if note:
                row["faults"].append("furniture")
                row["detail"]["furniture"] = {"page": index + 1, "text": note}
                break
    except Exception as exc:                          # noqa: BLE001 - reported
        row["faults"].append("error")
        row["detail"]["error"] = f"{type(exc).__name__}: {exc}"[:200]
    finally:
        doc.close()
    row["faults"] = sorted(set(row["faults"]))
    return row



def _worst_edge(job):
    """The worse of a picture's two edges, for the pool to chew through."""
    path, kind = job
    try:
        edge = edge_ink(Path(path), kind)
    except Exception:                                     # noqa: BLE001
        return path, 0.0
    return path, (max(edge) if edge else 0.0)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="List the papers with bad output.")
    p.add_argument("--root", default=str(ROOT))
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--only", default="", help="syllabus code, e.g. 9701")
    a = p.parse_args(argv)

    root, out = Path(a.root), Path(a.out)
    pdfs = sorted(q for q in root.rglob("*.pdf") if a.only in q.stem)
    if a.limit:
        pdfs = pdfs[:a.limit]

    written = {p.stem.rsplit("_q", 1)[0]
               for p in out.rglob("*.png") if "_q" in p.stem}

    print(f"auditing {len(pdfs)} papers", flush=True)
    rows, started = [], time.time()
    for done, path in enumerate(pdfs, 1):
        row = audit(path)
        if path.stem not in written:
            row["faults"] = sorted(set(row["faults"]) | {"no-output"})
        rows.append(row)
        if done % 100 == 0:
            bad = sum(1 for r in rows if r["faults"])
            rate = (time.time() - started) / done
            print(f"  {done}/{len(pdfs)}  {bad} with faults  "
                  f"~{(len(pdfs) - done) * rate / 60:.0f} min left", flush=True)

    # Where a cut landed inside a line of text, the image opens or closes on
    # a horizontal slice through the letters. Its first row then carries as
    # much ink as a whole line does, where a properly trimmed image starts
    # on the ascenders alone and carries almost none.
    #
    # Height cannot be used for this. A maths paper asks whole questions in
    # one line - "Solve the inequality |2x + 3| > 3|x + 2|. [4]" - and those
    # are short and perfectly correct.
    # Only the working set is counted. The others hold pictures under the very
    # same names - the web copies are them at half size, and the handover
    # folders are copies set aside for the database - so walking everything
    # found each one three or four times over and called the paper out of date
    # on the strength of it.
    aside = ("already done", "already done replacements",
             "done highquality 400dpi")
    images: dict = defaultdict(list)
    for png in out.rglob("*.png"):
        if "_q" not in png.stem or png.parent.name.endswith("_web"):
            continue
        if any(part in aside for part in png.relative_to(out).parts[:-1]):
            continue
        images[png.stem.rsplit("_q", 1)[0]].append(png)

    # Every picture has to be decoded for this, and there are fourteen
    # thousand of them - the one part of the audit that is worth spreading
    # over the machine. Reading them one at a time held a single core while
    # the other seven sat idle, which is half an hour of the wall clock.
    print("\nchecking the images for cuts through a line", flush=True)
    jobs = [(str(png), row.get("kind", ""))
            for row in rows for png in sorted(images.get(row["name"], ()))]
    edges: dict[str, float] = {}
    if jobs:
        workers = max(1, (os.cpu_count() or 2) - 1)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for done, (name, worst) in enumerate(
                    pool.map(_worst_edge, jobs, chunksize=32), 1):
                edges[name] = worst
                if done % 2000 == 0:
                    print(f"  {done}/{len(jobs)} images checked", flush=True)

    done = 0
    for row in rows:
        cut = []
        have = sorted(images.get(row["name"], ()))
        for png in have:
            worst = edges.get(str(png), 0.0)
            if worst > 0.5:
                cut.append([png.name, round(worst, 2)])
            done += 1
        if cut:
            row["faults"] = sorted(set(row["faults"]) | {"clipped"})
            row["detail"]["clipped"] = cut[:4]
        # The images on disk were made by an older run. Where the paper now
        # reads a different number of questions, whatever is on disk is out
        # of date whether or not anything else is wrong with it.
        wanted = len(row.get("questions") or ())
        if have and wanted and len(have) != wanted:
            row["faults"] = sorted(set(row["faults"]) | {"stale"})
            row["detail"]["stale"] = {"on_disk": len(have), "now": wanted}
        if done and done % 2000 == 0:
            print(f"  {done} images checked", flush=True)

    # A paper and its mark scheme should agree on how many questions there are.
    pairs: dict = defaultdict(dict)
    for row in rows:
        m = _NAME.match(row["name"])
        if m:
            pairs[(m.group(1), m.group(2), m.group(4))][m.group(3).lower()] = row
    for key, both in pairs.items():
        if "qp" in both and "ms" in both:
            a_n, b_n = both["qp"].get("questions"), both["ms"].get("questions")
            if a_n and b_n and len(a_n) != len(b_n):
                for side in both.values():
                    side["faults"] = sorted(set(side["faults"]) | {"pair-mismatch"})
                    side["detail"]["pair"] = {"qp": len(a_n), "ms": len(b_n)}

    bad = [r for r in rows if r["faults"]]
    counts: Counter = Counter(f for r in rows for f in r["faults"])

    dest = out / "audit.json"
    dest.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    listing = out / "defective papers.txt"
    with listing.open("w", encoding="utf-8") as fh:
        fh.write(f"{len(bad)} of {len(rows)} papers need regenerating\n\n")
        for row in sorted(bad, key=lambda r: r["name"]):
            fh.write(f"{row['name']:<24} {', '.join(row['faults'])}\n")
            for key, value in row["detail"].items():
                fh.write(f"      {key}: {value}\n")

    print(f"\n{len(bad)} of {len(rows)} papers have at least one fault")
    for fault, count in counts.most_common():
        print(f"   {fault:<16} {count}")
    print(f"\nwritten: {listing}\n         {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
