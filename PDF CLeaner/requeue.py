"""
Redo only the papers the split-column fault touched.

Detection is text-only and quick, so every paper already finished is
re-detected twice - once with the fix and once without - and only those
whose question starts move are thrown away and queued again. Papers that
came out the same either way keep their images and stay done.

    py requeue.py            (report only)
    py requeue.py --apply    (delete those images and drop their log rows)
"""
import json
import sys
from pathlib import Path
import fitz

sys.path.insert(0, r"e:\Photo Fuse tool\PDF CLeaner")
import pdfcleaner as pc

OUT = Path(r"D:\Papers\output questions and markschemes")
LOG = OUT / "_batch_log.jsonl"
apply = "--apply" in sys.argv


def starts(path: Path) -> list[tuple[int, float, int]]:
    doc = fitz.open(str(path))
    try:
        answers_from = pc.first_answer_table_page(doc)
        stamps = pc.stamp_rects(doc)
        bands = pc.header_footer_bands(doc)
        spans = []
        for i in range(doc.page_count):
            page = doc[i]
            pc.whiten(page, stamps.get(i, ()))
            pc.strip_furniture(page, bands)
            spans.append(pc.body_spans(page))
        searchable = spans if not answers_from else [
            [] if i < answers_from else sp for i, sp in enumerate(spans)]
        return [(p, round(y, 1), n) for p, y, n in pc.find_question_starts(searchable)]
    finally:
        doc.close()


rows = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines()
        if line.strip()]
print(f"{len(rows)} papers already finished", flush=True)

fixed = pc._first_part
affected, kept, failed = [], [], []
for done, row in enumerate(rows, 1):
    path = Path(row["paper"])
    if not path.is_file():
        failed.append(row["name"])
        continue
    try:
        pc._first_part = lambda raw, column, found, tol: found
        before = starts(path)
        pc._first_part = fixed
        after = starts(path)
    except Exception as exc:
        pc._first_part = fixed
        failed.append(f"{row['name']}: {type(exc).__name__}")
        continue
    (affected if before != after else kept).append(row)
    if done % 25 == 0:
        print(f"  {done}/{len(rows)} checked, {len(affected)} affected", flush=True)

print(f"\naffected  : {len(affected)}")
print(f"still good: {len(kept)}")
if failed:
    print(f"could not check: {len(failed)}  {failed[:5]}")
for row in affected[:20]:
    print(f"   redo {row['name']}")

if not apply:
    print("\nreport only - pass --apply to delete those images and requeue them")
    raise SystemExit

removed = 0
for row in affected:
    for png in OUT.glob(f"{row['name']}_q*.png"):
        png.unlink()
        removed += 1
LOG.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept),
               encoding="utf-8")
print(f"\ndeleted {removed} images, {len(kept)} papers remain done")
