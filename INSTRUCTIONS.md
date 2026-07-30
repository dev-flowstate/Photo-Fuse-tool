# Photo Fuse — how to use it

Takes the **pieces of one past-paper question** (or a single picture) and turns them
into **one clean PNG, already named the way the Aidify brief wants** — then adds the
row to your spreadsheet for you.

It also:

- trims the white margins so the crop is tight,
- removes page rules / scan edges stuck to the top or bottom of a crop,
- squashes huge blank answer spaces inside a question,
- turns grey scan paper into pure white,
- pads narrower pieces with white so everything lines up (nothing is ever stretched),
- resizes to 1100 px wide (the brief asks for 1000–1200 px).

**One picture is fine.** You do not need two. Drop in a single image and use it purely
as a renamer — see *Rename only* in Part 4.

**Two buttons, two jobs:**

| Button | What it does |
|---|---|
| **Fuse & Save Photo** (`Ctrl+S`) | builds the PNG and saves it under the correct name |
| **Add to Excel sheet** (`Ctrl+E`) | writes one row into your `aidify-topical-template.xlsx` |

Use either on its own, or both — they read the same boxes.

---

## Part 1 — Setup (do this once)

### Step 1: Install Python

If you already have Python 3.10 or newer, skip to Step 2.

1. Go to <https://www.python.org/downloads/>
2. Download the latest Python for Windows.
3. Run the installer. **On the very first screen, tick "Add python.exe to PATH".**
   This is the step everybody misses — if you skip it nothing else will work.
4. Click *Install Now* and let it finish.

### Step 2: Install the libraries

Double-click:

```
1 - INSTALL (run me first).bat
```

A black window opens and installs **Pillow** (image handling), **numpy** (fast maths)
and **openpyxl** (writes the spreadsheet).
It takes about 30 seconds. When it says *Done*, close it.

<details>
<summary>Prefer to do it by hand, or on Mac/Linux?</summary>

Open a terminal in this folder and run:

```bash
python -m pip install -r requirements.txt
```

Then start the tool with `python photofuse_gui.py`.
On Linux you may also need tkinter: `sudo apt install python3-tk`.
</details>

### If the install fails

| What you see | What to do |
|---|---|
| `Python is NOT installed` | You missed the "Add python.exe to PATH" tick. Reinstall Python and tick it. |
| `'python' is not recognized` | Same as above. |
| `pip` errors / timeouts | Check your internet, then run the INSTALL file again. |
| `No module named tkinter` (Mac/Linux) | Install the tkinter package for your system. |

---

## Part 2 — Where the pictures go

```
Photo Fuse tool/
├── input/     ← put your raw crops / screenshots here (optional, just for tidiness)
├── output/    ← FINISHED, CORRECTLY-NAMED PNGs LAND HERE  ← this is what goes on the USB
├── photofuse_gui.py
├── photofuse.py
└── the .bat files
```

- **`input/`** is only a convenient place to keep your raw pieces. The tool can read
  images from anywhere on your computer — Desktop, Downloads, a USB stick, wherever.
- **`output/`** is what matters. Every finished image is written there with its final
  name. **You never rename anything.** Copy the whole `output` folder onto the USB.

You can change the output folder in the app (the *Save to* box) if you want, for
example straight onto the USB drive.

---

## Part 3 — Making one question

Start the tool by double-clicking:

```
2 - START Photo Fuse.bat
```

### Step 1 — Add the pieces

Three ways to get pictures in:

1. **Add images… button** — pick one or more files. Hold `Ctrl` to select several.
2. **Drag and drop** — select the crops in File Explorer and drag them onto
   `Drag images here.bat`. The app opens with them already loaded.
3. **Command line** — see Part 6.

The list shows them numbered **1, 2, 3…** — that is the order they will be stacked,
**top to bottom**. Wrong order? Select one and use **Move up / Move down**.

> **A single picture is completely fine** — add just the one image. If it is already a
> clean crop (say a question PNG from PDF Cleaner), tick **Rename only** and the tool
> becomes a pure renamer: not one pixel is altered.

### Step 2 — Fill in the boxes

| Box | What to put | Example |
|---|---|---|
| Subject | math / physics / cs / chem / bio | `physics` |
| Type | `Q` for the question, `MS` for the mark scheme | `Q` |
| Paper | paper number, 1–6 | `1` |
| Variant | variant number — **required** | `1` |
| Chapter | topic name — spell it the same way every time | `dynamics` |
| Question no. | question number (`19`, or `19a` if you split parts) | `19` |
| Year | 4-digit exam year | `2025` |
| Season | `on` = Oct/Nov, `mj` = May/June, `fm` = Feb/March | `mj` |

Under **Will be saved as:** you see the exact file name, live. Green means good to go;
orange tells you what is still missing.

**Paper and variant go together.** The brief's `PV` is the two of them side by side:

| Paper | Variant | You get |
|---|---|---|
| 1 | 1 | `p11` |
| 1 | 2 | `p12` |
| 2 | 3 | `p23` |

So the example above saves as `physics_p11_dynamics_2025mj_q19_Q.png`. Names are
always **lowercase** with a lowercase `.png`, and no spaces, commas or `/` — the tool
guarantees that, which is the thing the brief says goes wrong most often.

The boxes under *For the spreadsheet* (Difficulty, Marks, YouTube URL) never appear in
the file name — they only fill columns E, F and I. **Marks:** Paper 1 MCQs are `1`;
structured papers take the real mark total.

### Step 3 — Preview, Save, then add the row

1. **Preview** (`Ctrl+P`) — see the result without saving.
2. **Fuse & Save Photo** (`Ctrl+S`) — writes the PNG to the output folder.
3. **Add to Excel sheet** (`Ctrl+E`) — writes the row (Part 5).

Then switch **Type** to `MS`, add the mark-scheme picture, and repeat. Adding the MS
fills the *same row* — one question is always one row.

The boxes are left exactly as you set them after saving, because both buttons read
them. Change only what differs for the next question.

---

## Part 4 — The options row (you can usually ignore this)

The defaults are tuned for typical past-paper scans. Change them only if something
looks wrong.

| Option | What it does | When to change it |
|---|---|---|
| **Join** | `vertical` stacks pieces; `horizontal` puts them side by side | Two-column layouts |
| **Align** | which edge the pieces line up on | Use `center` for diagrams/graphs |
| **Gap px** | white space between pieces | Bigger if parts feel cramped |
| **Max blank gap px** | blank bands taller than this get squashed down to it | Raise it to keep answer space, e.g. `200` |
| **Output width px** | final width | Brief wants 1000–1200. Set `0` to keep original size |
| **Ink threshold** | how dark a pixel must be to count as content (1–254) | **Raise** to ~230 if faint/grey text is being trimmed off. **Lower** to ~150 if speckly scans confuse it |
| **Trim white margins** | crops tightly around the content | Untick to keep the original indentation of each piece |
| **Remove edge lines** | deletes page rules touching the crop edge | Untick if a table border is being eaten |
| **Squash blank gaps** | removes dead vertical space | Untick to keep the layout exactly as printed |
| **Whiten background** | grey paper → pure white | Untick for colour diagrams that look washed out |
| **Scale parts to same width** | resizes pieces to match instead of padding | Only if pieces were cropped at different zoom levels |
| **Rename only** | saves the picture completely untouched — no trimming, no cleaning, no resizing | For crops that are already perfect, e.g. question PNGs from PDF Cleaner |

**Note on width:** the tool never enlarges a small image, because blowing up a small
crop makes it blurry and the brief rejects blurry crops. If the status bar says the
width is under 1000 px, your original crop was too small — **re-crop it from the PDF at
a higher zoom** rather than forcing it bigger here.

**Rename only and width:** nothing is resized in this mode, so the picture keeps
whatever width it came in at. If you are renaming PDF Cleaner questions, run PDF
Cleaner at **150 dpi** — that produces images about **1066 px** wide, right inside the
brief's 1000–1200 px range. (200 dpi gives 1424 px, which is over.)

---

## Part 5 — Filling the spreadsheet

Press **Choose…** next to *Excel sheet* and pick your `aidify-topical-template.xlsx`.
Then **Add to Excel sheet** (`Ctrl+E`) writes one row per question.

### Your original is never touched

The first time you add a row, the file is **copied into the output folder**, and every
row after that goes into the copy:

```
output/
├── aidify-topical-template.xlsx   ← the filled copy - this goes on the USB
└── physics_p11_dynamics_2025mj_q19_Q.png ...
```

Your master template stays exactly as it was. So if anything ever looks wrong, you
still have a clean copy to start again from. Next session, either pick the master
again (rows keep going into the same output copy) or pick the copy directly.

### What it writes

Only columns **A–I**: subject, paper, chapter, year, difficulty, marks, q_filename,
ms_filename, youtube_url.

- **Columns J and K are never written.** The brief says they fill themselves, so
  instead the tool copies their formulas down from the row above — exactly what Excel
  does when you drag a row down. They keep working on every new row.
- **`paper` holds the number only** (1–6). The variant lives in the file name, never
  in this column.
- **`chapter` is written in its short form** (`coord-geom`, `dynamics`) so it is
  spelled identically on every row — the brief asks for the same spelling every time.
- Saving the **Q** fills `q_filename`; saving the **MS** fills `ms_filename` **on the
  same row**. One question = one row, always.

Your dropdowns, colours, column widths, frozen headings and other tabs all survive
untouched.

### Two things it will tell you

- If the PNG for that row is not in the output folder yet, the status bar warns you —
  the sheet and the images must match.
- If the file is open in Excel, it says so. **Close it and press the button again**;
  nothing is lost.

The old `_spreadsheet_rows.csv` checkbox still works if you would rather paste rows in
by hand, but with the Excel button you no longer need it.

---

## Part 6 — Command line (optional, for bulk work)

```bash
python photofuse.py part1.png part2.png ^
    --subject physics --paper 1 --variant 1 --chapter "dynamics" ^
    --year 2025 --season mj --q 19 --type Q ^
    --difficulty Medium --marks 6
```

Useful extras: `--out FOLDER`, `--width 1200`, `--direction horizontal`,
`--align center`, `--max-gap 200`, `--no-trim`, `--no-clean`, `--no-collapse`,
`--keep-edge-lines`, `--match-widths`, `--no-csv`.

The Excel button is window-only — the command line still writes the CSV.

Full list: `python photofuse.py --help`

---

## Checklist before handing over the USB

- [ ] Every image is in `output/` with its automatic name — **nothing renamed by hand**
- [ ] Each question has both a `_Q.png` and a `_MS.png`
- [ ] All names lowercase, ending in a lowercase `.png`, no spaces / commas / `/`
- [ ] Crops are tight and readable, roughly 1000–1200 px wide
- [ ] The **filled copy** of `aidify-topical-template.xlsx` from `output/` goes on the
      USB — not your blank master
- [ ] Columns A–I filled, J and K left alone
- [ ] File names in the sheet match the images **exactly**, capitals included

---

## Something went wrong?

| Problem | Fix |
|---|---|
| Window won't open, black box flashes | Run `1 - INSTALL (run me first).bat` |
| `ModuleNotFoundError: PIL` / `numpy` / `openpyxl` | Same — run the INSTALL file |
| **Add to Excel sheet** is greyed out | openpyxl is missing — run the INSTALL file |
| "…is open in Excel" | Close the file in Excel, then press the button again |
| "Could not find the column headings" | Wrong file picked. It needs the template with a **Questions** tab whose headings include `subject` and `q_filename` |
| Rows going into the wrong file | Rows go into the **copy in `output/`**, not your master. That copy is the deliverable |
| Part of the question got cut off | Untick **Remove edge lines**, or raise **Ink threshold** |
| Faint text disappeared | Raise **Ink threshold** to about 230 |
| Grey smudges / speckles all over | Lower **Ink threshold** to about 150 |
| Pieces don't line up | Try **Align: center**, or tick **Scale parts to same width** |
| Final image is too small (< 1000 px) | Re-crop from the PDF at a higher zoom — don't upscale |
| Saved the wrong thing | Just fix the boxes and save again; the same name overwrites |
