"""
Setup check
===========

Reports which Python is being used and which libraries it can see, then offers
to install whatever is missing - and shows the real error if pip refuses, so a
failing install stops being a mystery.

Run it by double-clicking `Check setup.bat`.

The usual cause of a package looking missing when it is definitely installed:
the computer has more than one Python, and the package went into a different
one from the one the tools run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

#: (import name, pip name, what it is for)
PHOTO_FUSE_NEEDS = [
    ("PIL", "Pillow", "images"),
    ("numpy", "numpy", "pixel maths"),
    ("openpyxl", "openpyxl", "writing the spreadsheet"),
]
PDF_CLEANER_NEEDS = [
    ("fitz", "pymupdf", "reading PDFs"),
]

HERE = Path(__file__).resolve().parent
LINE = "=" * 62
RULE = "-" * 62


def check(group) -> list[str]:
    """Print each library's state; return the pip names that are missing."""
    missing = []
    for module, package, why in group:
        try:
            loaded = __import__(module)
        except ImportError:
            print(f"   [MISSING] {package:<10} {'':<10} - {why}")
            missing.append(package)
        else:
            version = getattr(loaded, "__version__", "")
            print(f"   [ok]      {package:<10} {version:<10} - {why}")
    return missing


def install(packages: list[str]) -> bool:
    """
    Try to install, showing everything pip says.

    A second attempt with --user follows a failure, because that is what gets
    past a Python installed somewhere the account cannot write to.
    """
    base = [sys.executable, "-m", "pip", "install"]
    for extra in ([], ["--user"]):
        command = base + extra + packages
        print()
        print(RULE)
        print("  Running: " + " ".join(command[1:]))
        print(RULE)
        print()
        try:
            result = subprocess.run(command)
        except OSError as exc:
            print(f"  Could not even start pip: {exc}")
            return False
        if result.returncode == 0:
            print()
            print("  pip finished successfully.")
            return True
        print()
        print(f"  pip failed (exit code {result.returncode}).")
        if not extra:
            print("  Trying again with --user ...")
    return False


def main(argv: list[str] | None = None) -> int:
    # --fix installs whatever is missing without asking, so setup.bat can run
    # the whole thing start to finish unattended.
    auto = "--fix" in (argv if argv is not None else sys.argv[1:])

    print(LINE)
    print("  Photo Fuse / PDF Cleaner - setup check")
    print(LINE)
    print()
    print("The Python being used:")
    print(f"   {sys.executable}")
    print(f"   version {sys.version.split()[0]}")
    if sys.version_info < (3, 9):
        print("   ^ TOO OLD. Python 3.10 or newer is needed.")
    print()

    print("Photo Fuse needs:")
    missing_core = check(PHOTO_FUSE_NEEDS)
    print()
    print("PDF Cleaner also needs:")
    missing_pdf = check(PDF_CLEANER_NEEDS)
    print()

    try:
        import tkinter                                    # noqa: F401
    except ImportError:
        print("   [MISSING] tkinter - the windows themselves.")
        print("             tkinter comes with Python. Reinstall Python from")
        print("             python.org and tick the tcl/tk option.")
        print()

    print("Project files:")
    for name in ("photofuse.py", "topical_sheet.py", "requirements.txt"):
        print(f"   [{'ok' if (HERE / name).is_file() else 'MISSING'}] {name}")
    cleaner = HERE / "PDF CLeaner" / "pdfcleaner.py"
    print(f"   [{'ok' if cleaner.is_file() else 'MISSING'}] PDF CLeaner\\pdfcleaner.py")
    print()

    print(RULE)
    print(f"  Photo Fuse:  {'READY' if not missing_core else 'needs ' + ', '.join(missing_core)}")
    print(f"  PDF Cleaner: {'READY' if not (missing_core or missing_pdf) else 'needs ' + ', '.join(missing_core + missing_pdf)}")
    print(RULE)
    print()

    missing = missing_core + missing_pdf
    if not missing:
        print("  Everything is present. You are good to go.")
        print()
        return 0

    if not missing_core:
        print("  Photo Fuse works right now - only PDF Cleaner is short of")
        print(f"  {', '.join(missing_pdf)}.")
        print()

    print(f"  Missing from THIS Python: {', '.join(missing)}")
    print()
    print("  If you are sure you installed these already, they went into a")
    print("  different Python on this computer. What matters is getting them")
    print("  into the one named at the top of this page.")
    print()

    if auto:
        answer = "y"
        print("  Installing them now...")
    else:
        try:
            answer = input("  Install them now into that Python? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

    if answer in ("", "y", "yes"):
        if install(missing):
            print()
            print("  Done. Run this check again to confirm.")
            return 0
        print()
        print(RULE)
        print("  pip could not install them. What the message above usually means")
        print(RULE)
        print()
        print("  'Access is denied' / 'Permission denied'")
        print("     Close any open Python windows and try again, or right-click")
        print("     Check setup.bat and choose Run as administrator.")
        print()
        print("  'No matching distribution found'")
        print("     This Python is too new for that library yet. Install Python")
        print("     3.12 from python.org, then put its path in python-path.txt.")
        print()
        print("  'Could not find a version' / connection or SSL errors")
        print("     A firewall is in the way. Try:")
        print(f'        "{sys.executable}" -m pip install --trusted-host pypi.org '
              f'--trusted-host files.pythonhosted.org {" ".join(missing)}')
        print()
        print("  Nothing works?")
        print("     Install Python 3.12 from python.org (tick 'Add python.exe to")
        print("     PATH'), then run \"1 - INSTALL (run me first).bat\" again.")
        print()
        return 1

    print()
    print("  Nothing installed. To do it yourself, copy this line:")
    print()
    print(f'     "{sys.executable}" -m pip install {" ".join(missing)}')
    print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
