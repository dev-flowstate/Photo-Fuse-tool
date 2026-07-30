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
    sys.exit("Missing dependencies. Run:  python -m pip install -r requirements.txt")

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit(
        "PyMuPDF is not installed - that is what reads the PDF.\n"
        "Run this once, then try again:\n\n"
        "    python -m pip install -r requirements.txt\n"
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
# Page selection
# --------------------------------------------------------------------------

def first_question_page(doc: "fitz.Document") -> int:
    """
    Index of the first page that looks like a question rather than front
    matter.

    Question pages carry dotted answer rulings; the cover, the data sheet and
    the formulae pages do not. Falls back to page 1 if nothing matches.
    """
    for index in range(doc.page_count):
        if re.search(r"\.{20,}", doc[index].get_text("text")):
            return index
    return 0


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
    # is the strip that sits just above the first question. Whitespace is
    # ignored: a two-line block like "0\n0" (a graph's axis labels) is normal
    # text, and counting its newline as exotic would delete the labels.
    visible = [ch for ch in body if not ch.isspace()]
    odd = sum(1 for ch in visible if not (32 <= ord(ch) < 127))
    if len(visible) >= 6 and odd > len(visible) * 0.3:
        return True

    if re.fullmatch(r"\*[\s\d]*\*", body):        # * 0000800000004 *
        return True
    if any(k in body for k in ("UCLES", "Turn over", "BLANK PAGE")):
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


def strip_furniture(page: "fitz.Page") -> None:
    """Permanently blank the headers, footers and margin bars on this page."""
    targets = []
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        rect = fitz.Rect(x0, y0, x1, y1)
        if _is_furniture(text, rect, page.rect):
            targets.append(rect)
    if not targets:
        return
    for rect in targets:
        page.add_redact_annot(rect)
    try:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    except (AttributeError, TypeError):           # older PyMuPDF signature
        page.apply_redactions()


def body_spans(page: "fitz.Page") -> list[tuple[float, float, str]]:
    """Every non-empty text span in the body area, as (x0, y0, text)."""
    out = []
    top = page.rect.height * 0.07
    bottom = page.rect.height * 0.93
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"].strip()
                x0, y0 = span["bbox"][0], span["bbox"][1]
                if text and top < y0 < bottom:
                    out.append((x0, y0, text))
    return out


def question_number_column(pages: list[list[tuple[float, float, str]]]) -> float | None:
    """
    The x position where question numbers sit.

    On a Cambridge paper the question number is the only thing in the
    left-most column - part labels like "(a)" are indented from it - so the
    smallest x we see across the body text is that column.
    """
    xs = [x for spans in pages for x, _, _ in spans]
    return min(xs) if xs else None


def find_question_starts(pages: list[list[tuple[float, float, str]]],
                         tolerance: float = 6.0) -> list[tuple[int, float, int]]:
    """
    Locate where each question begins.

    Returns (page position in the selection, y in points, question number).
    A candidate is a bare 1-2 digit number sitting in the question-number
    column; candidates are then kept only while they count up 1, 2, 3..., so
    a stray figure label can't start a bogus question.
    """
    column = question_number_column(pages)
    if column is None:
        return []

    candidates = []
    for index, spans in enumerate(pages):
        for x0, y0, text in spans:
            if re.fullmatch(r"\d{1,2}", text) and abs(x0 - column) <= tolerance:
                candidates.append((index, y0, int(text)))
    candidates.sort(key=lambda c: (c[0], c[1]))

    starts: list[tuple[int, float, int]] = []
    for index, y0, number in candidates:
        if not starts:
            starts.append((index, y0, number))
        elif number == starts[-1][2] + 1:
            starts.append((index, y0, number))
    return starts


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

    left, top, right, bottom = pf.trim_box(img, fs)
    img = img.crop((left, top, right, bottom))
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
    """Stack the cleaned pages into one continuous strip, left-aligned."""
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


def split_questions(strip: Image.Image, marks: Sequence[tuple[int, int]],
                    out_dir: Path, stem: str, s: CleanSettings) -> list[Path]:
    """
    Cut the continuous strip into one PNG per question.

    `marks` is (row in the strip, question number). Every image keeps the full
    strip width so they all come out the same size, and nothing is rescaled -
    the pixels are exactly those of the working resolution.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    blank = ~pf._ink_mask(strip, s.ink_threshold).any(axis=1)
    height = strip.height
    scale = s.dpi / PT_PER_INCH
    lookback = max(4, round(18 * scale))     # how far to hunt for a clean break
    margin = max(2, round(s.question_margin_pt * scale))

    # Turn each question's start row into a cut, nudged up onto blank paper so
    # the number at the top of the question is never clipped.
    cuts: list[int] = []
    for row, _ in marks:
        cut = next((y for y in range(row - 1, max(-1, row - lookback), -1) if blank[y]),
                   max(0, row - 2))
        cuts.append(max(0, cut))

    written: list[Path] = []
    for i, (cut, (_, number)) in enumerate(zip(cuts, marks)):
        start = 0 if i == 0 else cut          # keep anything above question 1
        end = cuts[i + 1] if i + 1 < len(cuts) else height
        if end - start < 10:
            continue

        piece = strip.crop((0, start, strip.width, end))

        # Trim blank paper off the top and bottom only - the width has to stay
        # identical across every question.
        ink_rows = np.flatnonzero(pf._ink_mask(piece, s.ink_threshold).any(axis=1))
        if not len(ink_rows):
            continue
        piece = piece.crop((0, int(ink_rows[0]), piece.width, int(ink_rows[-1]) + 1))

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
              progress: Callable[[int, int, str], None] | None = None) -> Result:
    """
    Clean `src` and write the result. `progress(done, total, message)` is
    called as it goes, so a GUI can show a bar.
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
        if s.skip_front_matter and not s.pages.strip():
            start = first_question_page(doc)
            wanted = list(range(start, doc.page_count))
        else:
            wanted = parse_pages(s.pages, doc.page_count)
        first = doc[wanted[0]]
        page_w_pt, page_h_pt = first.rect.width, first.rect.height

        # First pass: drop the furniture, then read the text layer. The
        # question-number column and the 1, 2, 3... sequence can only be
        # judged across the whole selection, not page by page - a page that
        # opens with "(b)" has no number on it at all.
        starts_by_page: dict[int, list[tuple[float, int]]] = {}
        if s.split_questions:
            spans = []
            for index in wanted:
                page = doc[index]
                if s.strip_furniture:
                    strip_furniture(page)
                spans.append(body_spans(page))
            for position, y, number in find_question_starts(spans):
                starts_by_page.setdefault(position, []).append((y, number))

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

    write_pdf(slices, dst, page_w_pt, page_h_pt, s)

    questions: list[Path] = []
    questions_dir: Path | None = None
    if s.split_questions and strip_marks:
        if progress:
            progress(len(wanted) + 1, len(wanted) + 1, "Saving each question")
        questions_dir = dst.parent / f"{src.stem}_questions"
        questions = split_questions(strip, strip_marks, questions_dir, src.stem, s)

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
