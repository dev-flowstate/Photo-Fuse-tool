"""
Setup check
===========

Reports which Python is being used and which libraries it can see, so a
"module not found" problem stops being guesswork. Run it by double-clicking
`Check setup.bat`.

The usual cause of a package looking missing when it is definitely installed:
the computer has more than one Python, and the package went into a different
one from the one the tool runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGES = [
    ("PIL", "Pillow", "images", True),
    ("numpy", "numpy", "pixel maths", True),
    ("openpyxl", "openpyxl", "writing the spreadsheet", True),
    ("fitz", "pymupdf", "reading PDFs (PDF Cleaner only)", True),
    ("tkinter", "tkinter", "the windows themselves", False),
]

HERE = Path(__file__).resolve().parent


def main() -> int:
    print("=" * 62)
    print("  Photo Fuse / PDF Cleaner - setup check")
    print("=" * 62)
    print()
    print("The Python being used:")
    print(f"   {sys.executable}")
    print(f"   version {sys.version.split()[0]}")
    if sys.version_info < (3, 9):
        print("   ^ TOO OLD. Python 3.10 or newer is needed.")
    print()

    print("Libraries:")
    missing = []
    for module, package, why, pip_installable in PACKAGES:
        try:
            loaded = __import__(module)
            version = getattr(loaded, "__version__", "")
            where = getattr(loaded, "__file__", "") or "(built in)"
            print(f"   [ok]      {package:<10} {version:<10} - {why}")
            if module == "fitz" and "pymupdf" not in where.lower() \
                    and "fitz" not in Path(where).parts[-2:]:
                print(f"             note: loaded from {where}")
        except ImportError:
            print(f"   [MISSING] {package:<10} {'':<10} - {why}")
            if pip_installable:
                missing.append(package)
            else:
                print("             tkinter comes with Python. Reinstall Python "
                      "from python.org and\n             tick the tcl/tk option.")
    print()

    print("Project files:")
    for name in ("photofuse.py", "topical_sheet.py", "requirements.txt"):
        mark = "ok" if (HERE / name).is_file() else "MISSING"
        print(f"   [{mark}] {name}")
    cleaner = HERE / "PDF CLeaner" / "pdfcleaner.py"
    print(f"   [{'ok' if cleaner.is_file() else 'MISSING'}] PDF CLeaner\\pdfcleaner.py")
    print()

    if missing:
        print("-" * 62)
        print("  WHAT TO DO")
        print("-" * 62)
        print()
        print("Those libraries are missing FROM THIS Python. If you believe you")
        print("already installed them, they went into a different Python that is")
        print("also on this computer - which is very common.")
        print()
        print("Fix it by installing them into this exact one. Copy this line:")
        print()
        print(f'   "{sys.executable}" -m pip install {" ".join(missing)}')
        print()
        print("Or just double-click \"1 - INSTALL (run me first).bat\", which")
        print("installs into whichever Python the tools actually use.")
        print()
        print("If you would rather use a different Python you already have set")
        print("up, put its full path to python.exe on the first line of a file")
        print("called python-path.txt next to this script, for example:")
        print()
        print("   D:\\Programs\\Python311\\python.exe")
        print()
        return 1

    print("-" * 62)
    print("  Everything needed is present. You are good to go.")
    print("-" * 62)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
