# Photo Fuse + PDF Cleaner

Two small Windows tools for building **Easify topical questions** out of past papers.

| Tool | What it does |
|---|---|
| **PDF Cleaner** | Takes a whole past paper and strips it down: erases the dotted answer lines, squashes the blank writing space, removes barcodes / page numbers / footers / the "DO NOT WRITE IN THIS MARGIN" bar, then **reflows** what is left so a question no longer breaks across pages. Can also spit out **one PNG per question**. |
| **Photo Fuse** | Takes one or more crops of a single question, cleans and joins them, saves the PNG **already named correctly**, and **adds the row to your spreadsheet**. |

Typical result on a real paper (Cambridge Physics 9702/21 M/J 2025): 13 question pages
in, **8 pages out, ~48% of the vertical space removed**, all 7 questions exported
individually, every diagram and graph intact.

---

## 1. Setup — just run one file

Download the project, then double-click:

```
setup.bat
```

That is the whole thing. It:

1. finds Python, wherever it lives on the machine;
2. **if Python is missing, downloads it from python.org and installs it** — for
   your account only, so no administrator password is needed;
3. installs Pillow, numpy, openpyxl and PyMuPDF into that exact Python;
4. checks it all worked and tells you if anything is still wrong.

Leave it running; the first time takes a few minutes. When it finishes, start the
tools with `2 - START Photo Fuse.bat`.

> It downloads the official signed installer straight from `python.org` — nothing
> else, and nothing from anywhere else.

`1 - INSTALL (run me first).bat` still works too; it just runs `setup.bat`.

### Prefer to install Python yourself?

1. Download it from <https://www.python.org/downloads/>
2. Run the installer.
3. **On the very first screen, tick "Add python.exe to PATH".**
4. Click *Install Now*, then run `setup.bat`.

Check it worked — open Command Prompt and run:

```bat
py --version
```

If that does not work, try:

```bat
python --version
```

**Either one is enough.** `py` is the Windows Python launcher; it installs into
`C:\Windows` and works even when *Add python.exe to PATH* was never ticked. The `.bat`
files try `py -3`, `python`, `py` and `python3` in turn, so a Python that only answers
to one of them is still found.

---

## 2. Installing the libraries by hand

Only needed if `setup.bat` could not finish — it does all of this for you.

### By hand

Open Command Prompt **in the project folder** (type `cmd` in the Explorer address bar
and press Enter), then run:

```bat
pip install -r requirements.txt
```

**If `pip` is not recognised**, use the launcher instead — this works on essentially
any Windows PC:

```bat
py -m pip install -r requirements.txt
```

**If `py` is not recognised either**, use:

```bat
python -m pip install -r requirements.txt
```

Then do the same for the PDF Cleaner:

```bat
cd "PDF CLeaner"
py -m pip install -r requirements.txt
cd ..
```

### Installing the packages one by one

If a requirements file gives you trouble, install them directly:

```bat
py -m pip install Pillow numpy openpyxl pymupdf
```

| Package | Used for |
|---|---|
| `Pillow` | reading and writing images |
| `numpy` | the fast pixel maths behind line removal |
| `openpyxl` | writing rows into the `.xlsx` |
| `pymupdf` | reading PDFs (PDF Cleaner only) |

### If pip itself is broken or out of date

```bat
py -m pip install --upgrade pip
py -m ensurepip --upgrade
```

### Behind a school / office firewall

```bat
py -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
```

### Mac / Linux

```bash
python3 -m pip install -r requirements.txt
python3 photofuse_gui.py
```

On Linux you may also need tkinter: `sudo apt install python3-tk`

---

## 3. Run it

| Tool | Double-click | Or from the command line |
|---|---|---|
| Setup (once) | `setup.bat` | `py -m pip install -r requirements.txt` |
| Photo Fuse | `2 - START Photo Fuse.bat` | `py photofuse_gui.py` |
| Photo Fuse (with files) | drag images onto `Drag images here.bat` | `py photofuse_gui.py a.png b.png` |
| PDF Cleaner | `PDF CLeaner\2 - START PDF Cleaner.bat` | `py "PDF CLeaner\pdfcleaner_gui.py"` |
| PDF Cleaner (with a paper) | drag a PDF onto `Drop PDF here.bat` | `py "PDF CLeaner\pdfcleaner.py" paper.pdf --questions` |

> **"Windows protected your PC"** when opening a `.bat`? That appears for files that
> came from the internet. Click **More info → Run anyway**.

---

## 4. The workflow

```
past paper PDF
      │
      ▼  PDF Cleaner  (tick "Output separate questions", set Quality to 150 dpi)
one PNG per question, ~1066 px wide
      │
      ▼  Photo Fuse   (tick "Rename only", fill the boxes)
correctly named PNG in output/  +  a row in your spreadsheet
```

**Use 150 dpi in PDF Cleaner** for this route — it produces images about **1066 px**
wide, right inside the brief's 1000–1200 px range. (200 dpi gives 1424 px, which is
over, and "Rename only" never resizes.)

If a question still needs two crops, add both to Photo Fuse and it fuses them.

### File names

```
subject_pPV_chapter_YEARseason_qNUM_Q.png
physics_p11_dynamics_2025mj_q19_Q.png
```

`PV` is **paper + variant** together: `p11` = paper 1 variant 1, `p23` = paper 2
variant 3. Names are always lowercase with a lowercase `.png` — the tool guarantees
this, and it is the thing that most often goes wrong by hand.

### The spreadsheet

Pick your `easify-topical-template.xlsx` in Photo Fuse and press **Add to Excel
sheet**. It:

- **never writes to your original** — it copies the file into `output/` the first time
  and adds rows to that copy, which is the one you work from;
- finds columns **by their heading**, so it still works if the layout shifts;
- fills **both** `q_filename` and `ms_filename` from the one entry (they differ only by
  `_Q` / `_MS`, so there is nothing to type twice and nothing to typo);
- never touches columns **J and K** — those fill themselves — and copies their formulas
  down for new rows;
- puts the same question on the same row if you add it again.

When everything is in, open that copy in Excel and **Save As → CSV**. The CSV plus the
PNG folder is what gets handed over. (That step needs Excel: J and K are formulas, and
only Excel can work out what they come to.)

> **On the brief's "don't use AI to fuse images":** that is about generative tools,
> which redraw the image and can silently change a number. Photo Fuse crops, pads and
> stacks the real pixels — like stitching in Paint, but without the slips. Nothing is
> ever redrawn.

Full details for contributors: **[INSTRUCTIONS.md](INSTRUCTIONS.md)** and
**[PDF CLeaner/INSTRUCTIONS.md](PDF%20CLeaner/INSTRUCTIONS.md)**.

---

## 5. Project layout

```
Photo Fuse tool/
├── photofuse.py              image cleaning + fusing + naming
├── photofuse_gui.py          the Photo Fuse window
├── topical_sheet.py          appends rows to the .xlsx
├── requirements.txt
├── INSTRUCTIONS.md           full contributor guide
├── input/                    drop raw crops here (optional)
├── output/                   finished PNGs + the filled spreadsheet copy
└── PDF CLeaner/
    ├── pdfcleaner.py         render, clean, reflow, re-paginate, split questions
    ├── pdfcleaner_gui.py     the PDF Cleaner window
    ├── requirements.txt
    ├── INSTRUCTIONS.md
    └── output/               cleaned PDFs + per-question PNGs
```

> **`PDF CLeaner` must stay inside the `Photo Fuse tool` folder.** It shares the
> line-erasing code in `photofuse.py`, and says so clearly if it is moved out.

Both tools also run headless from the command line — `py photofuse.py --help` and
`py "PDF CLeaner\pdfcleaner.py" --help`.

---

## 6. When something is missing: `Check setup.bat`

Double-click **`Check setup.bat`**. It prints which Python is actually being used,
where it lives, and which libraries it can see:

```
The Python being used:
   C:\Users\me\AppData\Local\Programs\Python\Python312\python.exe
   version 3.12.4

Libraries:
   [ok]      Pillow     11.0.0     - images
   [MISSING] pymupdf               - reading PDFs (PDF Cleaner only)
```

If something says `[MISSING]` it also prints the exact command to fix it, with the
full path filled in. Screenshot that page when asking for help — it answers almost
every setup question in one go.

### "But I already installed it!"

Almost always this: **the computer has more than one Python**, and the package went
into a different one from the one the tools run. `Check setup.bat` shows you which
Python is being used, so you can install into *that* one.

Two ways to sort it out:

**A — install into the Python the tools use** (simplest): double-click
`1 - INSTALL (run me first).bat`. It installs into exactly the Python the launchers
will use, so they cannot disagree.

**B — point the tools at the Python you already set up.** Make a file called
**`python-path.txt`** in this folder, with the full path to that `python.exe` on one
line:

```
D:\Programs\Python311\python.exe
```

Every `.bat` file will then use precisely that Python — no PATH changes, nothing
reinstalled. Lines starting with `#` are ignored, and if the path does not exist the
launchers quietly fall back to finding Python themselves.

---

## 7. Something went wrong?

| Problem | Fix |
|---|---|
| **"Python is NOT installed" but it definitely is** | Python was installed without *Add python.exe to PATH*. The `.bat` files also try the `py` launcher, so update to the current version of them. To fix PATH itself: Settings → Apps → Installed apps → Python → **Modify** → tick *Add Python to environment variables* |
| `'python' is not recognized` | Same cause — use `py` instead of `python` everywhere |
| `'pip' is not recognized` | Use `py -m pip ...` instead of `pip ...` |
| `python` opens the Microsoft Store | That is a Windows placeholder, not Python. Use `py`, or install from python.org |
| `ModuleNotFoundError` for anything | Run **`Check setup.bat`** — it names the Python in use and prints the exact install command |
| "I already installed that package!" | You have two Pythons. See section 6 — use `python-path.txt` or re-run the INSTALL file |
| Python is on D: / a USB / Anaconda | Put its `python.exe` path in `python-path.txt` (section 6) |
| `No module named 'tkinter'` (Mac/Linux) | Install your system's tkinter package |
| A `.bat` flashes and closes | Run the INSTALL `.bat` first; the others pause on error |
| "…is open in Excel" | Close the spreadsheet and press the button again |
| "Could not find the column headings" | Wrong file — it needs the template with a **Questions** tab |
| `Could not find photofuse.py` | `PDF CLeaner` was moved out of the project folder. Put it back |
| A graph lost its lines | Untick **Also erase solid rules** (off by default) |
| Text looks soft | Raise **Quality** to 300 dpi in PDF Cleaner |

---

## Note on committing

`.gitignore` deliberately excludes `*.xlsx`, `output/` and `photofuse-settings.json`.
Keep the spreadsheet out of the repo — its auto-fill columns contain your image-hosting
URL, which you probably do not want in a public repository.
