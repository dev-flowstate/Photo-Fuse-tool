"""
Photo Fuse - window version
===========================

Point-and-click front end for photofuse.py. Nothing to configure: add the
crops of one question, fill in the boxes, press Save. The file lands in the
output folder already named correctly.

    python photofuse_gui.py
    python photofuse_gui.py part1.png part2.png      (pre-loads those files)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from dataclasses import replace
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import ImageTk
except ImportError:
    sys.exit(
        "Missing dependencies.\n"
        "Run this once, then try again:\n\n"
        "    python -m pip install -r requirements.txt\n"
    )

import photofuse as pf

try:
    import topical_sheet as ts
    SHEET_ERROR = ""
except ImportError as exc:          # openpyxl missing - images still work fine
    ts = None
    SHEET_ERROR = str(exc)

IMAGE_TYPES = [
    ("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp"),
    ("All files", "*.*"),
]
EXCEL_TYPES = [("Excel workbook", "*.xlsx *.xlsm"), ("All files", "*.*")]

#: Remembers the output folder and spreadsheet between sessions, so they only
#: have to be picked once.
SETTINGS_FILE = Path(__file__).resolve().parent / "photofuse-settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(values: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(values, indent=2), encoding="utf-8")
    except OSError:
        pass                    # remembering is a convenience, never a failure


class App(ttk.Frame):
    def __init__(self, master: tk.Tk, preload: list[str] | None = None):
        super().__init__(master, padding=12)
        self.grid(row=0, column=0, sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        remembered = load_settings()
        self.paths: list[str] = []
        self.out_dir = tk.StringVar(value=remembered.get("out_dir")
                                    or str(pf.DEFAULT_OUTPUT_DIR))
        self.xlsx_path = tk.StringVar(value=remembered.get("xlsx_path", ""))
        self.last_saved: Path | None = None
        self._preview_ref = None  # keeps the PhotoImage alive

        self._build_header()
        self._build_parts_panel()
        self._build_details_panel()
        self._build_options_panel()
        self._build_footer()

        if preload:
            self.add_paths(preload)
        self.refresh_filename()

    # -- layout ------------------------------------------------------------

    def _build_header(self):
        head = ttk.Frame(self)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(head, text="Photo Fuse", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            head,
            text="Add the pieces of ONE question (top to bottom), fill in the boxes, "
                 "then Save. The name is built for you.",
            foreground="#555",
        ).pack(anchor="w")

    def _build_parts_panel(self):
        box = ttk.LabelFrame(self, text="1. Parts of this question", padding=8)
        box.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        box.rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(box, width=38, height=9, activestyle="dotbox",
                                  selectmode=tk.EXTENDED)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scroll.set)

        buttons = ttk.Frame(box)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        for text, cmd in (
            ("Add images...", self.choose_files),
            ("Move up", lambda: self.move(-1)),
            ("Move down", lambda: self.move(1)),
            ("Remove", self.remove_selected),
            ("Clear", self.clear_parts),
        ):
            ttk.Button(buttons, text=text, command=cmd).pack(side="left", padx=(0, 4))

        ttk.Label(
            box,
            text="Order matters - part 1 goes on top.\n"
                 "Tip: you can also drag files onto \"Drag images here.bat\".",
            foreground="#666", font=("Segoe UI", 8),
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_details_panel(self):
        box = ttk.LabelFrame(self, text="2. Question details", padding=8)
        box.grid(row=1, column=1, sticky="nsew")
        box.columnconfigure(1, weight=1)
        box.columnconfigure(3, weight=1)

        self.v = {
            "subject": tk.StringVar(value="math"),
            "paper": tk.StringVar(value="1"),
            "variant": tk.StringVar(value=""),
            "chapter": tk.StringVar(value=""),
            "year": tk.StringVar(value=""),
            "season": tk.StringVar(value="on"),
            "question": tk.StringVar(value=""),
            "kind": tk.StringVar(value="Q"),
            "difficulty": tk.StringVar(value=""),
            "marks": tk.StringVar(value=""),
            "youtube_url": tk.StringVar(value=""),
        }
        for var in self.v.values():
            var.trace_add("write", lambda *_: self.refresh_filename())

        def row(r, label, widget, col=0):
            ttk.Label(box, text=label).grid(row=r, column=col, sticky="w", pady=3, padx=(0, 6))
            widget.grid(row=r, column=col + 1, sticky="ew", pady=3, padx=(0, 12))

        row(0, "Subject", ttk.Combobox(box, textvariable=self.v["subject"],
                                       values=list(pf.SUBJECTS), state="readonly", width=12))
        row(0, "Type", ttk.Combobox(box, textvariable=self.v["kind"],
                                    values=list(pf.KINDS), state="readonly", width=12), col=2)
        row(1, "Paper", ttk.Entry(box, textvariable=self.v["paper"], width=12))
        row(1, "Variant", ttk.Entry(box, textvariable=self.v["variant"], width=12), col=2)
        row(2, "Chapter", ttk.Entry(box, textvariable=self.v["chapter"]))
        row(2, "Question no.", ttk.Entry(box, textvariable=self.v["question"], width=12), col=2)
        row(3, "Year", ttk.Entry(box, textvariable=self.v["year"], width=12))
        row(3, "Season", ttk.Combobox(box, textvariable=self.v["season"],
                                      values=list(pf.SEASONS), state="readonly", width=12), col=2)

        ttk.Label(box, text="Paper and variant go together: paper 1 variant 1 = p11, "
                            "paper 2 variant 3 = p23.",
                  foreground="#666", font=("Segoe UI", 8)
                  ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(0, 6))

        ttk.Separator(box, orient="horizontal").grid(
            row=5, column=0, columnspan=4, sticky="ew", pady=6)
        ttk.Label(box, text="For the spreadsheet (not in the file name)",
                  foreground="#666").grid(row=6, column=0, columnspan=4, sticky="w")

        row(7, "Difficulty", ttk.Combobox(box, textvariable=self.v["difficulty"],
                                          values=["", "Easy", "Medium", "Hard"],
                                          state="readonly", width=12))
        row(7, "Marks", ttk.Entry(box, textvariable=self.v["marks"], width=12), col=2)
        row(8, "YouTube URL", ttk.Entry(box, textvariable=self.v["youtube_url"]))

        ttk.Separator(box, orient="horizontal").grid(
            row=9, column=0, columnspan=4, sticky="ew", pady=8)
        ttk.Label(box, text="Will be saved as:").grid(row=10, column=0, columnspan=4, sticky="w")
        self.name_label = ttk.Label(box, text="", font=("Consolas", 10, "bold"),
                                    foreground="#1a7f37", wraplength=640, justify="left")
        self.name_label.grid(row=11, column=0, columnspan=4, sticky="w", pady=(2, 0))

    def _build_options_panel(self):
        box = ttk.LabelFrame(self, text="3. Fusing options (defaults are fine)", padding=8)
        box.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        s = pf.Settings()
        self.o = {
            "direction": tk.StringVar(value=s.direction),
            "align": tk.StringVar(value=s.align),
            "gap": tk.IntVar(value=s.gap),
            "output_width": tk.IntVar(value=s.output_width),
            "max_gap": tk.IntVar(value=s.max_gap),
            "ink_threshold": tk.IntVar(value=s.ink_threshold),
            "trim": tk.BooleanVar(value=s.trim),
            "strip_edge_lines": tk.BooleanVar(value=s.strip_edge_lines),
            "collapse_gaps": tk.BooleanVar(value=s.collapse_gaps),
            "clean_background": tk.BooleanVar(value=s.clean_background),
            "match_part_widths": tk.BooleanVar(value=s.match_part_widths),
            "passthrough": tk.BooleanVar(value=s.passthrough),
        }

        line1 = ttk.Frame(box)
        line1.pack(fill="x")
        ttk.Label(line1, text="Join").pack(side="left")
        ttk.Combobox(line1, textvariable=self.o["direction"], width=11, state="readonly",
                     values=["vertical", "horizontal"]).pack(side="left", padx=(4, 14))
        ttk.Label(line1, text="Align").pack(side="left")
        ttk.Combobox(line1, textvariable=self.o["align"], width=9, state="readonly",
                     values=["left", "center", "right"]).pack(side="left", padx=(4, 14))
        for label, key, width in (("Gap px", "gap", 5),
                                  ("Max blank gap px", "max_gap", 5),
                                  ("Output width px", "output_width", 6),
                                  ("Ink threshold", "ink_threshold", 5)):
            ttk.Label(line1, text=label).pack(side="left")
            ttk.Spinbox(line1, from_=0, to=4000, textvariable=self.o[key],
                        width=width).pack(side="left", padx=(4, 14))

        line2 = ttk.Frame(box)
        line2.pack(fill="x", pady=(6, 0))
        for label, key in (
            ("Trim white margins", "trim"),
            ("Remove edge lines", "strip_edge_lines"),
            ("Squash blank gaps", "collapse_gaps"),
            ("Whiten background", "clean_background"),
            ("Scale parts to same width", "match_part_widths"),
        ):
            ttk.Checkbutton(line2, text=label, variable=self.o[key]).pack(side="left", padx=(0, 14))

        line3 = ttk.Frame(box)
        line3.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(line3, text="Rename only - save the picture exactly as it is",
                        variable=self.o["passthrough"],
                        command=self.refresh_filename).pack(side="left")
        ttk.Label(line3, text="(for crops that are already clean, e.g. from PDF Cleaner)",
                  foreground="#666").pack(side="left", padx=(6, 0))

    def _build_footer(self):
        box = ttk.Frame(self)
        box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Save to").grid(row=0, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.out_dir).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(box, text="Change...", command=self.choose_out_dir).grid(row=0, column=2)
        ttk.Button(box, text="Open folder", command=self.open_out_dir).grid(row=0, column=3, padx=(6, 0))

        ttk.Label(box, text="Excel sheet").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(box, textvariable=self.xlsx_path).grid(row=1, column=1, sticky="ew",
                                                         padx=6, pady=(6, 0))
        ttk.Button(box, text="Choose...", command=self.choose_xlsx).grid(row=1, column=2, pady=(6, 0))
        ttk.Button(box, text="Open sheet", command=self.open_sheet).grid(row=1, column=3,
                                                                        padx=(6, 0), pady=(6, 0))

        ttk.Label(box,
                  text="Pick your easify-topical-template.xlsx. A copy is made in the output "
                       "folder and rows are added to that - your original is never changed.",
                  foreground="#666", font=("Segoe UI", 8)
                  ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(3, 0))

        actions = ttk.Frame(box)
        actions.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Preview  (Ctrl+P)", command=self.preview).pack(side="left")
        ttk.Button(actions, text="Fuse & Save Photo  (Ctrl+S)",
                   command=self.save).pack(side="left", padx=6)
        self.sheet_button = ttk.Button(actions, text="Add to Excel sheet  (Ctrl+E)",
                                       command=self.add_to_sheet)
        self.sheet_button.pack(side="left")
        if ts is None:
            self.sheet_button.state(["disabled"])

        self.csv_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="also log a CSV row",
                        variable=self.csv_var).pack(side="left", padx=(12, 0))

        self.status = ttk.Label(box, text="Ready.", foreground="#555", wraplength=880,
                                justify="left")
        self.status.grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))

    # -- parts list --------------------------------------------------------

    def add_paths(self, paths):
        added = 0
        for p in paths:
            p = str(Path(p).resolve())
            if os.path.isfile(p) and p not in self.paths:
                self.paths.append(p)
                added += 1
        self.redraw_list()
        if added:
            self.set_status(f"Added {added} image(s). {len(self.paths)} part(s) queued.")

    def choose_files(self):
        chosen = filedialog.askopenfilenames(title="Choose the parts of this question",
                                             filetypes=IMAGE_TYPES)
        if chosen:
            self.add_paths(chosen)

    def redraw_list(self):
        self.listbox.delete(0, tk.END)
        for i, p in enumerate(self.paths, 1):
            self.listbox.insert(tk.END, f"{i}. {Path(p).name}")

    def selected_indices(self) -> list[int]:
        return list(self.listbox.curselection())

    def move(self, step: int):
        idx = self.selected_indices()
        if not idx:
            self.set_status("Select a part in the list first.")
            return
        order = sorted(idx, reverse=step > 0)
        for i in order:
            j = i + step
            if 0 <= j < len(self.paths):
                self.paths[i], self.paths[j] = self.paths[j], self.paths[i]
        self.redraw_list()
        for i in idx:
            j = i + step
            if 0 <= j < len(self.paths):
                self.listbox.selection_set(j)

    def remove_selected(self):
        for i in sorted(self.selected_indices(), reverse=True):
            del self.paths[i]
        self.redraw_list()
        self.set_status(f"{len(self.paths)} part(s) queued.")

    def clear_parts(self):
        self.paths.clear()
        self.redraw_list()
        self.set_status("Parts cleared.")

    # -- state -------------------------------------------------------------

    def meta(self) -> pf.Meta:
        return pf.Meta(**{k: var.get() for k, var in self.v.items()})

    def settings(self) -> pf.Settings:
        o = self.o
        return replace(
            pf.Settings(),
            direction=o["direction"].get(), align=o["align"].get(),
            gap=max(0, o["gap"].get()), max_gap=max(1, o["max_gap"].get()),
            output_width=max(0, o["output_width"].get()),
            ink_threshold=min(254, max(1, o["ink_threshold"].get())),
            trim=o["trim"].get(), strip_edge_lines=o["strip_edge_lines"].get(),
            collapse_gaps=o["collapse_gaps"].get(),
            clean_background=o["clean_background"].get(),
            match_part_widths=o["match_part_widths"].get(),
            passthrough=o["passthrough"].get(),
        )

    def refresh_filename(self, *_):
        meta = self.meta()
        issues = meta.problems()
        if issues:
            self.name_label.configure(text=meta.filename() + "     (still needs: "
                                      + "; ".join(issues) + ")", foreground="#b34700")
        else:
            self.name_label.configure(text=meta.filename(), foreground="#1a7f37")

    def set_status(self, text: str, error: bool = False):
        self.status.configure(text=text, foreground="#b00020" if error else "#555")

    # -- actions -----------------------------------------------------------

    def build_image(self):
        if not self.paths:
            messagebox.showwarning("Nothing to fuse", "Add at least one image first.")
            return None
        return pf.build(self.paths, self.settings())

    def preview(self):
        try:
            img = self.build_image()
        except Exception as exc:                       # noqa: BLE001 - shown to user
            traceback.print_exc()
            messagebox.showerror("Could not build the image", str(exc))
            return
        if img is None:
            return

        win = tk.Toplevel(self)
        win.title(f"Preview - {img.width} x {img.height} px")
        screen_h = max(400, win.winfo_screenheight() - 180)
        scale = min(1.0, 700 / img.width, screen_h / img.height)
        shown = img.resize((max(1, round(img.width * scale)),
                            max(1, round(img.height * scale))), pf.RESAMPLE)
        self._preview_ref = ImageTk.PhotoImage(shown)
        ttk.Label(win, image=self._preview_ref, borderwidth=1, relief="solid").pack(padx=10, pady=10)
        ttk.Label(win, text=f"Final size: {img.width} x {img.height} px"
                            + ("" if 1000 <= img.width <= 1200
                               else "   (brief asks for 1000-1200 px wide)")
                  ).pack(pady=(0, 10))
        self.set_status(f"Preview built: {img.width} x {img.height} px.")

    def save(self):
        meta = self.meta()
        issues = meta.problems()
        if issues:
            messagebox.showwarning("Missing details", "Fix these first:\n\n- " + "\n- ".join(issues))
            return
        if not self.paths:
            messagebox.showwarning("Nothing to fuse", "Add at least one image first.")
            return

        try:
            path, img = pf.export(self.paths, meta, self.out_dir.get(),
                                  self.settings(), write_csv=self.csv_var.get())
        except Exception as exc:                       # noqa: BLE001 - shown to user
            traceback.print_exc()
            messagebox.showerror("Could not save", str(exc))
            self.set_status(str(exc), error=True)
            return

        self.last_saved = path
        note = "" if 1000 <= img.width <= 1200 else f"  (width {img.width} px is outside 1000-1200)"
        nudge = "  Now press Add to Excel sheet." if self.xlsx_path.get().strip() else ""
        # The form is deliberately left exactly as it is: Add to Excel reads
        # these same boxes, so quietly flipping Type to MS here would file the
        # row under the wrong picture.
        self.set_status(f"Saved {path.name} - {img.width} x {img.height} px{note}.{nudge}")

    def add_to_sheet(self):
        """Record this question in the spreadsheet - one row, Q and MS together."""
        if ts is None:
            messagebox.showerror("Excel support missing", SHEET_ERROR)
            return

        meta = self.meta()
        issues = meta.problems()
        if issues:
            messagebox.showwarning("Missing details", "Fix these first:\n\n- " + "\n- ".join(issues))
            return

        template = self.xlsx_path.get().strip()
        if not template:
            messagebox.showwarning(
                "No spreadsheet chosen",
                "Press Choose... next to 'Excel sheet' and pick your "
                "easify-topical-template.xlsx first.")
            return

        try:
            book = ts.working_copy(template, self.out_dir.get())
            result = ts.add_row(book, meta)
        except ts.SheetError as exc:
            messagebox.showerror("Could not update the spreadsheet", str(exc))
            self.set_status(str(exc), error=True)
            return
        except Exception as exc:                   # noqa: BLE001 - shown to user
            traceback.print_exc()
            messagebox.showerror("Could not update the spreadsheet", str(exc))
            self.set_status(str(exc), error=True)
            return

        # The row names both pictures, so warn about whichever is not saved yet
        # - the sheet and the images on the USB have to match.
        folder = Path(self.out_dir.get())
        missing = [name for name in (meta.filename("Q"), meta.filename("MS"))
                   if not (folder / name).exists()]
        warning = ("  Still to save: " + ", ".join(missing)) if missing else ""

        self.remember()
        verb = "Updated" if result.updated else "Added"
        self.set_status(
            f"{verb} row {result.row} of {result.path.name} ({result.sheet}) - "
            f"both {meta.filename('Q')} and {meta.filename('MS')} written.{warning}")

    def open_sheet(self):
        target = self.xlsx_path.get().strip()
        if not target:
            messagebox.showinfo("No spreadsheet chosen", "Choose your .xlsx first.")
            return
        copy = Path(self.out_dir.get()) / Path(target).name
        self._open(copy if copy.exists() else Path(target))

    def choose_xlsx(self):
        chosen = filedialog.askopenfilename(title="Choose your easify-topical-template.xlsx",
                                            filetypes=EXCEL_TYPES)
        if chosen:
            self.xlsx_path.set(chosen)
            self.remember()
            self.set_status(f"Spreadsheet set to {Path(chosen).name}.")

    def remember(self):
        """Keep the folder and spreadsheet for next time."""
        save_settings({"out_dir": self.out_dir.get().strip(),
                       "xlsx_path": self.xlsx_path.get().strip()})

    def choose_out_dir(self):
        chosen = filedialog.askdirectory(title="Where should finished images go?",
                                         initialdir=self.out_dir.get())
        if chosen:
            self.out_dir.set(chosen)
            self.remember()

    def open_out_dir(self):
        target = Path(self.out_dir.get())
        target.mkdir(parents=True, exist_ok=True)
        self._open(target)

    def _open(self, target: Path):
        """Hand a file or folder to whatever the system opens it with."""
        if sys.platform == "win32":
            os.startfile(target)                       # noqa: S606 - opening a file/folder
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    scale = pf.enable_hidpi()
    root = tk.Tk()
    root.title("Photo Fuse - Easify topical questions")
    if scale > 1.01:
        root.tk.call("tk", "scaling", 96.0 * scale / 72.0)
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass

    app = App(root, preload=argv)

    # Fit inside the screen so the buttons are never pushed out of sight on
    # smaller laptop displays.
    root.update_idletasks()
    width = min(root.winfo_reqwidth(), root.winfo_screenwidth() - 60)
    height = min(root.winfo_reqheight(), root.winfo_screenheight() - 110)
    root.geometry(f"{width}x{height}+30+20")
    root.minsize(int(880 * scale), int(500 * scale))
    root.bind("<Control-s>", lambda _e: app.save())
    root.bind("<Control-p>", lambda _e: app.preview())
    root.bind("<Control-e>", lambda _e: app.add_to_sheet())
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
