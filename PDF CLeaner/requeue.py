"""
Queue the papers the audit found fault with, so the batch redoes just those.

Deletes their images and drops their rows from the batch log, leaving every
clean paper alone. Running batch_all.py afterwards picks up exactly the
papers that were dropped.

    py requeue.py            (report what would be redone)
    py requeue.py --apply    (delete those images and drop their log rows)
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

OUT = Path(r"D:\Papers\output questions and markschemes")

#: Faults that say nothing about the images. A text layer arriving in
#: fragments only matters if something came of it, and that something would
#: show up as one of the other faults.
HARMLESS = {"shredded", "mixed-rotation"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Requeue the papers with faults.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)

    out = Path(a.out)
    report = out / "audit.json"
    if not report.is_file():
        print(f"No audit to read. Run audit.py first.\n  looked in {report}")
        return 1
    rows = json.loads(report.read_text(encoding="utf-8"))

    redo = {row["name"] for row in rows
            if set(row.get("faults", ())) - HARMLESS}
    reasons: Counter = Counter(
        fault for row in rows if row["name"] in redo
        for fault in set(row.get("faults", ())) - HARMLESS)

    log = out / "_batch_log.jsonl"
    done = []
    if log.is_file():
        done = [json.loads(line)
                for line in log.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    images = [png for png in out.rglob("*.png")
              if "_q" in png.stem and png.stem.rsplit("_q", 1)[0] in redo]

    print(f"{len(redo)} papers to redo, {len(images)} images to remove")
    print(f"{len(done) - sum(1 for r in done if r['name'] in redo)} papers stay done")
    for fault, count in reasons.most_common():
        print(f"   {fault:<16} {count}")

    if not a.apply:
        print("\nreport only - pass --apply to clear them for the batch")
        return 0

    for png in images:
        png.unlink()
    if done:
        keep = [r for r in done if r["name"] not in redo]
        log.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                               for r in keep), encoding="utf-8")
        print(f"\nlog now holds {len(keep)} finished papers")
    print(f"removed {len(images)} images - run batch_all.py to rebuild them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
