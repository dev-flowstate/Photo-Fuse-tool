"""
Make a web-sized copy of the finished question images.

The 400 dpi pictures are archival - around 2800 pixels across, more than
any screen shows. Shrinking from 400 dpi is if anything sharper than
rendering at 200 would have been, because four pixels average into one.

How far to shrink depends on the question. A one-line answer is a few
hundred pixels tall and weighs almost nothing, so there is nothing to be
saved by softening it - and being small on the page, it is the one a reader
looks at closely. A question running over seven pages is a strip twenty
thousand pixels long; no screen will ever show that at full size, so the
detail is paid for and never seen. The tall ones are also where all the
weight is.

So the short ones keep their resolution and the long ones give it up,
which is the opposite of treating them alike. The bands are in SIZES.

The originals are left exactly where they are, so a different size can be
made later from them rather than from the paper again.

    py webset.py                 (report what it would make)
    py webset.py --apply         (make it)
    py webset.py --apply --scale 0.4     (one fixed size, the old way)
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

#: What the pictures were rendered at.
SOURCE_DPI = 400

#: (tallest this band covers, how much of the original to keep). Read in
#: order; the first band a picture fits is the one it gets. Heights are in
#: pixels of the 400 dpi original, so 1200 is three inches - a couple of
#: lines and their answer space.
SIZES = (
    (1200, 1.00),      # a line or two: left alone, it costs nothing
    (3000, 0.75),      # a short question: 300 dpi
    (6000, 0.50),      # a page or so: 200 dpi
    (12000, 0.40),     # several pages: 160 dpi
    (10 ** 9, 0.30),   # the very long strips: 120 dpi
)


def scale_for(height: int) -> float:
    """How much of a picture this tall is worth keeping."""
    for limit, keep in SIZES:
        if height <= limit:
            return keep
    return SIZES[-1][1]


def shrink(job: tuple[str, str, float]) -> tuple[str, int, int]:
    """Write one image at the smaller size. Returns (name, before, after)."""
    src, dst, fixed = job
    source, target = Path(src), Path(dst)
    before = source.stat().st_size
    with Image.open(source) as im:
        scale = fixed if fixed else scale_for(im.height)
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
        # Say what the picture actually is. Without this the file carries no
        # resolution at all and a viewer falls back on 96 dpi, so a 200 dpi
        # page reports itself as 96 and looks, on paper, like a mistake.
        made_at = round(SOURCE_DPI * scale)
        small.save(target, format="PNG", optimize=True, compress_level=9,
                   dpi=(made_at, made_at))
    return source.name, before, target.stat().st_size


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Make a web-sized copy of the clean set.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--scale", type=float, default=0.0,
                   help="one fixed fraction for everything; the default of 0 "
                        "picks a size per picture from how tall it is")
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)

    out = Path(a.out)
    # What has already gone to the database is finished with. Remaking it at
    # a new size would leave the database pointing at a file that no longer
    # matches what was loaded.
    handed = {png.name for png in (out / "already done").rglob("*.png")}

    jobs, source_bytes = [], 0
    for folder in SOURCES:
        here = out / folder
        if not here.is_dir():
            continue
        dest = out / f"{folder}_web"
        for png in sorted(here.glob("*.png")):
            if png.name in handed:
                continue
            source_bytes += png.stat().st_size
            jobs.append((str(png), str(dest / png.name), a.scale))

    if not jobs:
        print(f"Nothing to convert. Looked in {out} for {', '.join(SOURCES)}.")
        return 1

    print(f"{len(jobs)} images, {source_bytes/1e9:.2f} GB"
          + (f"   ({len(handed)} already handed over, left alone)"
             if handed else ""))
    if a.scale:
        print(f"every one of them at {a.scale:.0%} of its size "
              f"({round(SOURCE_DPI * a.scale)} dpi)")
    else:
        print("sized on how tall each one is:")
        bands: Counter = Counter()
        for src, _, _ in jobs:
            with Image.open(src) as im:
                bands[scale_for(im.height)] += 1
        low = 0
        for limit, keep in SIZES:
            count = bands.get(keep, 0)
            if not count:
                low = limit
                continue
            span = (f"up to {limit} px tall" if limit < 10 ** 8
                    else f"over {low} px tall")
            print(f"   {count:>5} images {span:<22} "
                  f"keep {keep:.0%}  ({round(SOURCE_DPI * keep)} dpi)")
            low = limit

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
