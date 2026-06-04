"""Diagnostics for the three coverage blockers."""
import warnings; warnings.filterwarnings("ignore")
import csv, io
import numpy as np
import pandas as pd
from pathlib import Path

QOQ = Path(r"C:\Users\nilee\OneDrive\Desktop\NYU\Bond Project\SP data\qoqbonddata")

# ── 1. File existence + size ─────────────────────────────────────────────────
print("=== File inventory ===")
for fname in ["ytw%.csv", "entitytrade.csv", "sectortrade.csv"]:
    p = QOQ / fname
    print(f"  {fname:22s}  exists={p.exists()}  size={p.stat().st_size if p.exists() else 'N/A'}")

# ── 2. Try parsing ytw%.csv rows directly ────────────────────────────────────
print("\n=== ytw%.csv parse test ===")
ytw_path = QOQ / "ytw%.csv"
if ytw_path.exists():
    lines = open(ytw_path, encoding="utf-8-sig", errors="replace").readlines()
    print(f"  Physical lines: {len(lines)}")
    def _split(line):
        return next(csv.reader(io.StringIO(line)))
    dates = _split(lines[4])
    print(f"  Date columns (first 5): {dates[5:10]}")
    data_rows = [_split(l) for l in lines[5:] if _split(l) and _split(l)[0].strip()]
    print(f"  Data rows: {len(data_rows)}")
    if data_rows:
        r = data_rows[0]
        print(f"  Row 0 issuer: {r[0][:40]}")
        print(f"  Row 0 values[5:10]: {r[5:10]}")
else:
    print("  FILE NOT FOUND")

# ── 3. Try parsing entitytrade.csv ───────────────────────────────────────────
print("\n=== entitytrade.csv parse test ===")
et_path = QOQ / "entitytrade.csv"
if et_path.exists():
    lines = open(et_path, encoding="utf-8-sig", errors="replace").readlines()
    data_rows = [_split(l) for l in lines[5:] if _split(l) and _split(l)[0].strip()]
    print(f"  Data rows: {len(data_rows)}")
    if data_rows:
        r = data_rows[0]
        print(f"  Row 0 issuer: {r[0][:40]}")
        print(f"  Row 0 values[5:8]: {r[5:8]}")
    # Test _to_float on a real value
    raw = r[5] if data_rows else ""
    s = raw.strip().replace(",", "")
    try:
        val = float(s)
        print(f"  _to_float('{raw[:30]}') = {val:.0f}")
    except Exception as e:
        print(f"  _to_float failed: {e}")

# ── 4. Inspect current bond_panel columns ────────────────────────────────────
print("\n=== Current bond_panel columns ===")
bp = pd.read_parquet(r"C:\Users\nilee\OneDrive\Desktop\NYU\Bond Project\data\interim\bond_panel.parquet")
print(f"  Shape: {bp.shape}")
print(f"  Columns: {list(bp.columns)}")

# ── 5. OAS coverage by rating bucket ────────────────────────────────────────
print("\n=== OAS coverage by rating bucket ===")
def rating_bucket(r):
    if pd.isna(r): return "NR"
    r = float(r)
    if r <= 10: return "IG (AAA-BBB-)"
    elif r <= 16: return "HY (BB+-B-)"
    else: return "Distressed (CCC+)"

bp["bucket"] = bp["sp_rating_numeric"].apply(rating_bucket)
for bucket, grp in bp.groupby("bucket"):
    oas_pct = grp["oas_mid"].notna().mean() * 100
    z_pct   = grp["z_spread_mid"].notna().mean() * 100
    n_bonds = grp["instrument_id"].nunique()
    print(f"  {bucket:22s}  bonds={n_bonds:3d}  OAS={oas_pct:5.1f}%  Z-spread={z_pct:5.1f}%")

# ── 6. Universe shrink analysis ──────────────────────────────────────────────
print("\n=== Universe vs Phase 2 ===")
print(f"  bond_panel bonds  : {bp['instrument_id'].nunique()}")
print(f"  bond_panel issuers: {bp['mi_key'].nunique()}")
# Load Phase 2 spread OOF residuals for comparison
oof = pd.read_csv(r"C:\Users\nilee\OneDrive\Desktop\NYU\Bond Project\reports\spread_oof_residuals.csv")
print(f"  Phase 2 bonds     : {oof['instrument_id'].nunique() if 'instrument_id' in oof.columns else 'N/A'}")
print(f"  Phase 2 issuers   : {oof['mi_key'].nunique() if 'mi_key' in oof.columns else 'N/A'}")

# ── 7. Date cadence ──────────────────────────────────────────────────────────
print("\n=== Date cadence ===")
dates = sorted(bp["date"].dropna().unique())
print(f"  Total dates: {len(dates)}")
print(f"  Earliest: {dates[0].date()}  Latest: {dates[-1].date()}")
monthly_cutoff = pd.Timestamp("2024-10-01")
monthly_dates  = [d for d in dates if d >= monthly_cutoff]
quarterly_dates = [d for d in dates if d < monthly_cutoff]
print(f"  Monthly (>= Oct 2024)  : {len(monthly_dates)} dates")
print(f"  Quarterly (< Oct 2024) : {len(quarterly_dates)} dates")
