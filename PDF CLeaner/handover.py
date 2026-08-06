"""
Set aside the images that have already gone to the database.

412 mark scheme pictures were made at half size before the run was stopped,
and those - with the matching question paper pictures - have been handed
over. They must not move or change again, or the database will point at
something different from what was loaded.

So they are taken out of the working set into folders of their own: the
half-size ones are moved, since everything left in the web folders is then
by definition still to do, and the 400 dpi originals are copied, since
those folders are the archive everything else is rebuilt from.

    py handover.py             (say what it would do)
    py handover.py --apply
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

OUT = Path(r"D:\Papers\output questions and markschemes")
DONE = "already done"
DONE_BIG = "done highquality 400dpi"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Set the handed-over images aside.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    out = Path(a.out)

    web_ms = out / "markschemes_clean_web"
    handed = sorted(png.name for png in web_ms.glob("*.png"))
    if not handed:
        print(f"Nothing in {web_ms}. Nothing has been handed over.")
        return 1
    mates = [name.replace("_ms_", "_qp_") for name in handed]

    # (source folder, file names, destination, whether to move)
    plan = [
        (out / "markschemes_clean_web", handed,
         out / DONE / "markschemes", True),
        (out / "questions_clean_web", mates,
         out / DONE / "questions", True),
        (out / "markschemes_clean", handed,
         out / DONE_BIG / "markschemes", False),
        (out / "questions_clean", mates,
         out / DONE_BIG / "questions", False),
    ]

    print(f"{len(handed)} mark scheme images already handed over, "
          f"covering {len({n.rsplit('_q', 1)[0] for n in handed})} papers")
    print(f"{len(mates)} question paper images go with them\n")

    for source, names, dest, move in plan:
        there = [n for n in names if (source / n).is_file()]
        missing = len(names) - len(there)
        word = "move" if move else "copy"
        print(f"  {word} {len(there):>4} from {source.name:<24} -> "
              f"{dest.parent.name}/{dest.name}"
              + (f"   ({missing} not there)" if missing else ""))
        if not a.apply:
            continue
        dest.mkdir(parents=True, exist_ok=True)
        for name in there:
            target = dest / name
            if target.exists():
                continue
            if move:
                shutil.move(str(source / name), str(target))
            else:
                shutil.copy2(str(source / name), str(target))

    if not a.apply:
        print("\nreport only - pass --apply to do it")
        return 0

    print()
    for folder in (out / DONE, out / DONE_BIG):
        total = sum(1 for _ in folder.rglob("*.png"))
        print(f"  {folder.name:<26} {total} images")
    left = sum(1 for _ in (out / "questions_clean_web").glob("*.png"))
    print(f"\n  still in questions_clean_web: {left} "
          f"(these are rebuilt, the handed-over ones are not)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
