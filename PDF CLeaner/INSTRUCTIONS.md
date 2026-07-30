# PDF Cleaner — how to use it

Drop in a whole past paper, get back a **tight, continuous PDF**:

- the dotted answer rulings are erased,
- the blank answer space is squashed,
- the barcode, page number, footer and the vertical "DO NOT WRITE IN THIS
  MARGIN" bar are removed,
- blank pages and the cover / data / formulae pages are skipped,
- and the leftovers are **reflowed**, so a question that used to straddle two
  pages now runs on without a break.

That last part is the point: you no longer have to screenshot half a question
on page 4, the other half on page 5, and fuse them.

> **Real result** — Cambridge Physics 9702/21 May/June 2025:
> 13 question pages in → **8 pages out, 47% of the vertical space removed**,
> with every diagram, graph grid and `[2]` mark allocation intact.

---

## Important: keep this folder where it is

This folder must stay **inside** the `Photo Fuse tool` folder, right next to
`photofuse.py`:

```
Photo Fuse tool/
├── photofuse.py          ← PDF Cleaner shares the line-erasing code in here
├── photofuse_gui.py
└── PDF CLeaner/          ← you are here
    ├── pdfcleaner.py
    ├── pdfcleaner_gui.py
    └── output/           ← cleaned PDFs land here
```

If you move it out on its own it will stop working and tell you so. Send the
**whole** `Photo Fuse tool` folder when you share it.

---

## Part 1 — Setup (do this once)

1. Install Python 3.10+ from <https://www.python.org/downloads/> and **tick
   "Add python.exe to PATH"** on the first screen.
2. Double-click **`1 - INSTALL (run me first).bat`**.

That installs three things: Pillow, numpy and **PyMuPDF** (which reads PDFs).
It is a separate install from Photo Fuse's, so run it even if you already set
up Photo Fuse.

<details>
<summary>By hand, or on Mac/Linux</summary>

```bash
python -m pip install -r requirements.txt
python pdfcleaner_gui.py
```
</details>

---

## Part 2 — Cleaning a paper

Double-click **`2 - START PDF Cleaner.bat`**, or drag a PDF straight onto
**`Drop PDF here.bat`** to open it with that paper already loaded.

1. **Choose the PDF** (or drop it on the .bat).
2. Leave **Pages** blank — it finds the first real question page by itself and
   skips the cover and formula sheet. Type `4-16` if you want to force a range.
3. Press **Clean PDF** (or `Ctrl+Enter`). The bar shows progress; a 16-page
   paper takes roughly 10–20 seconds.
4. Press **Open the cleaned PDF** to check it.

The result is saved next to this file in `output/`, named
`<original name>_cleaned.pdf`. The original is never modified.

---

## Part 2b — Output separate questions

Tick **Output separate questions** (bottom of the options box) and you also get
**one PNG per question**, ready to drop straight into Photo Fuse. No cropping,
no screenshots.

They land in their own folder next to the cleaned PDF:

```
output/
├── 9702_s25_qp_21_cleaned.pdf
└── 9702_s25_qp_21_questions/
    ├── 9702_s25_qp_21_q1.png
    ├── 9702_s25_qp_21_q2.png
    └── ... one per question
```

- **Every question is complete.** Each image runs from its number to the start
  of the next one, so all parts — (a), (b), (c), every figure and the closing
  `[Total: 9]` — are in the one file, even though they used to be spread over
  two pages of the original.
- **They are all exactly the same width** (1424 px at 200 dpi), because they
  are cut from the same reflowed column. Only the height varies.
- **Nothing is rescaled.** The pixels are straight from the working
  resolution, saved as lossless PNG with the dpi tag set. Raise **Quality** to
  300 or 400 dpi if you want bigger images — that is the only thing that
  changes their size.

> Tested on Physics 9702/21 M/J 2025: all **7 questions** came out correctly
> split, each with its own `[Total: n]`, at 1424 × 1483–2781 px.

### How it decides where a question starts

It reads the PDF's text layer and looks for a bare number sitting in the
left-most column — the question-number column, which is further left than part
labels like `(a)`. It then keeps only numbers that count up 1, 2, 3…, so a
stray figure label can't start a bogus question. The cut is nudged onto blank
paper so the number at the top is never clipped.

If a paper numbers its questions differently and nothing is found, you simply
get the cleaned PDF and a note saying no questions were detected — nothing
breaks.

**Note:** this runs as part of cleaning, not on an already-cleaned PDF. The
cleaned PDF is made of images and has no text layer left, so the question
numbers can only be read from the original. Just tick the box when you clean.

### Straight into Photo Fuse

1. Clean the paper with **Output separate questions** ticked.
2. Open Photo Fuse, click **Add images…**, pick `..._q4.png`.
3. Fill in the boxes, press Save.

One question, one file, one row — no cropping and no fusing at all.

---

## Part 3 — The options

| Option | What it does | When to change it |
|---|---|---|
| **Pages** | which pages to use — `4-16`, or `4-9,12` | Leave blank unless the auto-detect guesses wrong |
| **Quality (dpi)** | rendering resolution | 200 is a good balance. Use 300–400 for a crisper file, 150 for a smaller one |
| **Max blank gap** | blank runs taller than this shrink to it, in points | Raise to ~60 to leave more writing room; lower to ~8 to pack tighter |
| **Erase answer lines** | wipes the dotted rulings | Untick to keep the paper looking original |
| **Squash blank space** | closes the empty answer space | Untick to keep the real spacing |
| **Remove headers/footers/margins** | drops barcodes, page numbers, footers and the margin bar | Untick if a paper's layout confuses it |
| **Skip blank pages** | drops pages with nothing on them | Rarely needed |
| **Skip cover & formula pages** | starts at the first page with answer rulings | Untick to keep the data/formulae sheets |
| **Also erase solid rules** | erases unbroken full-width lines too | **Leave off.** It can eat graph axes and table borders. Only use it on a paper that rules its answer space with solid lines |
| **Grayscale** | drops colour | Tick it if the file is too big to email |
| **Output separate questions** | also saves one PNG per question — see Part 2b | Tick it whenever you are building topical questions |

### A note on what is deliberately kept

- `[2]`, `[Total: 9]` and other mark allocations — they sit on the same line as
  a ruling, and the tool keeps them while erasing the dots around them.
- **Answer slots** like `time = ................ s [2]` keep their dots. They
  are one line each, so they cost almost nothing, and they tell the student
  what to answer and in what unit.
- Everything inside a diagram. The eraser refuses to touch any row that has a
  long vertical stroke running through it, which is what protects graph axes,
  building outlines, arrows, circuit wires and table borders.

---

## Part 4 — Command line

```bash
python pdfcleaner.py "9702_s25_qp_21.pdf"
python pdfcleaner.py "paper.pdf" --questions
python pdfcleaner.py "paper.pdf" --pages 4-16 --dpi 300 --out "D:\cleaned"
```

Extras: `--questions`, `--max-gap 60`, `--margin 24`, `--grayscale`, `--keep-answer-lines`,
`--no-collapse`, `--keep-blank-pages`, `--keep-front-matter`,
`--keep-furniture`, `--full-page`, `--remove-solid-rules`.

Full list: `python pdfcleaner.py --help`

---

## Part 5 — Using it with Photo Fuse

**The fast way** — tick **Output separate questions** (Part 2b). You get a
finished PNG per question, so you skip screenshotting entirely: just add the
file in Photo Fuse, fill in the boxes, Save.

**The manual way**, if you want a different crop (one part of a question, say):
open the cleaned PDF, screenshot what you want, and drop it into Photo Fuse.
Because questions are no longer split across page breaks, one crop is usually
enough — and if you do need two, Photo Fuse still fuses them exactly as before.

---

## Something went wrong?

| Problem | Fix |
|---|---|
| `Could not find photofuse.py` | This folder was moved out of `Photo Fuse tool`. Put it back |
| `PyMuPDF is not installed` | Run `1 - INSTALL (run me first).bat` |
| `That PDF is password protected` | Unlock or re-download the paper |
| It started at the wrong page | Type an explicit range in **Pages**, e.g. `4-16` |
| A graph or table lost lines | Untick **Also erase solid rules** (it should be off by default) |
| Part of a question got wiped | Untick **Remove headers/footers/margins** — that paper's layout differs from Cambridge's |
| Text looks soft | Raise **Quality** to 300 dpi |
| File too big | Tick **Grayscale**, or drop to 150 dpi |
| Blank pages left in | Tick **Skip blank pages** |
| No separate questions were written | That paper doesn't number questions in a left-hand column. The cleaned PDF is still fine — crop from it by hand |
| A question PNG holds two questions | One number wasn't detected. Crop that one by hand in Photo Fuse |
