"""
Rebuild the papers already handed over, into a folder of their own.

321 of the 412 question pictures loaded into the database were cut by the
fixed page crop and are missing the marks off the foot of a part. They
cannot simply be replaced where they stand, because the database points at
what was loaded - so the corrected pictures are written somewhere separate
and swapped in deliberately.

The mark scheme pictures are not touched. The crop fault was a question
paper fault throughout: of the 416 papers it hit, not one was a mark
scheme.

    py replacements.py             (say what it would rebuild)
    py replacements.py --apply --workers 6
"""

from __future__ import annotations

import argparse
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pdfcleaner as pc

OUT = Path(r"D:\Papers\output questions and markschemes")
ROOT = Path(r"D:\Papers\all folders\all folders")
DEST = "already done replacements"


def rebuild(job) -> dict:
    """Cut one paper again and move its pictures into the replacement folder."""
    name, source, dest, dpi = job
    row = {"name": name}
    try:
        stage = Path(dest) / f"_stage_{name}"
        # clean_pdf works out the kind and picks its profile, exactly as the
        # batch does, so the replacements come off the same rules as the rest.
        settings = pc.CleanSettings(dpi=dpi, split_questions=True,
                                    save_pdf=False)
        written = pc.clean_pdf(Path(source), stage / "x.pdf", settings)
        target = Path(dest)
        target.mkdir(parents=True, exist_ok=True)
        moved = 0
        for png in sorted((written.questions_dir or stage).glob("*.png")):
            shutil.move(str(png), str(target / png.name))
            moved += 1
        shutil.rmtree(stage, ignore_errors=True)
        row["images"] = moved
        row["status"] = "ok"
    except Exception as exc:                              # noqa: BLE001
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"[:160]
    return row


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Rebuild the handed-over papers into a separate folder.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--root", default=str(ROOT))
    p.add_argument("--dpi", type=int, default=400)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)

    out, root = Path(a.out), Path(a.root)
    handed = out / "already done" / "questions"
    papers = sorted({png.stem.rsplit("_q", 1)[0]
                     for png in handed.glob("*.png")})
    if not papers:
        print(f"Nothing in {handed}.")
        return 1

    dest = out / DEST / "questions"
    jobs = []
    missing = []
    for name in papers:
        pdf = next(root.rglob(name + ".pdf"), None)
        if pdf is None:
            missing.append(name)
            continue
        jobs.append((name, str(pdf), str(dest), a.dpi))

    images = len(list(handed.glob("*.png")))
    print(f"{len(papers)} question papers were handed over, "
          f"{images} pictures between them")
    print(f"rebuilding {len(jobs)} of them into {dest}")
    if missing:
        print(f"  {len(missing)} have no PDF any more: {missing[:5]}")
    print("  the 412 mark scheme pictures are left alone - the crop fault "
          "never touched a mark scheme")
    if not a.apply:
        print("\nreport only - pass --apply to do it")
        return 0

    started, done, made = time.time(), 0, 0
    bad = []
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for row in pool.map(rebuild, jobs, chunksize=1):
            done += 1
            made += row.get("images", 0)
            if row["status"] != "ok":
                bad.append(row)
            rate = (time.time() - started) / done
            print(f"[{done}/{len(jobs)}] {row['name']:<20} {row['status']:<8} "
                  f"{row.get('images', 0):>3} images   "
                  f"~{(len(jobs)-done)*rate/60:.0f} min left", flush=True)

    print(f"\n{made} pictures written to {dest}")
    if bad:
        print(f"{len(bad)} failed:")
        for row in bad[:5]:
            print(f"   {row['name']}: {row.get('error')}")

    # Say plainly which of the loaded pictures this replaces, and whether any
    # of them has gone or appeared - a question that was being cut in the
    # wrong place can come back as a different number of pictures.
    before = {png.name for png in handed.glob("*.png")}
    after = {png.name for png in dest.glob("*.png")}
    print(f"\n  {len(before & after)} replace a picture already loaded")
    if after - before:
        print(f"  {len(after - before)} are new: {sorted(after - before)[:8]}")
    if before - after:
        print(f"  {len(before - after)} loaded pictures have no replacement: "
              f"{sorted(before - after)[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
