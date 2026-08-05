"""
What each kind of paper looks like.

A syllabus sets the same paper every session, so 9702 Paper 5 always asks
two questions and 9700 Paper 4 always asks ten. Knowing that turns a
question the tool cannot find into a question it knows must be there, and
turns a number it wrongly found into one it knows cannot exist.

The figures are not guessed. They are counted from the papers that came
through every check and agreed with their own mark scheme, and each
carries the share of that family it accounts for - because some families
genuinely vary. 9701 Paper 4 runs anywhere from six questions to ten, so
nothing can be assumed there, while 9702 Paper 5 is two every time.

    py families.py            (show the table)
    py families.py --rebuild  (count it again from the clean set)
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(r"D:\Papers\output questions and markschemes")
HERE = Path(__file__).resolve().parent
TABLE = HERE / "paper families.json"

_NAME = re.compile(r"^(\d{4})_([a-z]\d{2})_(qp|ms)_(\d+)$", re.I)

#: Below this share the family varies too much to assume anything.
SURE = 0.90

#: How many papers a family needs before its shape means anything.
ENOUGH = 12


def family_of(name: str) -> str | None:
    """Which family a paper belongs to, as "9702_5" - syllabus and paper."""
    m = _NAME.match(name)
    return f"{m.group(1)}_{m.group(4)[0]}" if m else None


def load() -> dict:
    if TABLE.is_file():
        return json.loads(TABLE.read_text(encoding="utf-8"))
    return {}


def expected(name: str, table: dict | None = None) -> tuple[int, float] | None:
    """
    How many questions this paper should hold, and how sure that is.

    None where the family varies, or where too few of it are known.
    """
    table = load() if table is None else table
    row = table.get(family_of(name) or "")
    if not row:
        return None
    return row["questions"], row["share"]


def rebuild(out: Path) -> dict:
    """Count the shape of each family from the papers that passed everything."""
    seen: dict[tuple, dict[str, set]] = defaultdict(dict)
    for folder in ("questions_clean", "markschemes_clean"):
        for png in (out / folder).glob("*.png"):
            m = _NAME.match(png.stem.rsplit("_q", 1)[0])
            if m:
                key = (m.group(1), m.group(2), m.group(4))
                seen[key].setdefault(m.group(3).lower(), set()).add(
                    int(png.stem.rsplit("_q", 1)[1]))

    counts: dict[str, Counter] = defaultdict(Counter)
    for key, sides in seen.items():
        # Only a paper whose two sides agree can say what the family looks like.
        if len(sides) == 2 and sides["qp"] == sides["ms"]:
            counts[f"{key[0]}_{key[2][0]}"][len(sides["qp"])] += 1

    table = {}
    for family, tally in sorted(counts.items()):
        total = sum(tally.values())
        number, hits = tally.most_common(1)[0]
        table[family] = {
            "questions": number,
            "share": round(hits / total, 3),
            "papers": total,
            "seen": dict(sorted(tally.items())),
            "certain": bool(hits / total >= SURE and total >= ENOUGH),
        }
    return table


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="What each kind of paper looks like.")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--rebuild", action="store_true")
    a = p.parse_args(argv)

    table = rebuild(Path(a.out)) if a.rebuild else load()
    if a.rebuild:
        TABLE.write_text(json.dumps(table, indent=1), encoding="utf-8")

    print(f"{'family':<12}{'papers':>7}{'questions':>11}{'share':>8}   {'certain':<9}seen")
    for family, row in sorted(table.items()):
        mark = "yes" if row["certain"] else "varies"
        print(f"{family:<12}{row['papers']:>7}{row['questions']:>11}"
              f"{row['share']*100:>7.0f}%   {mark:<9}{row['seen']}")
    certain = sum(1 for r in table.values() if r["certain"])
    print(f"\n{certain} of {len(table)} families have a shape that can be relied on")
    if a.rebuild:
        print(f"written {TABLE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
