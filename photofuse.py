"""
Photo Fuse - core engine
========================

Fuses several crops of the SAME past-paper question into one clean, tightly
cropped PNG, named exactly the way the Easify contributor brief requires.

What it does to each part, in order:
  1. strip border lines   - removes page rules / scan edges sitting at the border
  2. trim whitespace      - crops tightly around the actual ink
  3. collapse gaps        - shrinks huge blank vertical gaps inside the question
  4. clean background     - turns grey scan paper into pure white

Then it stacks the parts, padding the narrower ones with white so every part
lines up, and resizes the result to the target width (1000-1200 px per brief).

Use it from the GUI (photofuse_gui.py) or from the command line:

    python photofuse.py part1.png part2.png ^
        --subject math --paper 1 --variant 2 --chapter Quadratics ^
        --year 2022 --season on --q 4 --type Q
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

try:
    import numpy as np
    from PIL import Image, ImageFilter
except ImportError:  # pragma: no cover - startup guard for contributors
    sys.exit(
        "Missing dependencies.\n\n"
        "Easiest fix: double-click \"1 - INSTALL (run me first).bat\".\n\n"
        "Or run one of these in this folder:\n"
        "    py -m pip install -r requirements.txt\n"
        "    python -m pip install -r requirements.txt\n"
    )

# Pillow renamed the resampling constants in 9.1; support old and new.
try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:  # Pillow < 9.1
    RESAMPLE = Image.LANCZOS


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------

SUBJECTS = ("math", "physics", "cs", "chem", "bio")
SEASONS = {"on": "Oct/Nov", "mj": "May/June", "fm": "Feb/March"}
KINDS = ("Q", "MS")

#: Where finished images are written, relative to this file.
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
#: Optional helper file that mirrors columns A-I of the spreadsheet.
ROWS_CSV_NAME = "_spreadsheet_rows.csv"
CSV_COLUMNS = [
    "subject", "paper", "chapter", "year", "difficulty",
    "marks", "q_filename", "ms_filename", "youtube_url",
]


def enable_hidpi() -> float:
    """
    Tell Windows this app draws its own pixels, and report the display scale.

    Without this, a laptop set to 125% scaling stretches the whole window
    afterwards: text goes soft and the window ends up a quarter taller than
    Tk believes, which pushes the buttons off the bottom of the screen.
    Returns the scale factor (1.0 when there is nothing to do).
    """
    if sys.platform != "win32":
        return 1.0
    try:
        from ctypes import windll
        try:
            windll.shcore.SetProcessDpiAwareness(1)      # system DPI aware
        except (AttributeError, OSError):
            windll.user32.SetProcessDPIAware()           # older Windows
        return max(1.0, windll.user32.GetDpiForSystem() / 96.0)
    except (AttributeError, OSError, ImportError):
        return 1.0


def slugify(text: str) -> str:
    """'Coordinate Geometry' -> 'coord-geometry'-safe token: lowercase, hyphens only."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


@dataclass
class Meta:
    """Everything needed to name the file (and, optionally, log a sheet row)."""

    subject: str = "math"
    paper: str = "1"
    variant: str = ""          # optional CIE variant, e.g. 2 -> p12
    chapter: str = ""
    year: str = ""
    season: str = "on"
    question: str = ""         # 4, or 4a
    kind: str = "Q"            # Q or MS
    # Spreadsheet-only extras (never appear in the file name):
    difficulty: str = ""
    marks: str = ""
    youtube_url: str = ""

    @property
    def paper_token(self) -> str:
        """
        The PV token: paper number followed by variant.

        p11 = paper 1 variant 1, p12 = paper 1 variant 2, p23 = paper 2
        variant 3 - exactly as the brief spells it out.
        """
        return f"p{slugify(self.paper)}{slugify(self.variant)}"

    @property
    def stem(self) -> str:
        """Everything before the trailing _Q / _MS."""
        return (
            f"{slugify(self.subject)}_{self.paper_token}_{slugify(self.chapter)}"
            f"_{slugify(self.year)}{slugify(self.season)}_q{slugify(self.question)}"
        )

    def filename(self, kind: str | None = None) -> str:
        """The image name. Pass a kind to ask for the other one of the pair."""
        return f"{self.stem}_{kind or self.kind}.png"

    def problems(self) -> list[str]:
        """Human-readable list of what still needs filling in. Empty == good to go."""
        issues = []
        if slugify(self.subject) not in SUBJECTS:
            issues.append(f"subject must be one of {', '.join(SUBJECTS)}")
        if not re.fullmatch(r"[1-6]", str(self.paper).strip()):
            issues.append("paper must be a single digit 1-6")
        # The brief's PV token is paper + variant, so the variant is not
        # optional: physics_p11_... means paper 1 variant 1.
        if not re.fullmatch(r"\d", str(self.variant).strip()):
            issues.append("variant is required (1 digit) - p11 = paper 1 variant 1")
        if not slugify(self.chapter):
            issues.append("chapter is empty")
        if not re.fullmatch(r"\d{4}", str(self.year).strip()):
            issues.append("year must be 4 digits, e.g. 2025")
        if slugify(self.season) not in SEASONS:
            issues.append("season must be on, mj or fm")
        if not slugify(self.question):
            issues.append("question number is empty")
        if self.kind not in KINDS:
            issues.append("type must be Q or MS")
        return issues


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

@dataclass
class Settings:
    """Tuning knobs for the cleaning + fusing pipeline."""

    # A pixel is "ink" when its grey value is below this. Raise it if faint
    # pencil-grey text is being trimmed away; lower it if grey scan speckle is
    # being treated as content.
    ink_threshold: int = 200

    strip_edge_lines: bool = True   # remove page rules stuck to the crop edge
    edge_line_depth: float = 0.10   # only look this far in (fraction of the side)
    edge_line_coverage: float = 0.55  # a row this dark, edge-to-edge, is a "line"

    trim: bool = True               # crop tightly around the ink
    trim_padding: int = 10          # breathing room left around the ink

    collapse_gaps: bool = True      # shrink blank vertical space inside the question
    max_gap: int = 45               # blank runs longer than this shrink down to it

    clean_background: bool = True   # grey scan paper -> pure white
    clean_threshold: int = 225      # anything lighter than this becomes white

    # Wipe the dotted "......................." answer rulings the student
    # would write on. Mark allocations like [2] sitting on the same line are
    # kept - only the ruling itself is erased.
    remove_answer_lines: bool = True
    # Solid full-width rules are a different animal: graph axes, plateaus in a
    # velocity-time curve and table borders all look exactly like one, so this
    # stays OFF unless the paper rules its answer space with unbroken lines.
    remove_solid_rules: bool = False
    answer_line_min_span: float = 0.45   # must reach across this much of the width
    answer_line_max_density: float = 0.75  # closely spaced dots still count as dotted
    answer_line_thickness: int = 0       # 0 = work it out from the image width

    direction: str = "vertical"     # vertical (stack) or horizontal (side by side)
    align: str = "left"             # left / center / right (top/middle/bottom if horizontal)
    gap: int = 22                   # white space between parts
    margin: int = 18                # white border around the finished image
    match_part_widths: bool = False  # scale parts to a common width before joining

    output_width: int = 1100        # brief asks for 1000-1200 px
    keep_original_size: bool = False  # True = never resize at all (max quality)
    no_upscale: bool = True         # never blow up a small image (keeps it sharp)
    sharpen: bool = True            # crisp the text back up after a downscale

    # Rename-only: take the picture exactly as it is and just save it under
    # the right name. Useful for crops that are already clean - the per-
    # question PNGs the PDF Cleaner produces, for instance.
    passthrough: bool = False


# --------------------------------------------------------------------------
# Image helpers
# --------------------------------------------------------------------------

def load_image(path: str | Path) -> Image.Image:
    """Open any image (incl. transparent PNGs) flattened onto white RGB."""
    img = Image.open(path)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        flat = Image.new("RGB", img.size, "white")
        flat.paste(img, mask=img.split()[-1])
        return flat
    return img.convert("RGB")


def _ink_mask(img: Image.Image, threshold: int) -> np.ndarray:
    """Boolean array, True where the pixel is dark enough to be content."""
    return np.asarray(img.convert("L")) < threshold


def _leading_edge_cut(mask: np.ndarray, s: Settings) -> int:
    """
    How many rows to shave off the TOP of `mask`.

    Walks inward past blank rows, eating any full-width dark rule it meets.
    Stops the moment it hits normal content, so table borders that belong to
    the question are safe - only rules separated from content by whitespace
    (i.e. page furniture at the crop edge) get removed.
    """
    height = mask.shape[0]
    limit = max(1, int(height * s.edge_line_depth))
    cut = 0
    i = 0
    while i < limit:
        coverage = mask[i].mean()
        if coverage == 0:                     # blank row - keep looking
            i += 1
            continue
        if coverage >= s.edge_line_coverage:  # a rule: eat the whole thing
            j = i
            while j < height and mask[j].mean() >= s.edge_line_coverage * 0.6:
                j += 1
            cut = j
            i = j
            continue
        break                                 # real content - stop
    return cut


def strip_edge_lines(img: Image.Image, s: Settings) -> Image.Image:
    """Remove page rules / scanner edges from all four sides."""
    mask = _ink_mask(img, s.ink_threshold)
    top = _leading_edge_cut(mask, s)
    bottom = _leading_edge_cut(mask[::-1], s)
    left = _leading_edge_cut(mask.T, s)
    right = _leading_edge_cut(mask.T[::-1], s)

    w, h = img.size
    box = (left, top, w - right, h - bottom)
    if box[2] - box[0] < 10 or box[3] - box[1] < 10:
        return img  # refuse to shred the image
    return img.crop(box)


def trim_box(img: Image.Image, s: Settings) -> tuple[int, int, int, int]:
    """
    The crop box that hugs the ink, with `trim_padding` px of white left on.

    Exposed separately from `trim_whitespace` so callers that need to follow a
    position through the crop (the PDF cleaner tracks where each question
    starts) can ask for the box instead of guessing it.
    """
    mask = _ink_mask(img, s.ink_threshold)
    rows, cols = mask.any(axis=1), mask.any(axis=0)
    if not rows.any():
        return 0, 0, img.width, img.height     # blank - nothing to trim towards

    pad = s.trim_padding
    return (
        max(0, int(cols.argmax()) - pad),
        max(0, int(rows.argmax()) - pad),
        min(img.width, img.width - int(cols[::-1].argmax()) + pad),
        min(img.height, img.height - int(rows[::-1].argmax()) + pad),
    )


def trim_whitespace(img: Image.Image, s: Settings) -> Image.Image:
    """Crop tightly around the ink, leaving `trim_padding` px of white."""
    return img.crop(trim_box(img, s))


def collapse_keep_mask(img: Image.Image, s: Settings) -> np.ndarray:
    """
    Which rows survive gap collapsing, as a boolean per row.

    Returned rather than applied so a caller can map old row numbers onto new
    ones with a cumulative sum.
    """
    mask = _ink_mask(img, s.ink_threshold)
    blank = ~mask.any(axis=1)
    keep = np.ones(img.height, dtype=bool)
    if not blank.any():
        return keep

    i = 0
    while i < img.height:
        if not blank[i]:
            i += 1
            continue
        j = i
        while j < img.height and blank[j]:
            j += 1
        if (j - i) > s.max_gap:
            head = s.max_gap // 2            # keep some white on each side
            keep[i + head: j - (s.max_gap - head)] = False
        i = j

    return keep


def collapse_vertical_gaps(img: Image.Image, s: Settings) -> Image.Image:
    """
    Shrink long blank horizontal bands (e.g. the answer space left for the
    student) down to `max_gap` px, so the fused question has no dead air.
    """
    keep = collapse_keep_mask(img, s)
    if keep.all():
        return img
    return Image.fromarray(np.asarray(img)[keep])


def _run_lengths(mask: np.ndarray) -> np.ndarray:
    """
    For every ink pixel, the length of the unbroken vertical run it belongs to.

    Lets us tell a 3 px-tall dot from the 12 px-tall stroke of a letter without
    needing full connected-component labelling.
    """
    height, width = mask.shape
    up = np.zeros((height, width), np.int32)
    acc = np.zeros(width, np.int32)
    for y in range(height):
        acc = np.where(mask[y], acc + 1, 0)
        up[y] = acc

    down = np.zeros((height, width), np.int32)
    acc = np.zeros(width, np.int32)
    for y in range(height - 1, -1, -1):
        acc = np.where(mask[y], acc + 1, 0)
        down[y] = acc

    return np.where(mask, up + down - 1, 0)


def remove_answer_lines(img: Image.Image, s: Settings) -> Image.Image:
    """
    Erase the dotted (or solid) answer rulings that past papers leave for the
    student's working.

    A ruling row is recognised by three things at once: its ink reaches right
    across the page, it is sparse (dots) or completely solid (a rule), and
    almost all of its ink is vertically thin. Body text fails the thinness
    test, so it is never touched.

    Only the thin ink on those rows is whitened, which is why a "[2]" mark
    allocation sitting at the end of a ruling survives - its brackets and
    digits are tall.
    """
    mask = _ink_mask(img, s.ink_threshold)
    height, width = mask.shape
    if not mask.any():
        return img

    thickness = s.answer_line_thickness or max(3, round(width / 220))
    vertical = _run_lengths(mask)
    thin = mask & (vertical <= thickness)
    # Anything with a long vertical stroke - a building outline, an axis, an
    # arrow shaft - means this row is inside a drawing, not an answer space.
    # Letters and the brackets of a "[2]" are far shorter than this.
    tall_counts = (vertical > thickness * 6).sum(axis=1)

    counts = mask.sum(axis=1)
    thin_counts = thin.sum(axis=1)
    dotted_rows = np.zeros(height, dtype=bool)
    solid_rows = np.zeros(height, dtype=bool)
    min_span = s.answer_line_min_span * width

    for y in np.flatnonzero(counts):
        cols = np.flatnonzero(mask[y])
        span = cols[-1] - cols[0] + 1
        if span < min_span:
            continue                                   # too short to be a ruling
        if thin_counts[y] < counts[y] * 0.8:
            continue                                   # mostly tall ink = text
        if tall_counts[y]:
            continue                                   # a drawing runs through here
        density = counts[y] / span
        if density <= s.answer_line_max_density:
            dotted_rows[y] = True
        elif s.remove_solid_rules and density >= 0.85 and span >= 0.70 * width:
            solid_rows[y] = True                       # a drawn rule, not dots

    if not (dotted_rows.any() or solid_rows.any()):
        return img

    # On dotted rows, spare wide strokes so a "[2]" or an underlined word
    # survives. A solid rule has no such neighbours, so it goes wholesale.
    horizontal = _run_lengths(mask.T).T
    erase = thin & ((horizontal <= thickness * 1.5) & dotted_rows[:, None]
                    | solid_rows[:, None])
    if not erase.any():
        return img

    keep_ink = mask & ~erase
    ruling = dotted_rows | solid_rows
    arr = np.asarray(img).copy()
    touched = False

    for top, bottom in _bands(ruling):
        if bottom - top > thickness * 2.5:
            continue          # too tall to be a ruling - leave it alone

        # Whiten the whole band except where ink worth keeping lives. Erasing
        # only the dark dot cores would leave their soft grey halos behind as
        # visible ghosts, so the band is cleared column by column instead.
        columns = _spread(keep_ink[top:bottom + 1].any(axis=0), thickness)
        if columns.all():
            continue
        arr[top:bottom + 1, ~columns] = 255
        touched = True

    return Image.fromarray(arr) if touched else img


def _bands(flags: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous True runs of a 1-D boolean array, as inclusive (start, end)."""
    runs: list[tuple[int, int]] = []
    start = None
    for i, on in enumerate(flags):
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(flags) - 1))
    return runs


def _spread(flags: np.ndarray, amount: int) -> np.ndarray:
    """Widen every True by `amount` on both sides (keeps glyph anti-aliasing)."""
    out = flags.copy()
    for shift in range(1, max(1, amount) + 1):
        out[shift:] |= flags[:-shift]
        out[:-shift] |= flags[shift:]
    return out


def clean_background(img: Image.Image, s: Settings) -> Image.Image:
    """Force near-white scan paper to pure white, leaving text untouched."""
    grey = np.asarray(img.convert("L"))
    arr = np.asarray(img).copy()
    arr[grey >= s.clean_threshold] = 255
    return Image.fromarray(arr)


def prepare_part(img: Image.Image, s: Settings) -> Image.Image:
    """Run the per-part cleaning pipeline."""
    if s.passthrough:
        return img
    if s.strip_edge_lines:
        img = strip_edge_lines(img, s)
    if s.remove_answer_lines:
        img = remove_answer_lines(img, s)   # before trimming: rulings must not
                                            # define the crop box
    if s.trim:
        img = trim_whitespace(img, s)
    if s.collapse_gaps:
        img = collapse_vertical_gaps(img, s)
    if s.clean_background:
        img = clean_background(img, s)
    return img


# --------------------------------------------------------------------------
# Fusing
# --------------------------------------------------------------------------

def _offset(free_space: int, align: str) -> int:
    if align in ("center", "middle"):
        return free_space // 2
    if align in ("right", "bottom"):
        return free_space
    return 0  # left / top


def fuse(images: Sequence[Image.Image], s: Settings) -> Image.Image:
    """
    Join already-prepared parts into one image.

    Parts narrower than the widest one are padded with white on the side that
    does not reach, according to `s.align` - nothing is ever stretched.
    """
    if not images:
        raise ValueError("No images to fuse.")

    # A lone picture in rename-only mode is handed back untouched: no margin,
    # no resize, not a single pixel altered.
    if s.passthrough and len(images) == 1:
        return images[0]

    parts = list(images)

    if s.direction == "horizontal":
        if s.match_part_widths:
            tallest = max(p.height for p in parts)
            parts = [p.resize((max(1, round(p.width * tallest / p.height)), tallest), RESAMPLE)
                     for p in parts]
        strip_h = max(p.height for p in parts)
        total_w = sum(p.width for p in parts) + s.gap * (len(parts) - 1)
        canvas = Image.new("RGB", (total_w + 2 * s.margin, strip_h + 2 * s.margin), "white")
        x = s.margin
        for p in parts:
            canvas.paste(p, (x, s.margin + _offset(strip_h - p.height, s.align)))
            x += p.width + s.gap
    else:
        if s.match_part_widths:
            widest = max(p.width for p in parts)
            parts = [p.resize((widest, max(1, round(p.height * widest / p.width))), RESAMPLE)
                     for p in parts]
        strip_w = max(p.width for p in parts)
        total_h = sum(p.height for p in parts) + s.gap * (len(parts) - 1)
        canvas = Image.new("RGB", (strip_w + 2 * s.margin, total_h + 2 * s.margin), "white")
        y = s.margin
        for p in parts:
            canvas.paste(p, (s.margin + _offset(strip_w - p.width, s.align), y))
            y += p.height + s.gap

    return resize_to_width(canvas, s)


def resize_to_width(img: Image.Image, s: Settings) -> Image.Image:
    """
    Scale to the target output width.

    Skipped entirely when `keep_original_size` is set - that is the maximum
    quality path, since every pixel of the original survives. Downscaling uses
    Lanczos (the sharpest of Pillow's filters) followed by a light unsharp
    mask, which puts back the crispness that any resampler costs you.
    """
    target = s.output_width
    if s.passthrough or s.keep_original_size or target <= 0 or img.width == target:
        return img
    if s.no_upscale and img.width < target:
        return img

    height = max(1, round(img.height * target / img.width))
    shrinking = target < img.width
    img = img.resize((target, height), RESAMPLE)
    if shrinking and s.sharpen:
        img = img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=3))
    return img


def build(paths: Sequence[str | Path], s: Settings) -> Image.Image:
    """Load -> clean -> fuse. Returns the finished image."""
    if not paths:
        raise ValueError("Add at least one image first.")

    parts = [prepare_part(load_image(p), s) for p in paths]

    # An accidentally blank part would otherwise show up as an empty white band.
    inked = [p for p in parts if _ink_mask(p, s.ink_threshold).any()]
    return fuse(inked or parts[:1], s)


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------

def save(img: Image.Image, meta: Meta, out_dir: Path, overwrite: bool = True) -> Path:
    """Write the PNG under its correct Easify name. Returns the full path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / meta.filename()

    if path.exists() and not overwrite:
        stem, n = path.stem, 2
        while path.exists():
            path = out_dir / f"{stem}-{n}.png"
            n += 1

    # PNG is lossless, so "quality" here is only about not throwing pixels
    # away: no palette reduction, maximum (lossless) compression effort.
    img.save(path, format="PNG", optimize=True, compress_level=9, dpi=(200, 200))
    return path


def log_spreadsheet_row(out_dir: Path, meta: Meta, filename: str) -> Path:
    """
    Keep `_spreadsheet_rows.csv` in step with what has been exported.

    One row per question. Saving the Q fills q_filename, saving the MS fills
    ms_filename on the same row. Open it in Excel and paste into columns A-I
    of the Questions tab. The .xlsx stays the real deliverable - this is a
    time-saver, not a replacement.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / ROWS_CSV_NAME

    rows: dict[str, dict[str, str]] = {}
    if csv_path.exists():
        with csv_path.open("r", newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                key = (row.get("q_filename") or row.get("ms_filename") or "")
                key = key.rsplit("_", 1)[0]
                if key:
                    rows[key] = {c: row.get(c, "") for c in CSV_COLUMNS}

    row = rows.get(meta.stem, {c: "" for c in CSV_COLUMNS})
    row.update({
        "subject": slugify(meta.subject),
        "paper": str(meta.paper).strip(),
        "chapter": str(meta.chapter).strip(),
        "year": str(meta.year).strip(),
        "difficulty": str(meta.difficulty).strip(),
        "marks": str(meta.marks).strip(),
        "youtube_url": str(meta.youtube_url).strip(),
    })
    # Both names come from the one entry - they differ only by _Q / _MS.
    row["q_filename"] = meta.filename("Q")
    row["ms_filename"] = meta.filename("MS")
    rows[meta.stem] = row

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow(rows[key])
    return csv_path


def export(paths: Sequence[str | Path], meta: Meta, out_dir: Path | None = None,
           s: Settings | None = None, write_csv: bool = True) -> tuple[Path, Image.Image]:
    """Full run: build the image, save it, update the CSV helper."""
    s = s or Settings()
    out_dir = Path(out_dir or DEFAULT_OUTPUT_DIR)
    issues = meta.problems()
    if issues:
        raise ValueError("Fix these before exporting:\n  - " + "\n  - ".join(issues))

    img = build(paths, s)
    path = save(img, meta, out_dir)
    if write_csv:
        log_spreadsheet_row(out_dir, meta, path.name)
    return path, img


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def _cli(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="photofuse",
        description="Fuse crops of one past-paper question into one correctly named PNG.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("images", nargs="+", help="the parts, in top-to-bottom order")

    g = p.add_argument_group("naming")
    g.add_argument("--subject", required=True, choices=list(SUBJECTS))
    g.add_argument("--paper", required=True, help="paper number, e.g. 1")
    g.add_argument("--variant", default="", help="optional variant, e.g. 2 -> p12")
    g.add_argument("--chapter", required=True, help="e.g. Quadratics")
    g.add_argument("--year", required=True, help="e.g. 2022")
    g.add_argument("--season", required=True, choices=list(SEASONS))
    g.add_argument("--q", dest="question", required=True, help="question number, e.g. 4")
    g.add_argument("--type", dest="kind", required=True, choices=list(KINDS))
    g.add_argument("--difficulty", default="", help="Easy/Medium/Hard - for the CSV only")
    g.add_argument("--marks", default="", help="total marks - for the CSV only")
    g.add_argument("--youtube", dest="youtube_url", default="", help="for the CSV only")

    o = p.add_argument_group("output")
    o.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR), help="output folder")
    o.add_argument("--width", type=int, default=Settings.output_width)
    o.add_argument("--original-size", action="store_true",
                   help="do not resize at all - highest possible quality")
    o.add_argument("--no-sharpen", action="store_true", help="skip the post-resize sharpening")
    o.add_argument("--no-csv", action="store_true", help="skip the spreadsheet CSV")

    f = p.add_argument_group("fusing")
    f.add_argument("--direction", choices=("vertical", "horizontal"), default="vertical")
    f.add_argument("--align", choices=("left", "center", "right"), default="left")
    f.add_argument("--gap", type=int, default=Settings.gap)
    f.add_argument("--margin", type=int, default=Settings.margin)
    f.add_argument("--max-gap", type=int, default=Settings.max_gap)
    f.add_argument("--ink-threshold", type=int, default=Settings.ink_threshold)
    f.add_argument("--match-widths", action="store_true", help="scale parts to equal width")
    f.add_argument("--no-trim", action="store_true")
    f.add_argument("--no-clean", action="store_true")
    f.add_argument("--no-collapse", action="store_true")
    f.add_argument("--keep-edge-lines", action="store_true")
    f.add_argument("--keep-answer-lines", action="store_true",
                   help="keep the dotted answer rulings instead of erasing them")
    f.add_argument("--remove-solid-rules", action="store_true",
                   help="also erase solid full-width rules (can eat graph axes)")
    f.add_argument("--allow-upscale", action="store_true")

    a = p.parse_args(argv)

    settings = replace(
        Settings(),
        direction=a.direction, align=a.align, gap=a.gap, margin=a.margin,
        max_gap=a.max_gap, ink_threshold=a.ink_threshold,
        match_part_widths=a.match_widths, output_width=a.width,
        trim=not a.no_trim, clean_background=not a.no_clean,
        collapse_gaps=not a.no_collapse, strip_edge_lines=not a.keep_edge_lines,
        remove_answer_lines=not a.keep_answer_lines,
        remove_solid_rules=a.remove_solid_rules,
        keep_original_size=a.original_size, sharpen=not a.no_sharpen,
        no_upscale=not a.allow_upscale,
    )
    meta = Meta(
        subject=a.subject, paper=a.paper, variant=a.variant, chapter=a.chapter,
        year=a.year, season=a.season, question=a.question, kind=a.kind,
        difficulty=a.difficulty, marks=a.marks, youtube_url=a.youtube_url,
    )

    try:
        path, img = export(a.images, meta, a.out, settings, write_csv=not a.no_csv)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Saved {path}  ({img.width} x {img.height} px)")
    if not 1000 <= img.width <= 1200:
        print(f"Note: width {img.width} px is outside the brief's 1000-1200 px range.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
