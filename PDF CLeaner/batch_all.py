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
import os
import shutil
import sys
import time
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdfcleaner as pc

#: The " (1)" a browser adds when the same paper is downloaded twice.
_COPY = re.compile(r" \(\d+\)$")


def one_paper(job: tuple[str, str, int]) -> dict:
    """
    Clean a single paper and move its questions into the output folder.

    Takes and returns plain data so it can be handed to a worker process.
    Each paper stages into its own folder, named after itself, so several
    can run at once without treading on each other.
    """
    name, out_dir, dpi = job
    pdf, out = Path(name), Path(out_dir)
    row = {"paper": name, "name": pdf.stem}
    started = time.time()
    staging = out / f"_tmp_{pdf.stem}"
    try:
        result = pc.clean_pdf(pdf, staging, pc.CleanSettings(
            dpi=dpi, split_questions=True, save_pdf=False))
        moved = 0
        for png in sorted((result.questions_dir or staging).glob("*.png")):
            target = out / png.name
            if target.exists():
                target.unlink()
            shutil.move(str(png), str(target))
            moved += 1
        row.update(status="ok" if moved else "no-questions", questions=moved,
                   pages_in=result.pages_in, pages_out=result.pages_out)
    except Exception as exc:                           # noqa: BLE001 - logged
        row.update(status="error", questions=0,
                   error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    row["seconds"] = round(time.time() - started, 1)
    return row


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
    p.add_argument("--workers", type=int, default=0,
                   help="papers to clean at once (default: half the logical CPUs)")
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

    # A paper downloaded twice arrives as "<name> (1).pdf" beside "<name>.pdf".
    # Cleaning both wastes the time and puts the same question in the output
    # twice under a name nobody wants, so the copy is passed over.
    copies = [q for q in pdfs if _COPY.search(q.stem)
              and q.with_name(_COPY.sub("", q.stem) + ".pdf").is_file()]
    if copies:
        print(f"skipping {len(copies)} duplicate downloads", flush=True)
        pdfs = [q for q in pdfs if q not in set(copies)]

    todo = [q for q in pdfs if str(q) not in done]
    print(f"{len(pdfs)} papers, {len(done)} already done, {len(todo)} to go", flush=True)

    if a.limit:
        todo = todo[:a.limit]
    jobs = [(str(q), str(out), a.dpi) for q in todo if q.is_file()]

    # One paper has nothing to do with the next, so they run several at a
    # time. The parent keeps the log to itself - several processes appending
    # to one file interleave and corrupt it.
    workers = a.workers if a.workers > 0 else max(1, (os.cpu_count() or 2) // 2)
    workers = max(1, min(workers, len(jobs)))
    print(f"running {workers} at a time", flush=True)

    started = time.time()
    finished = 0
    with log.open("a", encoding="utf-8") as fh:
        if workers == 1:
            results = map(one_paper, jobs)
        else:
            pool = ProcessPoolExecutor(max_workers=workers)
            results = pool.map(one_paper, jobs, chunksize=1)
        try:
            for row in results:
                finished += 1
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                rate = (time.time() - started) / finished
                left = (len(jobs) - finished) * rate / 3600
                print(f"[{finished}/{len(jobs)}] {Path(row['paper']).name:<28} "
                      f"{row['status']:<13} {row.get('questions', 0):>3} qs  "
                      f"{row['seconds']:>5.1f}s   ~{left:.1f}h left", flush=True)
        finally:
            if workers > 1:
                pool.shutdown(wait=True)

    print("batch finished", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
