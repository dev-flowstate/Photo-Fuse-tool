"""
PDF Cleaner - core engine
=========================

Takes a whole past paper and gives back a tight, continuous PDF:

  * the barcode / page number header, the footer and the "DO NOT WRITE IN
    THIS MARGIN" sidebar are cropped away,
  * the dotted answer rulings are erased (same algorithm as Photo Fuse),
  * the blank answer space is squashed,
  * what is left is reflowed as one continuous stream and re-paginated.

Because it reflows, a question split across two pages ends up joined - which
is the whole point: no more cropping two screenshots and fusing them.

    python pdfcleaner.py "paper.pdf"
    python pdfcleaner.py "paper.pdf" --pages 4-16 --dpi 300
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable, Sequence

# The image cleaning lives in photofuse.py one folder up, so both tools always
# behave identically.
_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("Missing dependencies. Run:  py -m pip install -r requirements.txt")

# Pillow refuses to build an image over about 179 million pixels, on the
# reasoning that a file claiming to be that big is probably an attack. Here
# the size is ours, not the file's: an A3 paper rendered at 400 dpi comes to
# 214 million pixels quite legitimately, and 9701_w16_qp_42 failed outright
# on it. The ceiling is raised to cover A3 at 600 dpi and no further.
Image.MAX_IMAGE_PIXELS = 500_000_000

# PyMuPDF answers to two names: "pymupdf" since 1.24, "fitz" before that and
# still shipped as an alias. Some installs only carry one, so try both.
try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError as exc:
        sys.exit(
            f"PyMuPDF will not load - that is what reads the PDF.\n\n"
            f"The exact error was:\n    {type(exc).__name__}: {exc}\n\n"
            "If that mentions 'DLL load failed', PyMuPDF IS installed but\n"
            "Windows cannot load it - install the Visual C++ runtime from\n"
            "    https://aka.ms/vs/17/release/vc_redist.x64.exe\n"
            "then restart the computer.\n\n"
            "Otherwise run \"Check setup.bat\" in the folder above; it says\n"
            "exactly which Python is in use and what it is short of.\n"
        )

try:
    import photofuse as pf
except ImportError:
    sys.exit(
        "Could not find photofuse.py.\n"
        "The 'pdf cleaner' folder must stay inside the 'Photo Fuse tool' folder,\n"
        f"next to photofuse.py. Looked in: {_PARENT}\n"
    )

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
PT_PER_INCH = 72.0


@dataclass
class CleanSettings:
    """Everything the cleaner can be told to do."""

    dpi: int = 200                  # working resolution

    # The window of the page that actually holds question content, as a
    # fraction of page width/height. Defaults are measured from a Cambridge
    # (CIE) paper: they drop the barcode strip, the page number, the footer
    # and the vertical "DO NOT WRITE IN THIS MARGIN" bar.
    crop_left: float = 0.060
    crop_top: float = 0.065
    crop_right: float = 0.940
    crop_bottom: float = 0.935
    strip_furniture: bool = True    # also blank headers/footers via the text layer

    remove_answer_lines: bool = True
    remove_solid_rules: bool = False
    collapse_gaps: bool = True
    max_gap_pt: float = 14.0        # blank runs longer than this shrink to it
    clean_background: bool = True
    ink_threshold: int = 200

    skip_blank_pages: bool = True
    blank_ink_fraction: float = 0.0006   # less ink than this = an empty page
    skip_front_matter: bool = True       # jump the cover / data / formulae pages

    gap_between_pages_pt: float = 10.0   # breathing room where pages join
    page_margin_pt: float = 30.0         # white border on the output pages
    grayscale: bool = False              # smaller file, no colour
    pages: str = ""                      # "" = all, else e.g. "4-16,20"

    split_questions: bool = False        # also write one PNG per question
    question_margin_pt: float = 6.0      # white border on those PNGs
    save_pdf: bool = True                # False = question PNGs only, no PDF

    # Which kind of document this is: "qp" a question paper, "ms" a mark
    # scheme, "" work it out. The two are laid out nothing alike and used to
    # be told apart by sniffing each page, so a wrong guess in one place
    # spoiled decisions elsewhere. It is settled once now, and everything
    # below reads from it.
    kind: str = ""

    # A question paper numbers its questions down the left margin of flowing
    # text; a mark scheme lists every part in the Question column of a ruled
    # table. Only the second has rules to cut on - on the first the test can
    # only ever match something that is not a rule, and a line of dense maths
    # was being cut through the middle.
    cut_on_rules: bool = False

    # A question paper opens with an instruction line that belongs to
    # question 1. A mark scheme opens with its abbreviations table, which
    # belongs to nothing.
    keep_above_first: bool = True

    # Reference and administrative pages follow the last question of a
    # question paper. A mark scheme simply ends.
    trim_end_matter: bool = True

    def fuse_settings(self) -> pf.Settings:
        """Translate into the Photo Fuse settings object, in pixels."""
        scale = self.dpi / PT_PER_INCH
        return replace(
            pf.Settings(),
            ink_threshold=self.ink_threshold,
            remove_answer_lines=self.remove_answer_lines,
            remove_solid_rules=self.remove_solid_rules,
            collapse_gaps=self.collapse_gaps,
            max_gap=max(2, round(self.max_gap_pt * scale)),
            clean_background=self.clean_background,
            strip_edge_lines=False,     # the crop box already did this
            trim=True,
            trim_padding=max(2, round(2 * scale)),
        )


# --------------------------------------------------------------------------
# The two setups
# --------------------------------------------------------------------------

#: A question paper: numbers down the left margin, dotted answer rulings to
#: erase, an instruction line above question 1, and reference pages after the
#: last question.
QUESTION_PAPER = dict(
    kind="qp",
    cut_on_rules=False,
    keep_above_first=True,
    trim_end_matter=True,
    remove_answer_lines=True,
)

#: A mark scheme: a ruled answer table, its own repeated column heading, and
#: no dotted rulings at all - so the pass that erases them has nothing to find
#: and can only take real content. Measured over four mark schemes it removed
#: 0.00% of the ink on three and 0.38% on the fourth, all of it answer.
MARK_SCHEME = dict(
    kind="ms",
    cut_on_rules=True,
    keep_above_first=False,
    trim_end_matter=False,
    remove_answer_lines=False,
)

#: Cambridge names every paper <syllabus>_<session>_<qp|ms>_<variant>.
_KIND_IN_NAME = re.compile(r"_(qp|ms)_", re.I)


def detect_kind(src: Path, doc: "fitz.Document") -> str:
    """
    Whether this is a question paper or a mark scheme.

    The filename says so on every paper Cambridge publishes. Where it does
    not, a mark scheme is the one with an answer table in it.
    """
    match = _KIND_IN_NAME.search(Path(src).stem)
    if match:
        return match.group(1).lower()
    return "ms" if first_answer_table_page(doc) is not None else "qp"


def profile_for(kind: str, base: CleanSettings) -> CleanSettings:
    """
    `base` with the settings this kind of document needs.

    Anything the caller set by hand on `base` is left alone - the profile
    only fills in what is still at its default, so the GUI and the command
    line can still override any of it.
    """
    wanted = MARK_SCHEME if kind == "ms" else QUESTION_PAPER
    blank = CleanSettings()
    changes = {name: value for name, value in wanted.items()
               if getattr(base, name) == getattr(blank, name)}
    return replace(base, **changes) if changes else base


# --------------------------------------------------------------------------
# Page selection
# --------------------------------------------------------------------------

def first_question_page(doc: "fitz.Document") -> int:
    """
    Index of the first page that looks like a question rather than front
    matter.

    Question pages carry dotted answer rulings; the cover, the data sheet and
    the formulae pages do not. Falls back to page 1 if nothing matches.

    Both the full stop and the ellipsis character count: some papers rule
    their answer space with "…" rather than "...", and matching only the
    latter used to skip the page holding question 1.
    """
    for index in range(doc.page_count):
        if re.search(r"[.…]{12,}", doc[index].get_text("text")):
            return index
    return 0


#: The heading over a mark scheme's answer table, in reading order.
_ANSWER_TABLE = re.compile(r"Question\s+Answer\s+(?:Marks|Mark)", re.I)

#: The awarding body, however it signs itself - the name changed over the
#: decade these papers span, and the 2024 footer reads "Cambridge University
#: Press & Assessment" where the 2016 header reads "Cambridge International".
_AWARDING = re.compile(r"Cambridge\s+(?:International|Assessment|University\s+Press)",
                       re.I)

#: "Page 9 of 13", printed in the footer of every mark scheme.
_PAGE_OF = re.compile(r"\bPage\s+\d+\s+of\s+\d+\b", re.I)

#: What a paper prints after its last question: the data pages, the spare
#: lined pages and the copyright notice. None of it belongs to a question.
_END_MATTER = re.compile(
    r"The Periodic Table of Elements"
    r"|Permission to reproduce items"
    r"|Copyright Acknowledgements Booklet"
    r"|BLANK PAGE"
    r"|Additional Page"
    r"|DATA BOOKLET",
    re.I)

#: Reference material and the closing notices, printed under the last
#: question rather than on a page of their own, so they have to be cut out of
#: the page instead of skipped. Every one of these is boilerplate that cannot
#: appear inside a question.
_TAIL_MATTER = re.compile(
    r"Important values,? constants and standards"
    r"|The Periodic Table of Elements"
    r"|Permission to reproduce items"
    r"|Copyright Acknowledgements"
    r"|To avoid the issue of disclosure of answer-related information"
    r"|The boundaries and names shown, the designations used",
    re.I)


def last_content_page(doc: "fitz.Document") -> int:
    """
    One past the last page that can belong to a question.

    The final question runs to the end of the paper, so without this it
    swallows whatever follows it - and what follows a chemistry paper is the
    Periodic Table, printed sideways across a whole page.

    Only an unbroken run at the very end is trimmed, and the text has to be
    read before the furniture is stripped, since "BLANK PAGE" is furniture
    itself and would be gone by then.
    """
    end = doc.page_count
    while end > 1 and _END_MATTER.search(doc[end - 1].get_text()):
        end -= 1
    return end


def first_answer_table_page(doc: "fitz.Document") -> int | None:
    """
    Where a mark scheme's answers begin, or None if this is not one.

    Everything before it is the examiners' preamble - generic marking
    principles and a numbered list of guidance ("1 Examiners should consider
    the context...", "2 The examiner should not..."). That list counts up
    exactly like question numbers and is longer than the real sequence on a
    two-question paper, so it wins on every measure unless it is excluded
    outright.

    Read before the furniture is stripped, since the heading is furniture.
    """
    for index in range(doc.page_count):
        if _ANSWER_TABLE.search(mended_text(doc[index])):
            return index
    return None


def page_count(path: str | Path) -> int:
    """How many pages a PDF has (for showing in the window)."""
    with fitz.open(str(path)) as doc:
        return doc.page_count


def parse_pages(spec: str, total: int) -> list[int]:
    """'4-16,20' -> zero-based page indexes. Empty string means every page."""
    spec = (spec or "").strip()
    if not spec:
        return list(range(total))

    wanted: set[int] = set()
    for chunk in spec.replace(" ", "").split(","):
        if not chunk:
            continue
        if "-" in chunk:
            a, _, b = chunk.partition("-")
            try:
                start, end = int(a), int(b)
            except ValueError as exc:
                raise ValueError(f"'{chunk}' is not a page range like 4-16") from exc
            if start > end:
                start, end = end, start
            wanted.update(range(start, end + 1))
        else:
            try:
                wanted.add(int(chunk))
            except ValueError as exc:
                raise ValueError(f"'{chunk}' is not a page number") from exc

    pages = sorted(p - 1 for p in wanted if 1 <= p <= total)
    if not pages:
        raise ValueError(f"No pages selected - this PDF has pages 1 to {total}.")
    return pages


# --------------------------------------------------------------------------
# Rendering and cleaning
# --------------------------------------------------------------------------

def _is_furniture(text: str, rect: "fitz.Rect", page_rect: "fitz.Rect") -> bool:
    """
    Is this text block page furniture rather than question content?

    Judged from the text itself instead of fixed coordinates, so it keeps
    working on papers whose layout differs slightly.
    """
    body = text.strip()
    if not body:
        return False

    if "DO NOT WRITE" in body:
        return True

    # The sideways margin bar: tall, very narrow AND hard against the page
    # edge. The edge test matters - a column of y-axis labels on a graph is
    # also tall and narrow, and must survive.
    at_edge = (rect.x1 < page_rect.width * 0.06
               or rect.x0 > page_rect.width * 0.94)
    if at_edge and rect.width < 25 and rect.height > 100:
        return True

    # Cambridge's anti-copy barcode fonts render as control characters. This
    # is the strip that sits just above the first question.
    #
    # Only true control/format codes count. "Anything outside plain ASCII" is
    # far too broad for an exam paper: a table row reading
    # "type of organism ……… bacterium ………" is a third ellipsis characters and
    # was being deleted outright, and the same would go for any line carrying
    # degrees, +/-, alpha or a superscript.
    visible = [ch for ch in body if not ch.isspace()]
    odd = sum(1 for ch in visible if unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cn"))
    if len(visible) >= 6 and odd > len(visible) * 0.3:
        return True

    if re.fullmatch(r"\*[\s\d]*\*", body):        # * 0000800000004 *
        return True
    if any(k in body for k in ("UCLES", "Turn over", "BLANK PAGE")):
        return True

    # The awarding body's name, the copyright line and the page count appear
    # only in page furniture - the header row "Cambridge International AS/A
    # Level - March 2016  9701  22" and the footer "(c) Cambridge University
    # Press & Assessment 2024   Page 9 of 13". Confined to the head and foot
    # bands so they could never touch an answer that mentions Cambridge.
    edge_band = (rect.y1 < page_rect.height * 0.16
                 or rect.y0 > page_rect.height * 0.84)
    if edge_band and (_AWARDING.search(body) or _PAGE_OF.search(body)
                      or "©" in body):
        return True

    # A mark scheme repeats a banner and a table heading on every page, which
    # would otherwise land in the middle of a question where pages join. Both
    # come through as whole blocks - "PUBLISHED May/June 2017" and
    # "Question Answer Marks" - so they are matched as such.
    if "Mark Scheme" in body:
        return True
    if rect.y1 < page_rect.height * 0.16 and "PUBLISHED" in body:
        return True

    # The column heading is not confined to the top of the page: where a new
    # question starts halfway down, the table is restarted and the heading is
    # printed again mid-page. Anywhere it appears it is furniture, so the test
    # is on the words alone - every one of them has to be a column name, and
    # there have to be at least two, so a lone answer of "Total" survives.
    #
    # Up in the header band one word is enough, because some papers hand the
    # heading back as three separate blocks - "Question", "Answer", "Mark" -
    # and none of them then reached two words. The heading's ruled box was
    # left behind as an empty row at the top of a question.
    words = body.lower().replace("/", " ").split()
    columns = {"question", "answer", "answers", "mark", "marks", "total",
               "totals", "guidance", "notes", "part", "additional"}
    enough = 1 if rect.y1 < page_rect.height * 0.20 else 2
    if len(words) >= enough and all(word in columns for word in words):
        return True

    # The copyright notice on the final page. These phrases never turn up in
    # a question, so matching them is safe.
    lowered = body.lower()
    if any(k in lowered for k in ("permission to reproduce",
                                  "copyright acknowledgement",
                                  "cambridgeinternational.org")):
        return True

    near_top = rect.y1 < page_rect.height * 0.075
    near_bottom = rect.y0 > page_rect.height * 0.935
    if near_bottom:
        return True
    if near_top and (body.isdigit() or (len(body) <= 5 and body.isupper())):
        return True                                # page number, "DFD"
    return False


def _as_shown(page: "fitz.Page", rect: "fitz.Rect") -> "fitz.Rect":
    """
    Put a text rectangle into the coordinates the page is drawn in.

    Text comes out of PyMuPDF in the page's own, unrotated space. Mark
    schemes are portrait pages carrying /Rotate 90, so their text y values
    run to 789 on a page that displays as 595 tall - and every rule about
    "near the bottom" then fires on the middle of the answers.
    """
    rotation = getattr(page, "rotation", 0)
    return (rect * page.rotation_matrix) if rotation else rect


def _stitch(a: str, b: str) -> str | None:
    """
    Join two pieces of a broken word, dropping the part they repeat.

    Some papers hand their text back in overlapping pieces - "Que" and
    "estion", "Ma" and "arks", "1(" and "(a)(ii)". Where the pieces meet they
    repeat the characters in between, so the repeat comes out and the word
    goes back together.

    None means they share nothing, so they were never one word - two pieces
    that merely happen to sit close on the page stay apart.
    """
    for size in range(min(len(a), len(b)), 0, -1):
        if a.endswith(b[:size]):
            return a + b[size:]
    return None


def _mend(pieces: list) -> list:
    """Put one line's broken words back together, left to right."""
    out: list[list] = []
    for rect, text in sorted(pieces, key=lambda p: p[0].x0):
        if out and rect.x0 < out[-1][0].x1 - 0.5:      # they overlap on the page
            joined = _stitch(out[-1][1], text)
            if joined is not None:
                out[-1][0] = out[-1][0] | rect
                out[-1][1] = joined
                continue
        out.append([fitz.Rect(rect), text])
    return out


def mended_lines(page: "fitz.Page",
                 blocks: bool = False) -> list[tuple["fitz.Rect", str]]:
    """
    The page's text with any broken words repaired, as (rect, text).

    A shredded page is unreadable to every test here at once: no piece reads
    as a header, as a column heading, or as a question label, so the banner
    survives into the middle of a question and the question starts several
    parts in. Repairing the words first lets all three work as they do on a
    page that came out whole.

    `blocks` reads whole blocks rather than spans, which is what the
    furniture tests want.
    """
    lines: dict[int, list] = defaultdict(list)
    if blocks:
        for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
            body = " ".join(text.split())
            if body:
                box = _as_shown(page, fitz.Rect(x0, y0, x1, y1))
                lines[round(box.y0 / 3.0)].append((box, body))
    else:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    body = span["text"].strip()
                    if not body:
                        continue
                    box = _as_shown(page, fitz.Rect(*span["bbox"]))
                    lines[round(box.y0 / 3.0)].append((box, body))

    out = []
    for key in sorted(lines):
        out += [(rect, text) for rect, text in _mend(lines[key])]
    return out


def mended_text(page: "fitz.Page") -> str:
    """The whole page as one string, with broken words repaired."""
    return " ".join(text for _, text in mended_lines(page, blocks=True))


def furniture_rects(page: "fitz.Page") -> list["fitz.Rect"]:
    """Headers, footers and margin bars, in the coordinates the page shows."""
    shown = page.rect
    return [rect for rect, text in mended_lines(page, blocks=True)
            if _is_furniture(text, rect, shown)]


def stamp_rects(doc: "fitz.Document") -> dict[int, list["fitz.Rect"]]:
    """
    Where a download site has branded the pages, page by page.

    Copies of these papers circulate with a site's logo stamped in the same
    spot on every page. A figure never repeats in one place page after page,
    so a small image that does is a stamp. On most papers it sits below the
    crop and is never seen; on a few it straddles the crop line and leaves a
    slice of itself along the bottom of a question.
    """
    counts: Counter = Counter()
    boxes: dict = defaultdict(list)
    for index in range(doc.page_count):
        page = doc[index]
        limit = abs(page.rect.get_area()) * 0.08
        seen = set()
        for info in page.get_images(full=True):
            for rect in page.get_image_rects(info[0]):
                key = (round(rect.x0), round(rect.y0), round(rect.x1), round(rect.y1))
                if key in seen or abs(rect.get_area()) > limit:
                    continue
                seen.add(key)
                counts[key] += 1
                boxes[key].append((index, rect))

    enough = max(2, doc.page_count * 0.6)
    found: dict[int, list] = defaultdict(list)
    for key, count in counts.items():
        if count >= enough:
            for index, rect in boxes[key]:
                found[index].append(rect)
    return found


def whiten(page: "fitz.Page", rects: Sequence["fitz.Rect"]) -> None:
    """
    Blank the given areas, leaving white paper.

    These come straight from the image list, so they are already in the
    page's own space and need no turning. Drawing a white rectangle over the
    top does not work - the stamp is painted after it - so the pixels are
    redacted away instead.
    """
    if not rects:
        return
    for rect in rects:
        page.add_redact_annot(rect)
    for kwargs in ({"images": fitz.PDF_REDACT_IMAGE_PIXELS}, {}):
        try:
            page.apply_redactions(**kwargs)
            return
        except (AttributeError, TypeError):       # older PyMuPDF signature
            continue


def header_footer_bands(doc: "fitz.Document") -> tuple[float, float]:
    """
    Where the header ends and the footer starts, agreed across the document.

    Some pages come out of the PDF with their text shattered into overlapping
    fragments - "Question" arrives as "Qu", "uest", "tion", and "Mark Scheme"
    as "Mar", "rk S", "Sche", "eme" - so no fragment reads as a header and the
    whole banner survives into the middle of a question, at the page join.

    A Cambridge paper prints its header in the same place on every page, so a
    page that cannot recognise its own can borrow the measurement from the
    pages that can. Only a figure agreed by at least two pages is used.
    """
    heads: Counter = Counter()
    feet: Counter = Counter()
    for index in range(doc.page_count):
        page = doc[index]
        shown = page.rect
        band = shown.height * 0.16
        rects = furniture_rects(page)
        top = max((r.y1 for r in rects if r.y1 < band), default=0.0)
        bottom = min((r.y0 for r in rects if r.y0 > shown.height - band),
                     default=0.0)
        if top:
            heads[round(top)] += 1
        if bottom:
            feet[round(bottom)] += 1

    head = max((v for v, n in heads.items() if n >= 2), default=0)
    foot = min((v for v, n in feet.items() if n >= 2), default=0)
    return float(head), float(foot)


def tail_matter_top(page: "fitz.Page") -> float | None:
    """
    Where the data sheet begins on this page, if it does.

    A chemistry paper prints its table of constants directly under the last
    question's total, on the same page, so it cannot be dropped a page at a
    time. Everything from that heading to the foot of the page is reference
    material and belongs to no question.
    """
    tops = [_as_shown(page, fitz.Rect(b[0], b[1], b[2], b[3])).y0
            for b in page.get_text("blocks")
            if _TAIL_MATTER.search(" ".join(b[4].split()))]
    return min(tops) if tops else None


def strip_furniture(page: "fitz.Page",
                    bands: tuple[float, float] | None = None) -> None:
    """
    Blank the headers, footers and margin bars on this page.

    A header is widened to the full page before being removed, and line art
    inside it goes with the text. Older mark schemes rule their header as a
    table, and deleting only the words left its cell borders behind - which
    then turned up as stray rules in the middle of a question wherever two
    pages were joined.

    `bands` is where the rest of the document agrees its header ends and its
    footer starts. It is used only where this page found none of its own,
    which happens when its text comes through shattered into fragments.

    Redaction works in the page's own space, so the rectangles are converted
    back out of display coordinates before being applied.
    """
    rects = furniture_rects(page)
    tail = tail_matter_top(page)

    shown = page.rect
    band = shown.height * 0.16

    head, foot = bands or (0.0, 0.0)
    deeper = head > max((r.y1 for r in rects if r.y1 < band), default=0.0)
    higher = bool(foot) and foot < min(
        (r.y0 for r in rects if r.y0 > shown.height - band), default=shown.height)

    if not rects and tail is None and not (deeper or higher):
        return

    # Where the real content starts and ends, so a header can be swept from
    # the page edge right down to it. Clearing only the words left the ruled
    # box they sat in, which then read as an empty table row at the top of a
    # question; taking the whole region removes the borders with them.
    #
    # Only what lies beyond the furniture counts as content. A header carries
    # odds and ends the tests here do not name - a bare "February/March 2024"
    # off to the right - and letting one of those set the content line stopped
    # the sweep above the header's own bottom border, which then survived.
    head_end = max((r.y1 for r in rects if r.y1 < band), default=0.0)
    foot_start = min((r.y0 for r in rects if r.y0 > shown.height - band),
                     default=shown.height)
    keep = [_as_shown(page, fitz.Rect(b[0], b[1], b[2], b[3]))
            for b in page.get_text("blocks")
            if not _is_furniture(b[4], _as_shown(page, fitz.Rect(b[0], b[1], b[2], b[3])), shown)
            and b[4].strip()]
    content_top = min((r.y0 for r in keep if r.y0 >= head_end), default=shown.height)
    content_bottom = max((r.y1 for r in keep if r.y1 <= foot_start), default=0.0)

    # What the rest of the document agrees its header and footer measure, as a
    # floor rather than a fallback: a page that recognises its banner but not
    # the column heading below it would otherwise sweep only as far as the
    # banner and leave the heading standing. Held back by the content line
    # like every other sweep, or a page whose question starts high loses it.
    borrowed = []
    if deeper:
        borrowed.append(fitz.Rect(shown.x0, shown.y0, shown.x1,
                                  min(head + 2.0, content_top)))
    if higher:
        borrowed.append(fitz.Rect(shown.x0, max(foot - 2.0, content_bottom),
                                  shown.x1, shown.y1))

    # Stop a few points short of the content. The rule under a column heading
    # is also the rule over the first answer, and sweeping right up to the
    # content took it away - leaving the question with no top border and the
    # previous page's closing rule floating above it across the page join.
    clearance = 4.0

    widened = []
    for rect in rects:
        if rect.y1 < band:
            # Never past the content, whatever the clearance asks for. A
            # biology mark scheme prints its header 1.7pt above question 1,
            # and reaching for the clearance took the question's first line
            # with it - redaction deletes any text the rectangle touches.
            bottom = max(rect.y1, min(content_top - clearance, band))
            rect = fitz.Rect(shown.x0, shown.y0, shown.x1,
                             min(bottom, content_top))
        elif rect.y0 > shown.height - band:
            top = min(rect.y0, max(content_bottom + clearance,
                                   shown.height - band))
            rect = fitz.Rect(shown.x0, max(top, content_bottom),
                             shown.x1, shown.y1)
        elif rect.height < 40 and rect.width > shown.width * 0.5:
            # A column heading reprinted halfway down the page, where the
            # table restarts for a new question. Only the width is stretched -
            # taking it to the page edges lets the ruled box around it go too,
            # which a text-width rectangle leaves standing as an empty row.
            #
            # The shape test earns its keep: the sideways "DO NOT WRITE IN
            # THIS MARGIN" bar is furniture in this same middle band, and
            # widening that one blanked the whole page.
            rect = fitz.Rect(shown.x0, rect.y0 - 2.0, shown.x1, rect.y1 + 2.0)
        widened.append(rect)

    widened.extend(borrowed)
    if tail is not None:
        widened.append(fitz.Rect(shown.x0, tail - 2.0, shown.x1, shown.y1))

    back = ~page.rotation_matrix if getattr(page, "rotation", 0) else None
    for rect in widened:
        page.add_redact_annot(rect * back if back else rect)

    for kwargs in (
        {"images": fitz.PDF_REDACT_IMAGE_NONE,
         "graphics": fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED},
        {"images": fitz.PDF_REDACT_IMAGE_NONE},
        {},
    ):
        try:
            page.apply_redactions(**kwargs)
            return
        except (AttributeError, TypeError):       # older PyMuPDF signature
            continue


def body_spans(page: "fitz.Page") -> list[tuple[float, float, float, str]]:
    """
    Every non-empty text span in the body area, as (left, centre, y, text).

    Both the left edge and the horizontal centre are kept because question
    labels are left-aligned on a question paper but centred in a mark
    scheme's Question column - where "7(a)(i)" starts well left of "1(a)"
    while the two share a centre.

    Coordinates are the ones the page displays in, so they line up with the
    rendered image whatever rotation the PDF carries.
    """
    out = []
    shown = page.rect
    # Only a sliver is excluded. Headers and footers are already gone by
    # redaction, and a wider margin costs real content: some mark schemes
    # print a question number right at the top of the page, where a 7% guard
    # swallowed it - and losing question 1 loses everything before the next
    # number that survives.
    top = shown.height * 0.02
    bottom = shown.height * 0.98
    for box, text in mended_lines(page):
        if top < box.y0 < bottom:
            out.append((box.x0, (box.x0 + box.x1) / 2, box.y0, text))
    return out


#: "1", and the mark-scheme forms "1(a)", "1(b)(i)", "2(b)(iv)1.", "3(c)(ii)".
_QUESTION_LABEL = re.compile(r"(\d{1,2})\s*(?:\(.*)?\.?$")

#: A label opens its line - "2", "2.", "2(a)", "2 (b)(ii)".
_LABEL_START = re.compile(r"^\d{1,2}\s*(?:[.(]|$)")


def _question_number(text: str) -> int | None:
    """The question a label belongs to, or None if it is not one."""
    body = text.strip()
    if not body or not body[0].isdigit():
        return None
    match = _QUESTION_LABEL.fullmatch(body)
    if not match:
        return None
    number = int(match.group(1))
    return number if 1 <= number <= 40 else None


def _longest_run(numbers: list[int]) -> list[int]:
    """
    Positions forming the longest chain that counts up by one.

    Not simply "keep anything that follows the last kept number": a stray
    figure label early on would then anchor the chain and throw away every
    real question after it. This walks every possibility and keeps the best.
    """
    if not numbers:
        return []
    best_len = [1] * len(numbers)
    previous: list[int | None] = [None] * len(numbers)

    for i, value in enumerate(numbers):
        for j in range(i):
            if numbers[j] == value - 1 and best_len[j] + 1 > best_len[i]:
                best_len[i] = best_len[j] + 1
                previous[i] = j

    # Longest chain wins; ties go to the one starting nearest question 1.
    end = max(range(len(numbers)), key=lambda i: (best_len[i], -numbers[i]))
    chain = []
    node: int | None = end
    while node is not None:
        chain.append(node)
        node = previous[node]
    return chain[::-1]


def find_questions_qp(pages, tolerance: float = 4.0):
    """
    Where each question begins on a question paper.

    The numbers run down the left margin of flowing text, one to a question,
    and the parts - "(a)", "(i)" - are indented underneath in the body rather
    than listed beside the number. So there is nothing to snap back to: the
    first place a number appears is where its question starts.
    """
    return find_question_starts(pages, tolerance, snap_to_part=False)


def find_questions_ms(pages, tolerance: float = 4.0):
    """
    Where each question begins on a mark scheme.

    Every part is listed in the Question column - 1(a), 1(b), 1(d)(i) - and
    the column is centred, so parts of one question share a centre but not a
    left edge. Clustering can therefore split one real column in two and pick
    the half holding the longer labels, which would open each question
    several parts in. The result is snapped back to the first part carrying
    the number.
    """
    return find_question_starts(pages, tolerance, snap_to_part=True)


def find_question_starts(pages: list[list[tuple[float, float, str]]],
                         tolerance: float = 4.0,
                         snap_to_part: bool = True) -> list[tuple[int, float, int]]:
    """
    Locate where each question begins.

    Returns (page position, y in points, question number).

    Question numbers share one x position, further left than part labels like
    "(a)". Rather than assuming that is the left-most text on the page - a
    graph's axis caption is often further left still, which is exactly what
    used to break Biology papers - every column containing bare numbers is
    considered, and the one whose numbers count 1, 2, 3... furthest wins.

    Prefer `find_questions_qp` or `find_questions_ms`, which set the parts of
    this that differ between the two.
    """
    raw = []
    for index, spans in enumerate(pages):
        for left, centre, y0, text in spans:
            number = _question_number(text)
            if number is not None:
                raw.append((left, centre, index, y0, number, text))
    if not raw:
        return []

    best: list[tuple[int, float, int]] = []
    best_column: list[tuple[int, float, int]] = []
    best_score = ()
    best_key, best_x = 0, 0.0

    # Try lining the labels up by their left edges and by their centres:
    # question papers align one way, mark schemes the other.
    for key in (0, 1):
        # (aligning x, left edge, page, y, number) - the left edge travels
        # along so gap filling can use it later.
        # (aligning x, left, page, y, number, centre) - both edges travel
        # along, because the gap filling and the snap back to the first part
        # each need to know where this column really sits.
        candidates = [(c[key], c[0], c[2], c[3], c[4], c[1]) for c in raw]

        # A mark scheme lists every part in its Question column - 1(a),
        # 1(b)(i), 1(b)(ii)... - so the same number recurs many times. Only
        # its first appearance starts a question.
        seen: set[tuple[int, int]] = set()
        unique = []
        for row in sorted(candidates, key=lambda c: (c[2], c[3])):
            slot = (round(row[0] / max(1.0, tolerance)), row[4])
            if slot not in seen:
                seen.add(slot)
                unique.append(row)

        # A question number is printed out in the margin, to the left of
        # everything else on the page. Nothing else here is: the numbers that
        # compete with it come from inside tables, graph scales and the
        # periodic table, all of them set in from the edge.
        margin = min((c[0] for c in unique), default=0.0) + tolerance

        for row in unique:
            seed_x = row[0]
            column = [c for c in unique if abs(c[0] - seed_x) <= tolerance]
            column.sort(key=lambda c: (c[2], c[3]))     # reading order
            chain = _longest_run([c[4] for c in column])
            if len(chain) < 2:
                continue
            picked = [(column[i][2], column[i][3], column[i][4]) for i in chain]

            # Sitting in the margin comes first. On a Planning paper the two
            # question numbers are hopelessly outnumbered - by the group
            # numbers across the periodic table, which run 2..10 over three
            # pages, and by the scale up the side of a graph - and every test
            # below was losing to them.
            #
            # How many pages the run is spread over comes next, ahead of how
            # long it is. A numbered list inside one question - the NATO
            # alphabet on a Computer Science paper, a list of essay titles -
            # can easily run longer than the real question numbers, but it
            # never leaves its page.
            #
            # Then whether the column opens at question 1, which a real one
            # nearly always does and a table of data nearly never does. On a
            # Planning paper the two question numbers are outnumbered by the
            # figures in the results tables, and a column reading 2, 3, 25, 30
            # was beating the true 1, 2 on the count below.
            #
            # Distinct numbers in the whole column breaks the remaining ties,
            # because the column is read permissively afterwards: where two
            # columns tie on their consecutive run, the one holding more
            # question numbers is the one that yields more questions.
            # Left-aligned labels of differing width ("2" against "10(b)") can
            # otherwise split one real column in two, and the poorer half was
            # winning on position.
            numbers = {c[4] for c in column}
            score = (seed_x <= margin, len({p for p, _, _ in picked}),
                     min(numbers) == 1, len(picked), len(numbers), -seed_x)
            if score > best_score:
                best_score, best = score, picked
                best_key, best_x = key, seed_x
                best_column = [(c[2], c[3], c[4], c[1], c[5]) for c in column]

    if len(best) < 2:
        return []
    # In anything longer than a short extract, questions reach past one page.
    # The count of pages is the second term of the score, behind the margin.
    if best_score[1] < 2 and len(pages) > 5:
        return []

    # Now that the column is known, recover any number the strict label match
    # missed, then take everything from it that still counts upwards.
    #
    # Counting up by exactly one is the right test for *choosing* the column -
    # it is what separates real question numbers from stray digits. It is the
    # wrong test for *reading* the chosen column: where a paper prints no
    # label at all for question 3, insisting on 1,2,3,4 would discard 1 and 2
    # to keep 7..12. Merely increasing keeps all of them, and a question whose
    # own start was never found simply stays joined to the one before it.
    filled = _fill_gaps(pages, best_column, best_key, best_x, tolerance)
    chain = _longest_increasing([n for _, _, n in filled])
    picked = [filled[i] for i in chain]
    if not snap_to_part:
        return picked
    return _first_part(raw, best_column, picked, tolerance)


def _first_part(raw: list[tuple[float, float, int, float, int]],
                column: list[tuple[int, float, int, float]],
                found: list[tuple[int, float, int]],
                tolerance: float) -> list[tuple[int, float, int]]:
    """
    Move each question back to the first part that carries its number.

    A mark scheme lists every part in its Question column - 1(a), 1(b),
    1(d)(i) - centred, so they share a centre but not a left edge: "1(a)"
    starts at 81.6 where "1(d)(i)" starts at 76.7. Clustering by left edge
    splits one real column in two, and the half holding the longer labels
    wins on pages spanned, precisely because starting each question later
    pushes it onto a later page.

    The column choice is left alone - it reads the right numbers either way -
    but a question has to begin at its first part. Otherwise question 1 opened
    at 1(d)(i), everything from 1(a) to 1(c) was dropped as being above the
    first question, and 2(a) was left on the end of question 1.
    """
    if not found or not column:
        return found

    # Both bands come from the column's own members, and from the middle of
    # them rather than the extremes. One member is often a label that ran
    # into its own wording - "2 The orca, Orcinus orca, ..." - whose centre
    # lies far across the page; taking the widest pair let the band cover
    # most of the paper, and a question then snapped onto the subscript 2 of
    # "4CO2".
    lefts = sorted(c[3] for c in column)
    centres = sorted(c[4] for c in column)
    reach = tolerance * 2                    # labels differ in width
    mid_left = lefts[len(lefts) // 2]
    mid_centre = centres[len(centres) // 2]
    edge = (mid_left - reach, mid_left + reach)
    middle = (mid_centre - reach, mid_centre + reach)

    def in_column(left: float, centre: float) -> bool:
        return edge[0] <= left <= edge[1] or middle[0] <= centre <= middle[1]

    moved: list[tuple[int, float, int]] = []
    floor = (-1, -1.0)                       # never overtake the question above
    for index, y, number in found:
        best = (index, y)
        for left, centre, page, y0, n, text in raw:
            if n != number or not in_column(left, centre):
                continue
            # A label opens its line: "2", "2(a)", "2(b)(ii)". A digit buried
            # in a formula does not, however well it happens to line up.
            if not _LABEL_START.match(text.strip()):
                continue
            if (page, y0) < best and (page, y0) > floor:
                best = (page, y0)
        moved.append((best[0], best[1], number))
        floor = best
    return moved


def _longest_increasing(numbers: list[int]) -> list[int]:
    """Positions forming the longest strictly increasing run (gaps allowed)."""
    if not numbers:
        return []
    best_len = [1] * len(numbers)
    previous: list[int | None] = [None] * len(numbers)
    for i, value in enumerate(numbers):
        for j in range(i):
            if numbers[j] < value and best_len[j] + 1 > best_len[i]:
                best_len[i] = best_len[j] + 1
                previous[i] = j
    end = max(range(len(numbers)), key=lambda i: (best_len[i], -numbers[i]))
    chain = []
    node: int | None = end
    while node is not None:
        chain.append(node)
        node = previous[node]
    return chain[::-1]


def _fill_gaps(pages, column: list[tuple[int, float, int, float]], key: int,
               column_x: float, tolerance: float) -> list[tuple[int, float, int]]:
    """
    Recover a question whose number was swallowed by its own text.

    Typesetting sometimes runs the label and the wording into one span, as in
    "10 The complex number..." or "3 Use the quadratic formula M1", which no
    longer reads as a bare label - and losing 3 costs you 1 and 2 as well,
    because the run has to be consecutive.

    Such a span is matched on its LEFT edge, never its centre: the trailing
    wording drags the centre far to the right while the left edge stays on
    the column. The search covers 1 upwards, since a paper starts at 1 even
    when the strict pass first saw question 7 - and on past the highest one
    found, since a gap is not the only way a question goes missing. Where the
    swallowed label belongs to the LAST question there is no gap to give it
    away, and the question simply stayed joined to the one before it: a maths
    paper ending "11 Functions f and g are defined by..." came out with
    questions 10 and 11 in one picture.
    """
    found = sorted([(c[0], c[1], c[2]) for c in column], key=lambda c: (c[0], c[1]))
    lefts = [c[3] for c in column]
    if not found:
        return found
    have = {n for _, _, n in found}
    low, high = min(lefts) - tolerance, max(lefts) + tolerance
    # Past the end as well as in between. Nothing is lost by asking: a number
    # that is not there simply is not found, and the first miss stops it.
    beyond = list(range(max(have) + 1, min(max(have) + 12, 41)))
    missing = [n for n in range(1, max(have) + 1) if n not in have]
    if not missing and not beyond:
        return found

    recovered = list(found)

    def look(number: int):
        """Where this question's swallowed label is, if it is anywhere."""
        # It has to sit between the questions either side of it.
        before = max([(p, y) for p, y, n in recovered if n < number], default=(-1, -1.0))
        after = min([(p, y) for p, y, n in recovered if n > number], default=(10 ** 6, 0.0))
        pattern = re.compile(rf"^{number}(?=$|[\s(])")
        for index, spans in enumerate(pages):
            for left, centre, y, text in spans:
                aligned = (low <= left <= high
                           or abs((left if key == 0 else centre) - column_x) <= tolerance)
                if not aligned or not pattern.match(text.strip()):
                    continue
                if (index, y) <= before or (index, y) >= after:
                    continue
                return (index, y, number)
        return None

    for number in missing:
        hit = look(number)
        if hit:
            recovered.append(hit)
            recovered.sort(key=lambda c: (c[0], c[1]))

    # Past the end, stopping at the first number that is not there - so a
    # paper of ten questions costs one extra look, not twelve.
    for number in beyond:
        hit = look(number)
        if not hit:
            break
        recovered.append(hit)
        recovered.sort(key=lambda c: (c[0], c[1]))

    return recovered


def render_page(page: "fitz.Page", s: CleanSettings) -> Image.Image:
    """Rasterise one PDF page, cropped to the content window."""
    if s.strip_furniture:
        strip_furniture(page)
    rect = page.rect
    clip = fitz.Rect(
        rect.x0 + rect.width * s.crop_left,
        rect.y0 + rect.height * s.crop_top,
        rect.x0 + rect.width * s.crop_right,
        rect.y0 + rect.height * s.crop_bottom,
    )
    pix = page.get_pixmap(dpi=s.dpi, clip=clip, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def clean_page(img: Image.Image, s: CleanSettings,
               marks: Sequence[float] = ()) -> tuple[Image.Image | None, list[int]]:
    """
    Strip a rendered page down to its content.

    `marks` are row numbers to follow through the cleaning - the cropping and
    gap-collapsing both move rows around, so question positions have to be
    carried along rather than recomputed afterwards.

    Returns (image, moved marks), or (None, []) when nothing meaningful is
    left, so a blank page can be dropped from the flow.
    """
    fs = s.fuse_settings()
    rows = [float(m) for m in marks]

    ink = pf._ink_mask(img, s.ink_threshold)
    if s.skip_blank_pages and ink.mean() < s.blank_ink_fraction:
        return None, []

    if s.remove_answer_lines:
        img = pf.remove_answer_lines(img, fs)      # same size, marks unmoved

    # Only the top and bottom are trimmed here. Cropping each page to its own
    # left edge as well made the indentation jump wherever two pages joined -
    # a part that starts halfway across the page came out hard against the
    # margin because that page happened to have nothing further left. The
    # sides are trimmed once, off the finished strip, so every page keeps the
    # same frame of reference.
    _, top, _, bottom = pf.trim_box(img, fs)
    img = img.crop((0, top, img.width, bottom))
    rows = [r - top for r in rows]

    if s.collapse_gaps:
        keep = pf.collapse_keep_mask(img, fs)
        if not keep.all():
            moved = np.cumsum(keep) - 1            # old row -> new row
            limit = len(moved) - 1
            rows = [float(moved[min(max(int(r), 0), limit)]) for r in rows]
            img = Image.fromarray(np.asarray(img)[keep])

    if s.clean_background:
        img = pf.clean_background(img, fs)

    ink = pf._ink_mask(img, s.ink_threshold)
    if s.skip_blank_pages and ink.mean() < s.blank_ink_fraction:
        return None, []

    height = img.height
    return img, [int(min(max(r, 0), height - 1)) for r in rows]


# --------------------------------------------------------------------------
# Reflow
# --------------------------------------------------------------------------

def reflow(pages: Sequence[Image.Image], s: CleanSettings) -> Image.Image:
    """
    Stack the cleaned pages into one continuous strip, left-aligned.

    The side margins come off here rather than page by page, so a part that
    is indented stays indented no matter which page it landed on.
    """
    if not pages:
        raise ValueError("Nothing left after cleaning - every page looked blank.")

    gap = max(0, round(s.gap_between_pages_pt * s.dpi / PT_PER_INCH))
    width = max(p.width for p in pages)
    height = sum(p.height for p in pages) + gap * (len(pages) - 1)

    strip = Image.new("RGB", (width, height), "white")
    y = 0
    for p in pages:
        strip.paste(p, (0, y))
        y += p.height + gap

    columns = np.flatnonzero(pf._ink_mask(strip, s.ink_threshold).any(axis=0))
    if len(columns):
        strip = strip.crop((int(columns[0]), 0, int(columns[-1]) + 1, strip.height))
    return strip


def paginate(strip: Image.Image, page_height_px: int, s: CleanSettings) -> list[Image.Image]:
    """
    Slice the continuous strip into page-sized pieces.

    Cuts are nudged back onto a blank row so a line of text is never sliced
    in half. If no blank row is available it cuts square, which only happens
    inside a very tall diagram.
    """
    if page_height_px < 10:
        raise ValueError("Output page is too small to hold anything.")

    blank = ~pf._ink_mask(strip, s.ink_threshold).any(axis=1)
    total = strip.height
    slices: list[Image.Image] = []
    y = 0

    while y < total:
        end = min(total, y + page_height_px)
        if end < total:
            earliest = y + int(page_height_px * 0.70)   # don't cut too short
            cut = next((yy for yy in range(end - 1, earliest, -1) if blank[yy]), None)
            if cut:
                end = cut
        slices.append(strip.crop((0, y, strip.width, end)))
        y = end
        while y < total and blank[y]:      # don't start a page with white space
            y += 1

    return slices


def _unbroken(row: "np.ndarray") -> int:
    """The longest run of ink along one row, in pixels."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], row.view(np.int8), [0]))))
    return int((edges[1::2] - edges[::2]).max()) if len(edges) else 0


def split_questions(strip: Image.Image, marks: Sequence[tuple[int, int]],
                    out_dir: Path, stem: str, s: CleanSettings,
                    keep_head: bool = True) -> list[Path]:
    """
    Cut the continuous strip into one PNG per question.

    `marks` is (row in the strip, question number). Every image keeps the full
    strip width so they all come out the same size, and nothing is rescaled -
    the pixels are exactly those of the working resolution.

    `keep_head` decides what happens to whatever sits above question 1. On a
    question paper that is the paper's own instruction line and belongs with
    it; on a mark scheme the answer table opens at question 1, so anything
    above is the tail of the abbreviations page and is dropped.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    height = strip.height
    scale = s.dpi / PT_PER_INCH
    ink = pf._ink_mask(strip, s.ink_threshold)
    ink_per_row = ink.sum(axis=1)
    blank = ink_per_row == 0
    # A mark scheme's table has unbroken vertical borders, so no row inside it
    # is ever truly blank - every row carries those few border pixels, and that
    # constant is the paper's real zero. It has to be measured rather than
    # guessed: a fixed fraction of the page width outgrows a short line of text
    # in a narrow column, and the seam test then fired on the text itself and
    # sliced a question's first line in half.
    inked = ink_per_row[ink_per_row > 0]
    floor = int(np.percentile(inked, 5)) if inked.size else 0
    seam = ink_per_row <= max(2, round(floor * 1.5))
    # The rule between two table rows is where a mark scheme really divides,
    # and it is nearly solid ink, so neither test above will ever take it.
    #
    # It has to be an unbroken run of ink, not merely a lot of it. A line of
    # dense maths reaches 0.56 of the width where a real rule reaches 1.0, so
    # counting ink alone mistook a line of text for a rule and cut through the
    # middle of it. A word is the longest unbroken thing text ever draws.
    #
    # A question paper has no such table, so there is nothing here for it to
    # find and the test is off - that removes the failure rather than tuning
    # around it.
    if s.cut_on_rules:
        divider = np.array([_unbroken(ink[y]) >= strip.width * 0.5
                            if ink_per_row[y] >= strip.width * 0.35 else False
                            for y in range(height)])
    else:
        divider = np.zeros(height, dtype=bool)
    # A wide black picture looks the same one row at a time, so only a thin
    # run counts as a rule.
    rule_max = max(2, round(6 * scale))
    # Reach well above the label. A question's first row can carry taller ink
    # than the number itself - the numerator of a fraction rides above it - and
    # a short reach cut straight through it.
    lookback = max(6, round(40 * scale))
    margin = max(2, round(s.question_margin_pt * scale))

    def rule_run(y: int) -> tuple[int, int] | None:
        """The (top, bottom) rows of the ruled line through `y`, if it is one."""
        top = bottom = y
        while top > 0 and divider[top - 1]:
            top -= 1
        while bottom + 1 < height and divider[bottom + 1]:
            bottom += 1
        return (top, bottom) if bottom - top < rule_max else None

    # Turn each question's start row into a pair: where this question opens and
    # where the question above it closes. They differ only across a ruled line,
    # which both sides keep - a table row with a missing border looks broken.
    cuts: list[tuple[int, int]] = []
    for row, _ in marks:
        window = range(row - 1, max(-1, row - lookback), -1)
        rule = next((r for r in map(rule_run, (y for y in window if divider[y]))
                     if r is not None), None)
        if rule is not None:
            cuts.append((rule[0], rule[1] + 1))
            continue
        cut = next((y for y in window if blank[y]), None)
        if cut is None:
            cut = next((y for y in window if seam[y]), None)
        if cut is None:
            cut = row - 2
        cut = max(0, cut)
        cuts.append((cut, cut))

    # Rows carrying something a reader would miss: not white paper, not the
    # table's own borders, not a ruled line.
    content = ~seam & ~divider

    def close_in(start: int, end: int) -> tuple[int, int]:
        """
        Pull the crop in to the ruled lines that box the real content.

        A mark scheme draws each page's whole table as one path, so redacting
        the column header removes its words but never its cell - and an empty
        ruled row was left at the head of a question, and another at its foot
        wherever the header was reprinted mid-page. They cannot be taken out
        in the PDF, so they are dropped here: everything past the rule nearest
        the content goes, and that rule stays to box the question in.
        """
        real = np.flatnonzero(content[start:end])
        if not len(real):
            return start, start
        first, last = start + int(real[0]), start + int(real[-1])

        above = np.flatnonzero(divider[start:first])
        if len(above):
            rule = start + int(above[-1])
            # White paper between the rule and the content means the rule
            # closes the page above rather than opening this question, so it
            # is left behind with it.
            if not blank[rule + 1:first].any():
                first = rule
                while first > start and divider[first - 1]:
                    first -= 1

        below = np.flatnonzero(divider[last + 1:end])
        if len(below):
            last = last + 1 + int(below[0])
            while last + 1 < end and divider[last + 1]:
                last += 1
        return first, last + 1

    written: list[Path] = []
    for i, ((opens, _), (_, number)) in enumerate(zip(cuts, marks)):
        start = 0 if i == 0 and keep_head else opens
        end = cuts[i + 1][1] if i + 1 < len(cuts) else height
        start, end = close_in(start, end)
        if end - start < 10:
            continue

        piece = strip.crop((0, start, strip.width, end))

        canvas = Image.new("RGB", (piece.width + 2 * margin, piece.height + 2 * margin),
                           "white")
        canvas.paste(piece, (margin, margin))

        path = out_dir / f"{stem}_q{number}.png"
        canvas.save(path, format="PNG", optimize=True, compress_level=9, dpi=(s.dpi, s.dpi))
        written.append(path)

    return written


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def write_pdf(slices: Sequence[Image.Image], dst: Path,
              page_w_pt: float, page_h_pt: float, s: CleanSettings) -> Path:
    """Place each slice on its own page and save, losslessly (PNG/Flate)."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()
    margin = s.page_margin_pt
    content_w = page_w_pt - 2 * margin

    for piece in slices:
        if s.grayscale:
            piece = piece.convert("L")
        page = doc.new_page(width=page_w_pt, height=page_h_pt)
        scale = content_w / piece.width
        rect = fitz.Rect(margin, margin, margin + content_w,
                         margin + piece.height * scale)
        buf = io.BytesIO()
        piece.save(buf, format="PNG", optimize=True)
        page.insert_image(rect, stream=buf.getvalue())

    doc.save(str(dst), deflate=True, garbage=4)
    doc.close()
    return dst


# --------------------------------------------------------------------------
# The whole job
# --------------------------------------------------------------------------

@dataclass
class Result:
    path: Path
    pages_in: int
    pages_used: int
    pages_out: int
    height_before_pt: float
    height_after_pt: float
    questions: list[Path] = field(default_factory=list)
    questions_dir: Path | None = None

    @property
    def saved_percent(self) -> float:
        if self.height_before_pt <= 0:
            return 0.0
        return (1 - self.height_after_pt / self.height_before_pt) * 100


def clean_pdf(src: str | Path, dst: str | Path | None = None,
              s: CleanSettings | None = None,
              progress: Callable[[int, int, str], None] | None = None,
              marks: list[tuple[int, float, int]] | None = None) -> Result:
    """
    Clean `src` and write the result. `progress(done, total, message)` is
    called as it goes, so a GUI can show a bar.

    `marks` overrides where the questions are taken to begin, as (page, y in
    points, number). Repairing a paper works out the right answer by other
    means - usually from the other side of the same paper - and this is how
    that answer is handed back in to be cut.
    """
    s = s or CleanSettings()
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(f"No such file: {src}")

    doc = fitz.open(str(src))
    if doc.needs_pass:
        doc.close()
        raise ValueError("That PDF is password protected, so it cannot be read.")
    if doc.page_count == 0:
        doc.close()
        raise ValueError("That PDF has no pages.")

    try:
        # Read the whole document's text first. The question numbers answer
        # two things at once: where each question begins, and where the front
        # matter ends - so the page range no longer rests on spotting dotted
        # answer rulings, which some papers draw differently.
        # Read before stripping: the answer-table heading is itself furniture,
        # and so is the "BLANK PAGE" that marks the end of the paper.
        answers_from = first_answer_table_page(doc)
        # Settle what kind of document this is once, and work from that
        # setup for the rest of the run. Deciding it page by page is what
        # let one kind's rules misfire on the other.
        s = profile_for(s.kind or detect_kind(src, doc), s)

        content_end = last_content_page(doc) if s.trim_end_matter else doc.page_count
        stamps = stamp_rects(doc)
        bands = header_footer_bands(doc) if s.strip_furniture else None

        all_spans = []
        for index in range(doc.page_count):
            page = doc[index]
            whiten(page, stamps.get(index, ()))
            if s.strip_furniture:
                strip_furniture(page, bands)
            all_spans.append(body_spans(page))

        # A mark scheme's preamble is not searched for questions - its
        # numbered guidance list would otherwise be read as the paper.
        searchable = all_spans
        if answers_from:
            searchable = [[] if i < answers_from else spans
                          for i, spans in enumerate(all_spans)]

        found = marks if marks is not None else (
            find_questions_ms(searchable) if s.kind == "ms"
            else find_questions_qp(searchable))

        if s.pages.strip():
            wanted = parse_pages(s.pages, doc.page_count)
        else:
            # Never trim away a page a question actually starts on, however
            # the end of the paper reads.
            stop = max(content_end, (found[-1][0] + 1) if found else 1)
            start = 0
            if s.skip_front_matter:
                start = found[0][0] if found else first_question_page(doc)
            wanted = list(range(start, max(stop, start + 1)))

        first = doc[wanted[0]]
        page_w_pt, page_h_pt = first.rect.width, first.rect.height

        position_of = {index: i for i, index in enumerate(wanted)}
        starts_by_page: dict[int, list[tuple[float, int]]] = {}
        if s.split_questions:
            for index, y, number in found:
                if index in position_of:
                    starts_by_page.setdefault(position_of[index], []).append((y, number))

        cleaned: list[Image.Image] = []
        page_marks: list[list[tuple[int, int]]] = []   # per page: (row, number)

        for i, index in enumerate(wanted):
            if progress:
                progress(i + 1, len(wanted) + 1, f"Cleaning page {index + 1}")

            page = doc[index]
            here = starts_by_page.get(i, [])
            crop_top_pt = page.rect.height * s.crop_top
            rows = [(y - crop_top_pt) * s.dpi / PT_PER_INCH for y, _ in here]

            image, moved = clean_page(render_page(page, s), s, rows)
            if image is not None:
                cleaned.append(image)
                page_marks.append(list(zip(moved, (n for _, n in here))))
    finally:
        doc.close()

    if not cleaned:
        raise ValueError(
            "Every selected page came out blank. Check the page range, or "
            "turn off 'skip blank pages'."
        )

    if progress:
        progress(len(wanted) + 1, len(wanted) + 1, "Building the PDF")

    strip = reflow(cleaned, s)

    # Same stacking arithmetic reflow() uses, so the marks land where the
    # pages actually ended up in the strip.
    strip_marks: list[tuple[int, int]] = []
    gap = max(0, round(s.gap_between_pages_pt * s.dpi / PT_PER_INCH))
    offset = 0
    for image, marks in zip(cleaned, page_marks):
        strip_marks.extend((offset + row, number) for row, number in marks)
        offset += image.height + gap
    strip_marks.sort()

    # How tall a page is, measured in strip pixels.
    content_w_pt = page_w_pt - 2 * s.page_margin_pt
    content_h_pt = page_h_pt - 2 * s.page_margin_pt
    pt_per_px = content_w_pt / strip.width
    page_height_px = max(10, int(content_h_pt / pt_per_px))

    slices = paginate(strip, page_height_px, s)

    if dst is None:
        dst = DEFAULT_OUTPUT_DIR
    dst = Path(dst)
    # Anything that is not explicitly a .pdf is treated as a folder to put the
    # file in - including a folder that does not exist yet.
    if dst.is_dir() or dst.suffix.lower() != ".pdf":
        dst = dst / f"{src.stem}_cleaned.pdf"

    # Skipping the PDF is worth it in bulk: at high dpi writing it costs about
    # as much again as everything before it, and a batch may only want the
    # per-question images.
    if s.save_pdf:
        write_pdf(slices, dst, page_w_pt, page_h_pt, s)

    questions: list[Path] = []
    questions_dir: Path | None = None
    if s.split_questions and strip_marks:
        if progress:
            progress(len(wanted) + 1, len(wanted) + 1, "Saving each question")
        questions_dir = dst.parent / f"{src.stem}_questions"
        questions = split_questions(strip, strip_marks, questions_dir, src.stem, s,
                                    keep_head=s.keep_above_first)

    return Result(
        path=dst,
        pages_in=len(wanted),
        pages_used=len(cleaned),
        pages_out=len(slices),
        height_before_pt=len(wanted) * page_h_pt,
        height_after_pt=strip.height * pt_per_px,
        questions=questions,
        questions_dir=questions_dir,
    )


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def _cli(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pdfcleaner",
        description="Strip a past paper down to its questions and reflow it.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("pdf", help="the paper to clean")
    p.add_argument("--out", default=None, help="output file or folder")
    p.add_argument("--pages", default="", help='e.g. "4-16" (default: all)')
    p.add_argument("--dpi", type=int, default=CleanSettings.dpi)
    p.add_argument("--max-gap", type=float, default=CleanSettings.max_gap_pt,
                   help="longest blank run to keep, in points")
    p.add_argument("--margin", type=float, default=CleanSettings.page_margin_pt)
    p.add_argument("--grayscale", action="store_true", help="smaller file")
    p.add_argument("--questions", action="store_true",
                   help="also save each question as its own PNG")
    p.add_argument("--keep-answer-lines", action="store_true")
    p.add_argument("--remove-solid-rules", action="store_true",
                   help="also erase solid rules (can eat graph axes)")
    p.add_argument("--no-collapse", action="store_true", help="keep blank space")
    p.add_argument("--keep-blank-pages", action="store_true")
    p.add_argument("--full-page", action="store_true",
                   help="do not crop the header/footer/margin bar")
    p.add_argument("--keep-furniture", action="store_true",
                   help="keep page numbers, footers and barcodes")
    p.add_argument("--keep-front-matter", action="store_true",
                   help="keep the cover, data and formulae pages")
    a = p.parse_args(argv)

    s = CleanSettings(
        dpi=a.dpi, pages=a.pages, max_gap_pt=a.max_gap, page_margin_pt=a.margin,
        grayscale=a.grayscale, remove_answer_lines=not a.keep_answer_lines,
        remove_solid_rules=a.remove_solid_rules, collapse_gaps=not a.no_collapse,
        skip_blank_pages=not a.keep_blank_pages,
        strip_furniture=not a.keep_furniture,
        skip_front_matter=not a.keep_front_matter,
        split_questions=a.questions,
    )
    if a.full_page:
        s = replace(s, crop_left=0.0, crop_top=0.0, crop_right=1.0, crop_bottom=1.0)

    def show(done: int, total: int, message: str) -> None:
        print(f"  [{done:>3}/{total}] {message}", end="\r", flush=True)

    try:
        result = clean_pdf(a.pdf, a.out, s, progress=show)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1

    print(" " * 60, end="\r")
    print(f"Saved {result.path}")
    print(f"  {result.pages_in} pages in -> {result.pages_out} pages out "
          f"({result.pages_in - result.pages_used} blank pages dropped)")
    print(f"  {result.saved_percent:.0f}% of the vertical space removed")
    if result.questions:
        print(f"  {len(result.questions)} questions saved to {result.questions_dir}")
    elif a.questions:
        print("  No question numbers were found, so no separate PNGs were written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
