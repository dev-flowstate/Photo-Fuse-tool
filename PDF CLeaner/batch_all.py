"""
Batch runner - every paper in a folder tree into per-question PNGs.

Resumable: each finished paper is recorded, so stopping and restarting picks
up where it left off rather than redoing work. Failures are logged and the
run carries on.

    py batch_all.py "D:\\Papers" --out "D:\\Papers\\output questions and markschemes"
    py batch_all.py "D:\\Papers" --dpi 400
    py batch_all.py "D:\\Papers" --status        (progress only, runs nothing)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdfcleaner as pc


def load_done(log: Path) -> dict:
    if not log.is_file():
        return {}
    done = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("paper"):
            done[row["paper"]] = row
    return done


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Split every paper in a tree into question PNGs.")
    p.add_argument("root", help="folder to search for PDFs (recursively)")
    p.add_argument("--out", default=None, help="where the PNGs go")
    p.add_argument("--dpi", type=int, default=400)
    p.add_argument("--status", action="store_true", help="show progress and exit")
    p.add_argument("--limit", type=int, default=0, help="stop after N papers (testing)")
    a = p.parse_args(argv)

    root = Path(a.root)
    if not root.is_dir():
        print(f"No such folder: {root}")
        return 1
    out = Path(a.out) if a.out else root.parent / "output questions and markschemes"
    out.mkdir(parents=True, exist_ok=True)
    log = out / "_batch_log.jsonl"

    pdfs = sorted(q for q in root.rglob("*.pdf"))
    done = load_done(log)

    if a.status:
        ok = sum(1 for r in done.values() if r.get("questions", 0) > 0)
        none = sum(1 for r in done.values() if r.get("status") == "no-questions")
        bad = sum(1 for r in done.values() if r.get("status") == "error")
        images = len(list(out.glob("*.png")))
        print(f"papers found     : {len(pdfs)}")
        print(f"processed        : {len(done)}  ({len(pdfs) - len(done)} remaining)")
        print(f"  with questions : {ok}")
        print(f"  no questions   : {none}")
        print(f"  errors         : {bad}")
        print(f"PNGs written     : {images}")
        return 0

    todo = [q for q in pdfs if str(q) not in done]
    print(f"{len(pdfs)} papers, {len(done)} already done, {len(todo)} to go", flush=True)

    started = time.time()
    for i, pdf in enumerate(todo, 1):
        if a.limit and i > a.limit:
            break
        row = {"paper": str(pdf), "name": pdf.stem}
        t0 = time.time()
        staging = out / f"_tmp_{pdf.stem}"
        try:
            settings = pc.CleanSettings(dpi=a.dpi, split_questions=True, save_pdf=False)
            result = pc.clean_pdf(pdf, staging, settings)

            moved = 0
            for png in sorted((result.questions_dir or staging).glob("*.png")):
                target = out / png.name
                if target.exists():
                    target.unlink()
                shutil.move(str(png), str(target))
                moved += 1

            row.update(status="ok" if moved else "no-questions", questions=moved,
                       pages_in=result.pages_in, pages_out=result.pages_out,
                       seconds=round(time.time() - t0, 1))
        except Exception as exc:                       # noqa: BLE001 - logged
            row.update(status="error", questions=0,
                       error=f"{type(exc).__name__}: {exc}"[:300],
                       seconds=round(time.time() - t0, 1))
            traceback.print_exc(file=sys.stderr)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        rate = (time.time() - started) / i
        left = (len(todo) - i) * rate / 3600
        print(f"[{i}/{len(todo)}] {pdf.name:<28} {row['status']:<13} "
              f"{row.get('questions', 0):>3} qs  {row['seconds']:>5.1f}s   "
              f"~{left:.1f}h left", flush=True)

    print("batch finished", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
