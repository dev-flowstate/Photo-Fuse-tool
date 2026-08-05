"""
Make a web-sized copy of the finished question images.

The 400 dpi pictures are archival - around 2800 pixels across, more than
any screen shows. Halving them gives the same picture at a quarter of the
weight, and shrinking from 400 dpi is if anything sharper than rendering
at 200 would have been, because four pixels average into one.

The originals are left exactly where they are, so a different size can be
made later from them rather than from the paper again.

    py webset.py                 (report what it would make)
    py webset.py --apply         (make it)
    py webset.py --apply --scale 0.4
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = 500_000_000

OUT = Path(r"D:\Papers\output questions and markschemes")
SOURCES = ("questions_clean", "markschemes_clean")


def shrink(job: tuple[str, str, float]) -> tuple[str, int, int]:
    """Write one image at the smaller size. Returns (name, before, after)."""
    src, dst, scale = job
    source, target = Path(src), Path(dst)
    before = source.stat().st_size
    with Image.open(source) as im:
        width = max(1, round(im.width * scale))
        height = max(1, round(im.height * scale))
        # LANCZOS averages the pixels it drops rather than throwing them
        # away, which is what keeps small text readable.
        small = im.resize((width, height), Image.LANCZOS)
        # Nearly all of these are black on white. Stored as RGB that is three
        # bytes a pixel to say the same thing three times, and resampling
        # turns crisp edges into shades that compress far worse - converted
        # this way a page came out LARGER than the 400 dpi original it was
        # made from. Grey costs a third of that and loses nothing, so it is
        # used wherever the three channels agree.
        # Asking for the channels to agree exactly is too strict: the
        # renderer smooths edges a shade differently in each, so a plain page
        # of black text reads as "colour" on 5% of its pixels - by one or
        # two levels out of 255, which no eye sees. A real photograph
        # differs by fifty or more. So a page counts as grey unless a
        # noticeable fraction of it is noticeably coloured.
        if small.mode not in ("L", "1"):
            rgb = np.asarray(small.convert("RGB")).astype(np.int16)
            spread = rgb.max(axis=2) - rgb.min(axis=2)
            if float((spread > 12).mean()) < 0.002:
                small = small.convert("L")
        small.save(target, format="PNG", optimize=True, compress_level=9)
    return source.name, before, target.stat().st_size


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Make a web-sized copy of the clean set.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--scale", type=float, default=0.5,
                   help="fraction of the original size (default: a half)")
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)

    out = Path(a.out)
    jobs, source_bytes = [], 0
    for folder in SOURCES:
        here = out / folder
        if not here.is_dir():
            continue
        dest = out / f"{folder}_web"
        for png in sorted(here.glob("*.png")):
            source_bytes += png.stat().st_size
            jobs.append((str(png), str(dest / png.name), a.scale))

    if not jobs:
        print(f"Nothing to convert. Looked in {out} for {', '.join(SOURCES)}.")
        return 1

    with Image.open(jobs[0][0]) as sample:
        was = sample.size
    now = (round(was[0] * a.scale), round(was[1] * a.scale))
    print(f"{len(jobs)} images, {source_bytes/1e9:.2f} GB")
    print(f"a typical one goes {was[0]}x{was[1]} -> {now[0]}x{now[1]}")

    if not a.apply:
        print("\nreport only - pass --apply to make it")
        return 0

    for folder in SOURCES:
        (out / f"{folder}_web").mkdir(exist_ok=True)

    workers = a.workers if a.workers > 0 else max(1, (os.cpu_count() or 2) // 2)
    print(f"converting, {workers} at a time", flush=True)

    started, done, written = time.time(), 0, 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for name, before, after in pool.map(shrink, jobs, chunksize=16):
            done += 1
            written += after
            if done % 2000 == 0:
                rate = (time.time() - started) / done
                print(f"  {done}/{len(jobs)}  ~{(len(jobs)-done)*rate/60:.0f} min left",
                      flush=True)

    print(f"\nwritten {written/1e9:.2f} GB  "
          f"({written/source_bytes*100:.0f}% of the originals)")
    for folder in SOURCES:
        here = out / f"{folder}_web"
        print(f"  {here.name:<24} {len(list(here.glob('*.png')))} images")
    print(f"\nthe 400 dpi originals are untouched in "
          f"{', '.join(SOURCES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
