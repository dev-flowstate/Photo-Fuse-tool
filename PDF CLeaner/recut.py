"""
Follow a running batch and re-cut the papers it got wrong.

The batch holds the code it started with, so a fix made while it runs does
not reach it. Rather than stop and lose the hours already spent, this walks
behind it: for every paper the batch has finished, it reads the paper again
with the current code and, where that now finds a different set of
questions, cuts that one paper again and replaces its images.

It only ever touches papers the batch has already logged, so the two never
work on the same paper at once. It exits once the batch is finished and
there is nothing left to redo.

    py recut.py                       (follow until the batch ends)
    py recut.py --once                (one pass over what is done so far)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdfcleaner as pc

try:
    import fitz
except ImportError:                                  # pragma: no cover
    import pymupdf as fitz

OUT = Path(r"D:\Papers\output questions and markschemes")


def question_count(path: Path) -> int | None:
    """How many questions this paper holds, read with the current code."""
    doc = fitz.open(str(path))
    try:
        answers_from = pc.first_answer_table_page(doc)
        kind = pc.detect_kind(path, doc)
        stamps = pc.stamp_rects(doc)
        bands = pc.header_footer_bands(doc)
        spans = []
        for index in range(doc.page_count):
            page = doc[index]
            pc.whiten(page, stamps.get(index, ()))
            pc.strip_furniture(page, bands)
            spans.append(pc.body_spans(page))
        searchable = spans if not answers_from else [
            [] if i < answers_from else sp for i, sp in enumerate(spans)]
        found = (pc.find_questions_ms(searchable) if kind == "ms"
                 else pc.find_questions_qp(searchable))
        return len(found)
    finally:
        doc.close()


def recut(path: Path, out: Path, dpi: int) -> int:
    """Cut this paper again, replacing whatever is there."""
    staging = out / f"_recut_{path.stem}"
    try:
        result = pc.clean_pdf(path, staging, pc.CleanSettings(
            dpi=dpi, split_questions=True, save_pdf=False))
        for old in out.glob(f"{path.stem}_q*.png"):
            old.unlink()
        moved = 0
        for png in sorted((result.questions_dir or staging).glob("*.png")):
            shutil.move(str(png), str(out / png.name))
            moved += 1
        return moved
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Re-cut papers a running batch got wrong.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--dpi", type=int, default=400)
    p.add_argument("--once", action="store_true", help="one pass, then stop")
    a = p.parse_args(argv)

    out = Path(a.out)
    log = out / "_batch_log.jsonl"
    mine = out / "_recut_log.jsonl"

    seen: set[str] = set()
    if mine.is_file():
        for line in mine.read_text(encoding="utf-8").splitlines():
            if line.strip():
                seen.add(json.loads(line)["name"])

    fixed = checked = 0
    while True:
        rows = []
        if log.is_file():
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
        batch_done = out.joinpath("_batch_stdout.txt").is_file() and "batch finished" in \
            out.joinpath("_batch_stdout.txt").read_text(errors="replace")[-400:]

        work = [r for r in rows if r["name"] not in seen and r.get("status") == "ok"]
        if not work:
            if a.once or batch_done:
                break
            time.sleep(30)
            continue

        for row in work:
            path = Path(row["paper"])
            seen.add(row["name"])
            checked += 1
            if not path.is_file():
                continue
            try:
                now = question_count(path)
            except Exception as exc:                   # noqa: BLE001 - reported
                print(f"  {row['name']}: {type(exc).__name__}", flush=True)
                continue
            have = len(list(out.glob(f"{path.stem}_q*.png")))
            note = {"name": row["name"], "was": have, "now": now}
            if now is not None and now != have and now > 0:
                try:
                    note["written"] = recut(path, out, a.dpi)
                    fixed += 1
                    print(f"[{fixed}] {row['name']:<26} {have} -> {note['written']} "
                          f"questions   ({checked} checked)", flush=True)
                except Exception as exc:               # noqa: BLE001 - reported
                    note["error"] = f"{type(exc).__name__}: {exc}"[:160]
                    print(f"  {row['name']}: {note['error']}", flush=True)
            with mine.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(note, ensure_ascii=False) + "\n")

    print(f"re-cut finished: {checked} papers checked, {fixed} cut again", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
