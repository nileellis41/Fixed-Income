import csv, re
from pathlib import Path

path = Path("SP data/qoqbonddata/ytw%.csv")
DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

with open(path, encoding="utf-8-sig", errors="replace") as fh:
    rows = list(csv.reader(fh))

print(f"Total logical rows: {len(rows)}")
for i, row in enumerate(rows[:10]):
    c0 = repr(row[0][:50]) if row else ""
    c5 = repr(row[5][:30]) if len(row) > 5 else "MISSING"
    c5_match = DATE_RE.match(row[5].strip()) if len(row) > 5 else None
    print(f"  row[{i:2d}]  ncols={len(row):3d}  col0={c0}  col5={c5}  date_match={bool(c5_match)}")
