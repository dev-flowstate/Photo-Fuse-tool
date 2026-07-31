# Photo Fuse + PDF Cleaner

Two small Windows tools for building **Aidify topical questions** out of past papers.

| Tool | What it does |
|---|---|
| **PDF Cleaner** | Takes a whole past paper and strips it down: erases the dotted answer lines, squashes the blank writing space, removes barcodes / page numbers / footers / the "DO NOT WRITE IN THIS MARGIN" bar, then **reflows** what is left so a question no longer breaks across pages. Can also spit out **one PNG per question**. |
| **Photo Fuse** | Takes one or more crops of a single question, cleans and joins them, saves the PNG **already named correctly**, and **adds the row to your spreadsheet**. |

Typical result on a real paper (Cambridge Physics 9702/21 M/J 2025): 13 question pages
in, **8 pages out, ~48% of the vertical space removed**, all 7 questions exported
individually, every diagram and graph intact.

---

## 1. Install Python

You need **Python 3.10 or newer**.

1. Download it from <https://www.python.org/downloads/>
2. Run the installer.
3. **On the very first screen, tick "Add python.exe to PATH".**
   This is the step people miss, and nothing works without it.
4. Click *Install Now*.

Check it worked — open Command Prompt and run:

```bat
python --version
```

If that says *'python' is not recognized*, try:

```bat
py --version
```

If `py` works but `python` does not, just use `py` everywhere below.

---

## 2. Install the libraries

### The easy way (Windows)

Double-click **`1 - INSTALL (run me first).bat`**, then the one inside the
**`PDF CLeaner`** folder. Done.

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

Pick your `aidify-topical-template.xlsx` in Photo Fuse and press **Add to Excel
sheet**. It:

- **never writes to your original** — it copies the file into `output/` the first time
  and adds rows to that copy, which is the one you hand over;
- finds columns **by their heading**, so it still works if the layout shifts;
- fills **both** `q_filename` and `ms_filename` from the one entry (they differ only by
  `_Q` / `_MS`, so there is nothing to type twice and nothing to typo);
- never touches the self-filling image-URL columns, and copies their formulas down for
  new rows;
- puts the same question on the same row if you add it again.

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

## 6. Something went wrong?

| Problem | Fix |
|---|---|
| `'python' is not recognized` | You missed *Add python.exe to PATH*. Reinstall Python and tick it, or use `py` instead |
| `'pip' is not recognized` | Use `py -m pip ...` instead of `pip ...` |
| `ModuleNotFoundError: No module named 'PIL'` | `py -m pip install Pillow` |
| `ModuleNotFoundError: No module named 'fitz'` | `py -m pip install pymupdf` |
| `ModuleNotFoundError: No module named 'openpyxl'` | `py -m pip install openpyxl` |
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
