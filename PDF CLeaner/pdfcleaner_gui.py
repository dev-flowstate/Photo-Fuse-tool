"""
PDF Cleaner - window version
============================

Drop a past paper in, get a tight one back. The cleaning runs on a background
thread so the window keeps responding and can show a progress bar.

    python pdfcleaner_gui.py
    python pdfcleaner_gui.py "paper.pdf"      (pre-loads that file)
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
from dataclasses import replace
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pdfcleaner as pc

PDF_TYPES = [("PDF files", "*.pdf"), ("All files", "*.*")]


class App(ttk.Frame):
    def __init__(self, master: tk.Tk, preload: list[str] | None = None):
        super().__init__(master, padding=14)
        self.grid(row=0, column=0, sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.pdf_path = tk.StringVar()
        self.out_dir = tk.StringVar(value=str(pc.DEFAULT_OUTPUT_DIR))
        self.messages: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_saved: Path | None = None
        self.last_questions: Path | None = None

        self._build_header()
        self._build_file_panel()
        self._build_options_panel()
        self._build_footer()

        if preload:
            self.set_pdf(preload[0])

    # -- layout ------------------------------------------------------------

    def _build_header(self):
        head = ttk.Frame(self)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(head, text="PDF Cleaner", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            head,
            text="Strips the answer lines, blank space, headers and margins out of a past "
                 "paper,\nthen closes the gaps so each question runs on without a page break.",
            foreground="#555", justify="left",
        ).pack(anchor="w")

    def _build_file_panel(self):
        box = ttk.LabelFrame(self, text="1. The paper", padding=8)
        box.grid(row=1, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="PDF file").grid(row=0, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.pdf_path).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(box, text="Choose...", command=self.choose_pdf).grid(row=0, column=2)

        self.info = ttk.Label(box, text="No file chosen yet.", foreground="#666")
        self.info.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        ttk.Label(box, text="Tip: you can drag a PDF straight onto \"Drop PDF here.bat\".",
                  foreground="#666", font=("Segoe UI", 8)
                  ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _build_options_panel(self):
        box = ttk.LabelFrame(self, text="2. What to do (defaults are fine)", padding=8)
        box.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        d = pc.CleanSettings()
        self.o = {
            "pages": tk.StringVar(value=""),
            "dpi": tk.IntVar(value=d.dpi),
            "max_gap_pt": tk.DoubleVar(value=d.max_gap_pt),
            "remove_answer_lines": tk.BooleanVar(value=d.remove_answer_lines),
            "collapse_gaps": tk.BooleanVar(value=d.collapse_gaps),
            "strip_furniture": tk.BooleanVar(value=d.strip_furniture),
            "skip_blank_pages": tk.BooleanVar(value=d.skip_blank_pages),
            "skip_front_matter": tk.BooleanVar(value=d.skip_front_matter),
            "remove_solid_rules": tk.BooleanVar(value=d.remove_solid_rules),
            "grayscale": tk.BooleanVar(value=d.grayscale),
            "split_questions": tk.BooleanVar(value=d.split_questions),
        }

        line1 = ttk.Frame(box)
        line1.pack(fill="x")
        ttk.Label(line1, text="Pages").pack(side="left")
        ttk.Entry(line1, textvariable=self.o["pages"], width=12).pack(side="left", padx=(4, 4))
        ttk.Label(line1, text="(blank = automatic)", foreground="#666").pack(side="left", padx=(0, 16))
        ttk.Label(line1, text="Quality").pack(side="left")
        ttk.Combobox(line1, textvariable=self.o["dpi"], width=6, state="readonly",
                     values=[150, 200, 300, 400]).pack(side="left", padx=(4, 4))
        ttk.Label(line1, text="dpi", foreground="#666").pack(side="left", padx=(0, 16))
        ttk.Label(line1, text="Max blank gap").pack(side="left")
        ttk.Spinbox(line1, from_=2, to=400, textvariable=self.o["max_gap_pt"],
                    width=6).pack(side="left", padx=(4, 2))
        ttk.Label(line1, text="pt", foreground="#666").pack(side="left")

        line2 = ttk.Frame(box)
        line2.pack(fill="x", pady=(8, 0))
        for label, key in (
            ("Erase answer lines", "remove_answer_lines"),
            ("Squash blank space", "collapse_gaps"),
            ("Remove headers/footers/margins", "strip_furniture"),
            ("Skip blank pages", "skip_blank_pages"),
        ):
            ttk.Checkbutton(line2, text=label, variable=self.o[key]).pack(side="left", padx=(0, 14))

        line3 = ttk.Frame(box)
        line3.pack(fill="x", pady=(4, 0))
        for label, key in (
            ("Skip cover & formula pages", "skip_front_matter"),
            ("Also erase solid rules (can damage graphs)", "remove_solid_rules"),
            ("Grayscale (smaller file)", "grayscale"),
        ):
            ttk.Checkbutton(line3, text=label, variable=self.o[key]).pack(side="left", padx=(0, 14))

        ttk.Separator(box, orient="horizontal").pack(fill="x", pady=8)
        line4 = ttk.Frame(box)
        line4.pack(fill="x")
        ttk.Checkbutton(line4, text="Output separate questions",
                        variable=self.o["split_questions"]).pack(side="left")
        ttk.Label(line4,
                  text="- also saves every question as its own PNG (all the same width, "
                       "full resolution)",
                  foreground="#666").pack(side="left", padx=(6, 0))

    def _build_footer(self):
        box = ttk.Frame(self)
        box.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Save to").grid(row=0, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.out_dir).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(box, text="Change...", command=self.choose_out_dir).grid(row=0, column=2)
        ttk.Button(box, text="Open folder", command=self.open_out_dir).grid(row=0, column=3, padx=(6, 0))

        actions = ttk.Frame(box)
        actions.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        self.run_button = ttk.Button(actions, text="Clean PDF", command=self.start)
        self.run_button.pack(side="left")
        self.open_button = ttk.Button(actions, text="Open the cleaned PDF",
                                      command=self.open_result, state="disabled")
        self.open_button.pack(side="left", padx=6)
        self.questions_button = ttk.Button(actions, text="Open the questions folder",
                                           command=self.open_questions, state="disabled")
        self.questions_button.pack(side="left")

        self.progress = ttk.Progressbar(box, mode="determinate")
        self.progress.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10, 0))

        self.status = ttk.Label(box, text="Ready.", foreground="#555")
        self.status.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))

    # -- file handling -----------------------------------------------------

    def set_pdf(self, path: str):
        path = str(Path(path).resolve())
        self.pdf_path.set(path)
        try:
            total = pc.page_count(path)
        except Exception as exc:                    # noqa: BLE001 - shown to user
            self.info.configure(text=f"Could not read that file: {exc}", foreground="#b00020")
            return
        self.info.configure(text=f"{Path(path).name} - {total} pages", foreground="#666")
        self.set_status("Ready. Press Clean PDF.")

    def choose_pdf(self):
        chosen = filedialog.askopenfilename(title="Choose a past paper", filetypes=PDF_TYPES)
        if chosen:
            self.set_pdf(chosen)

    def choose_out_dir(self):
        chosen = filedialog.askdirectory(title="Where should the cleaned PDF go?",
                                         initialdir=self.out_dir.get())
        if chosen:
            self.out_dir.set(chosen)

    def _reveal(self, target: Path):
        if sys.platform == "win32":
            os.startfile(target)                    # noqa: S606 - opening a file/folder
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)

    def open_out_dir(self):
        target = Path(self.out_dir.get())
        target.mkdir(parents=True, exist_ok=True)
        self._reveal(target)

    def open_result(self):
        if self.last_saved and self.last_saved.exists():
            self._reveal(self.last_saved)

    def open_questions(self):
        if self.last_questions and self.last_questions.exists():
            self._reveal(self.last_questions)

    def set_status(self, text: str, error: bool = False):
        self.status.configure(text=text, foreground="#b00020" if error else "#555")

    # -- running -----------------------------------------------------------

    def settings(self) -> pc.CleanSettings:
        o = self.o
        return replace(
            pc.CleanSettings(),
            pages=o["pages"].get().strip(),
            dpi=int(o["dpi"].get()),
            max_gap_pt=max(2.0, float(o["max_gap_pt"].get())),
            remove_answer_lines=o["remove_answer_lines"].get(),
            remove_solid_rules=o["remove_solid_rules"].get(),
            collapse_gaps=o["collapse_gaps"].get(),
            strip_furniture=o["strip_furniture"].get(),
            skip_blank_pages=o["skip_blank_pages"].get(),
            skip_front_matter=o["skip_front_matter"].get(),
            grayscale=o["grayscale"].get(),
            split_questions=o["split_questions"].get(),
        )

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        source = self.pdf_path.get().strip()
        if not source:
            messagebox.showwarning("No file", "Choose a PDF first.")
            return
        if not Path(source).is_file():
            messagebox.showerror("Not found", f"There is no file at:\n{source}")
            return

        try:
            settings = self.settings()
        except (tk.TclError, ValueError):
            messagebox.showerror("Bad setting", "One of the numbers is not valid.")
            return

        self.run_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.progress.configure(value=0, maximum=100)
        self.set_status("Working...")

        out_dir = self.out_dir.get()
        self.worker = threading.Thread(
            target=self._work, args=(source, out_dir, settings), daemon=True)
        self.worker.start()
        self.after(80, self._drain)

    def _work(self, source: str, out_dir: str, settings: pc.CleanSettings):
        """Runs on the background thread - must only talk via the queue."""
        def progress(done: int, total: int, message: str) -> None:
            self.messages.put(("progress", done, total, message))

        try:
            result = pc.clean_pdf(source, out_dir, settings, progress=progress)
            self.messages.put(("done", result))
        except Exception as exc:                    # noqa: BLE001 - shown to user
            self.messages.put(("error", exc, traceback.format_exc()))

    def _drain(self):
        """Runs on the UI thread; pulls whatever the worker has reported."""
        try:
            while True:
                message = self.messages.get_nowait()
                kind = message[0]

                if kind == "progress":
                    _, done, total, text = message
                    self.progress.configure(maximum=max(1, total), value=done)
                    self.set_status(text)

                elif kind == "done":
                    result: pc.Result = message[1]
                    self.progress.configure(value=self.progress["maximum"])
                    self.last_saved = result.path
                    self.last_questions = result.questions_dir
                    self.open_button.configure(state="normal")
                    self.questions_button.configure(
                        state="normal" if result.questions else "disabled")
                    self.run_button.configure(state="normal")

                    extra = ""
                    if result.questions:
                        extra = f"  {len(result.questions)} questions saved separately."
                    elif self.o["split_questions"].get():
                        extra = "  No question numbers were found, so no separate PNGs."
                    self.set_status(
                        f"Saved {result.path.name} - {result.pages_in} pages in, "
                        f"{result.pages_out} out, {result.saved_percent:.0f}% of the "
                        f"vertical space removed.{extra}"
                    )
                    return

                elif kind == "error":
                    _, exc, detail = message
                    print(detail, file=sys.stderr)
                    self.progress.configure(value=0)
                    self.run_button.configure(state="normal")
                    self.set_status(str(exc), error=True)
                    messagebox.showerror("Could not clean that PDF", str(exc))
                    return
        except queue.Empty:
            pass

        if self.worker and self.worker.is_alive():
            self.after(80, self._drain)
        else:
            self.run_button.configure(state="normal")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    scale = pc.pf.enable_hidpi()
    root = tk.Tk()
    root.title("PDF Cleaner - past papers")
    if scale > 1.01:
        root.tk.call("tk", "scaling", 96.0 * scale / 72.0)
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass

    app = App(root, preload=argv)
    root.update_idletasks()
    width = min(root.winfo_reqwidth(), root.winfo_screenwidth() - 60)
    height = min(root.winfo_reqheight(), root.winfo_screenheight() - 110)
    root.geometry(f"{width}x{height}+40+40")
    root.minsize(int(840 * scale), int(420 * scale))
    root.bind("<Control-Return>", lambda _e: app.start())
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
