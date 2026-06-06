"""
Build bond_panel (instrument × date) and issuer_panel (issuer × quarter).

Rules enforced:
  - PIT ratings: each (instrument_id, date) gets the rating that was current on
    that exact date from ratings.csv — no anachronistic assignment.
  - Defaulted / dropped bonds: rows with all-NaN values after maturity / default
    are KEPT; survivorship filtering is left to the modelling step.
  - Duplicate CUSIPs (144A/Reg S): flagged with is_duplicate_cusip=True; not deduped.
  - TLD join: Ticker→MI KEY via mikey.csv; multi-match tickers resolved by
    preferring NYSE/NASDAQ-listed entity.
  - Sector trade volume: stored at bond level (same value for all bonds in sector).
  - No model training is performed here.

Outputs:
  data/interim/bond_panel.parquet
  data/interim/issuer_panel.parquet
  reports/coverage_report.md
"""
from __future__ import annotations

import calendar
import csv
import io
import re
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.config import (
    DATA_INTERIM,
    MIKEY_CSV,
    MIKEYS_SP_CSV,
    QOQ_BOND_DIR,
    QOQ_FUND_DIR,
    REPORTS,
    SP_RATING_SCALE,
)

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
BOND_PANEL_PARQUET    = DATA_INTERIM / "bond_panel.parquet"
ISSUER_PANEL_PARQUET  = DATA_INTERIM / "issuer_panel.parquet"
COVERAGE_REPORT_PATH  = REPORTS / "coverage_report.md"

# Metrics whose value of exactly 0 means "not yet issued / no data"
_ZERO_MASK_METRICS = frozenset({
    "z_spread_mid", "oas_mid", "ytm_mid", "ytw_mid",
    "mid_price", "modified_duration", "convexity", "macaulay_duration",
})

# QoQ bond CSV files → metric name  (ratings & info handled separately)
_BOND_METRIC_FILES: dict[str, str] = {
    "Z.csv":            "z_spread_mid",
    "OAS.csv":          "oas_mid",
    "modified.csv":     "modified_duration",
    "convexity.csv":    "convexity",
    "Macaulay.csv":     "macaulay_duration",
    "midprice.csv":     "mid_price",
    "yytm.csv":         "ytm_mid",
    "ytw%.csv":         "ytw_mid",
    "entitytrade.csv":  "entity_trade_vol",
    "sectortrade.csv":  "sector_trade_vol",
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _split(line: str) -> list[str]:
    return next(csv.reader(io.StringIO(line)))


def _to_float(raw: str) -> float:
    if not isinstance(raw, str):
        return np.nan
    s = raw.strip()
    if s in ("", "NA", "N/A", "—", "-", "NM"):
        return np.nan
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


_CQ_RE = re.compile(r"CQ(\d)(20\d{2})")


def _cq_to_period(col_name: str) -> Optional[str]:
    """'Total Transcript Level Score (Net Positivity|CQ12020)' → '2020Q1'"""
    m = _CQ_RE.search(str(col_name))
    if m:
        return f"{m.group(2)}Q{m.group(1)}"
    return None


def _quarter_end_date(period: str) -> Optional[pd.Timestamp]:
    """'2023Q2' → Timestamp('2023-06-30')"""
    m = re.match(r"(\d{4})Q(\d)", str(period))
    if not m:
        return None
    yr, q = int(m.group(1)), int(m.group(2))
    month = q * 3
    day = calendar.monthrange(yr, month)[1]
    return pd.Timestamp(yr, month, day)


# ---------------------------------------------------------------------------
# 1. Parse QoQ bond metric CSVs → wide bond panel
# ---------------------------------------------------------------------------

_DATE_COL_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def _parse_bond_metric_file(path: Path, metric_name: str) -> pd.DataFrame:
    """
    Parse one QoQ bond metric CSV → long DataFrame.

    Uses csv.reader (logical rows) instead of physical line indexing so that:
    - Files missing the sub-category row (entitytrade, sectortrade) parse correctly.
    - Files with embedded newlines in column names (ytw%) parse correctly.

    The dates row is auto-detected as the first logical row where column 5
    matches MM/DD/YYYY; all subsequent logical rows are treated as bond data.
    """
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        all_rows = list(csv.reader(fh))

    # Auto-detect dates row
    dates_row_idx: int | None = None
    for i, row in enumerate(all_rows):
        if len(row) > 5 and _DATE_COL_RE.match(row[5].strip()):
            dates_row_idx = i
            break

    if dates_row_idx is None:
        warnings.warn(f"Could not find dates row in {path.name} — skipping")
        return pd.DataFrame()

    dates = [
        pd.to_datetime(d.strip(), errors="coerce", dayfirst=False)
        for d in all_rows[dates_row_idx][5:]
    ]

    records = []
    for row in all_rows[dates_row_idx + 1:]:
        if not row or not row[0].strip():
            continue
        issuer_name   = row[0].strip()
        instrument_id = row[1].strip() if len(row) > 1 else ""
        mi_key        = row[2].strip() if len(row) > 2 else ""
        cusip         = row[3].strip() if len(row) > 3 else ""

        if not instrument_id:
            continue
        for i, dt in enumerate(dates):
            if pd.isna(dt):
                continue
            raw_val = row[i + 5].strip() if (i + 5) < len(row) else ""
            val = _to_float(raw_val)
            if metric_name in _ZERO_MASK_METRICS and val == 0.0:
                val = np.nan
            records.append({
                "instrument_id": instrument_id,
                "cusip":         cusip,
                "mi_key":        mi_key,
                "issuer_name":   issuer_name,
                "date":          dt,
                "metric":        metric_name,
                "value":         val,
            })
    return pd.DataFrame(records)


def parse_bond_metrics_wide(qoq_bond_dir: Path = QOQ_BOND_DIR) -> pd.DataFrame:
    """
    Parse all numeric bond metric CSVs → wide DataFrame.
    Returns one row per (instrument_id, date).
    """
    long_frames = []
    missing_files = []

    for fname, metric in _BOND_METRIC_FILES.items():
        path = qoq_bond_dir / fname
        if not path.exists():
            missing_files.append(fname)
            continue
        df = _parse_bond_metric_file(path, metric)
        long_frames.append(df)

    if missing_files:
        warnings.warn(f"Missing bond metric files: {missing_files}")

    long = pd.concat(long_frames, ignore_index=True)

    # Pivot to wide: (instrument_id, date) × metric
    wide = (
        long
        .pivot_table(
            index=["instrument_id", "cusip", "mi_key", "issuer_name", "date"],
            columns="metric",
            values="value",
            aggfunc="last",
        )
        .reset_index()
    )
    wide.columns.name = None

    # Normalise mi_key
    wide["mi_key"] = (
        pd.to_numeric(wide["mi_key"], errors="coerce")
        .astype("Int64").astype(str)
        .replace("<NA>", pd.NA)
    )
    return wide.sort_values(["instrument_id", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 2. Parse ratings.csv → PIT rating series
# ---------------------------------------------------------------------------

def parse_ratings_pit(ratings_path: Path) -> pd.DataFrame:
    """
    Parse ratings.csv → long DataFrame with one row per (instrument_id, date).

    PIT integrity: the rating stored at each date is the one that was current
    on that exact observation date — no look-ahead.
    """
    with open(ratings_path, encoding="utf-8-sig", errors="replace") as fh:
        all_rows = list(csv.reader(fh))

    dates_row_idx: int | None = None
    for i, row in enumerate(all_rows):
        if len(row) > 5 and _DATE_COL_RE.match(row[5].strip()):
            dates_row_idx = i
            break

    if dates_row_idx is None:
        warnings.warn("Could not find dates row in ratings.csv")
        return pd.DataFrame()

    dates = [
        pd.to_datetime(d.strip(), errors="coerce", dayfirst=False)
        for d in all_rows[dates_row_idx][5:]
    ]

    records = []
    for row in all_rows[dates_row_idx + 1:]:
        if not row or not row[0].strip():
            continue
        instrument_id = row[1].strip() if len(row) > 1 else ""
        if not instrument_id:
            continue
        for i, dt in enumerate(dates):
            if pd.isna(dt):
                continue
            raw_rating = row[i + 5].strip() if (i + 5) < len(row) else ""
            rating_str = raw_rating if raw_rating and raw_rating not in ("", "NA", "N/A") else pd.NA
            rating_num = float(SP_RATING_SCALE.get(str(rating_str), np.nan)) if pd.notna(rating_str) else np.nan
            records.append({
                "instrument_id":     instrument_id,
                "date":              dt,
                "sp_rating":         rating_str,
                "sp_rating_numeric": rating_num,
            })
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# 3. Parse info.csv → static bond attributes
# ---------------------------------------------------------------------------

def parse_bond_info_static(info_path: Path) -> pd.DataFrame:
    """
    Parse info.csv → one row per instrument_id with static attributes.

    File has an unusual header: columns 5–11 have embedded newlines in their
    names (e.g. 'Callable?\\nYes/No'). We parse using csv.reader to handle
    quoted multi-line cells, skip the 5 metadata rows, then take data rows.
    """
    with open(info_path, encoding="utf-8-sig", errors="replace") as f:
        content = f.read()

    rows = list(csv.reader(io.StringIO(content)))
    # rows[0] = SPGTable
    # rows[1] = column headers (embedded newlines resolved by csv.reader)
    # rows[2] = SPT field codes
    # rows[3] = sub-category
    # rows[4] = dates
    # rows[5+] = data

    _INFO_COLS = [
        "issuer_name", "instrument_id", "mi_key", "cusip", "description",
        "callable", "next_call_date", "first_callable_payment_date",
        "seniority_level", "debt_type_detail", "maturity_date", "maturity_type",
    ]

    records = []
    n_dropped = 0
    for row in rows[5:]:
        if not row or not row[0].strip():
            continue
        if len(row) < 6:
            n_dropped += 1
            continue
        r = {col: (row[i].strip() if i < len(row) else "") for i, col in enumerate(_INFO_COLS)}
        records.append(r)

    df = pd.DataFrame(records)
    if n_dropped:
        warnings.warn(f"info.csv: dropped {n_dropped} rows (< 6 columns)")

    # Parse dates
    for date_col in ["next_call_date", "first_callable_payment_date", "maturity_date"]:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=False)

    df["mi_key"] = (
        pd.to_numeric(df["mi_key"], errors="coerce")
        .astype("Int64").astype(str)
        .replace("<NA>", pd.NA)
    )
    return df.drop_duplicates("instrument_id").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4. Build bond_panel: merge metrics + ratings + static info + duplicate flag
# ---------------------------------------------------------------------------

def build_bond_panel(qoq_bond_dir: Path = QOQ_BOND_DIR) -> tuple[pd.DataFrame, dict]:
    """
    Build the full bond_panel and return (df, audit_log).
    audit_log contains counts for the coverage report.
    """
    log: dict = {}

    print("  Parsing numeric bond metrics…")
    wide = parse_bond_metrics_wide(qoq_bond_dir)
    log["total_obs"]    = len(wide)
    log["unique_bonds"] = wide["instrument_id"].nunique()
    log["unique_dates"] = wide["date"].nunique()
    log["date_range"]   = (wide["date"].min().date(), wide["date"].max().date())

    # PIT ratings
    ratings_path = qoq_bond_dir / "ratings.csv"
    if ratings_path.exists():
        print("  Parsing ratings (PIT)…")
        ratings = parse_ratings_pit(ratings_path)
        wide = wide.merge(ratings, on=["instrument_id", "date"], how="left")
        log["ratings_coverage_pct"] = (
            wide["sp_rating"].notna().sum() / len(wide) * 100
        )
    else:
        warnings.warn("ratings.csv not found — sp_rating columns will be absent")
        log["ratings_coverage_pct"] = 0.0

    # Static bond info
    info_path = qoq_bond_dir / "info.csv"
    if info_path.exists():
        print("  Parsing bond static info…")
        info = parse_bond_info_static(info_path)
        info_cols = ["instrument_id", "callable", "seniority_level",
                     "debt_type_detail", "maturity_date", "maturity_type",
                     "next_call_date"]
        wide = wide.merge(info[info_cols], on="instrument_id", how="left")
    else:
        warnings.warn("info.csv not found — static bond attributes absent")

    # Duplicate CUSIP flag
    cusip_instrument_counts = (
        wide[wide["cusip"].notna() & (wide["cusip"] != "")]
        .groupby("cusip")["instrument_id"]
        .nunique()
    )
    dup_cusips = set(cusip_instrument_counts[cusip_instrument_counts > 1].index)
    wide["is_duplicate_cusip"] = wide["cusip"].isin(dup_cusips)
    log["duplicate_cusip_count"] = len(dup_cusips)
    log["duplicate_cusip_list"]  = sorted(dup_cusips)

    # bond_active: True only if the bond has a valid spread on this date.
    # trade volume is always populated so cannot be used here.
    _SPREAD_COLS = ["z_spread_mid", "oas_mid", "ytm_mid"]
    spread_cols_present = [c for c in _SPREAD_COLS if c in wide.columns]
    wide["bond_active"] = wide[spread_cols_present].notna().any(axis=1)

    # yield_for_irr: YTW where callable and available, else YTM; flag the source
    if "ytw_mid" in wide.columns and "ytm_mid" in wide.columns:
        callable_yes = wide.get("callable", pd.Series(dtype=str)).str.upper() == "YES"
        ytw_available = wide["ytw_mid"].notna()
        wide["yield_for_irr"] = wide["ytm_mid"].copy()                     # default: YTM
        wide["yield_source"]  = "YTM"
        # Callable + YTW present → use YTW
        wide.loc[callable_yes & ytw_available, "yield_for_irr"] = wide.loc[
            callable_yes & ytw_available, "ytw_mid"
        ]
        wide.loc[callable_yes & ytw_available, "yield_source"] = "YTW"
        # Callable + YTW missing → YTM fallback, flag it
        wide.loc[callable_yes & ~ytw_available, "yield_source"] = "YTM_fallback"

    # Null rates per metric column
    metric_cols = [c for c in _BOND_METRIC_FILES.values() if c in wide.columns]
    log["null_rates"] = {
        col: round(wide[col].isna().mean() * 100, 1)
        for col in metric_cols
    }

    DATA_INTERIM.mkdir(parents=True, exist_ok=True)
    wide.to_parquet(BOND_PANEL_PARQUET, index=False)
    print(f"  bond_panel.parquet: {len(wide):,} rows × {wide.shape[1]} cols")
    return wide, log


# ---------------------------------------------------------------------------
# 5. Parse TLD sentiment scores → long format
# ---------------------------------------------------------------------------

def parse_tld_long(tld_path: Path) -> pd.DataFrame:
    """
    Parse tld.csv → long DataFrame with columns:
      ticker, entity_name, sector, industry, period, tld_score, period_end_date
    """
    df = pd.read_csv(tld_path, dtype=str, encoding="utf-8-sig")
    # Strip all column names (they have trailing spaces in the export)
    df.columns = df.columns.str.strip()

    # After stripping, column names are: 'Ticker', 'Entity Name', 'Sector', 'Industry', ...
    score_cols = [c for c in df.columns if "|CQ" in c]

    # Identify available id columns by their stripped names
    _WANTED_IDS = ["Ticker", "Entity Name", "Sector", "Industry"]
    id_cols = [c for c in _WANTED_IDS if c in df.columns]

    df_long = df[id_cols + score_cols].melt(
        id_vars=id_cols,
        value_vars=score_cols,
        var_name="col_name",
        value_name="tld_score_raw",
    )

    df_long["period"]    = df_long["col_name"].apply(_cq_to_period)
    df_long["tld_score"] = pd.to_numeric(df_long["tld_score_raw"], errors="coerce")
    df_long = df_long.dropna(subset=["period"])
    df_long["period_end_date"] = df_long["period"].apply(_quarter_end_date)

    # Normalise to lowercase column names
    rename = {
        "Ticker":      "ticker",
        "Entity Name": "entity_name",
        "Sector":      "sector",
        "Industry":    "industry",
    }
    df_long = df_long.rename(columns={k: v for k, v in rename.items() if k in df_long.columns})
    for c in ["ticker", "entity_name", "sector", "industry"]:
        if c in df_long.columns:
            df_long[c] = df_long[c].str.strip()

    out_cols = [c for c in ["ticker", "entity_name", "sector", "industry",
                             "period", "period_end_date", "tld_score"]
                if c in df_long.columns]
    return df_long[out_cols].copy()


# ---------------------------------------------------------------------------
# 6. Build Ticker → MI KEY crosswalk from mikey.csv
# ---------------------------------------------------------------------------

_EXCHANGE_SUFFIX_RE  = re.compile(r"\s*\([A-Z]{1,10}:[^)]+\)\s*$")
_LEGAL_SUFFIX_RE     = re.compile(
    r"\b(Inc\.?|LLC\.?|Corp\.?|Corporation|Company|Limited|LP|L\.P\.|"
    r"L\.L\.C\.|PLC|plc|N\.A\.)\b", re.I
)


def _norm_name(s: str) -> str:
    """Normalise an entity name for fuzzy matching (strip exchange tag + legal suffixes)."""
    s = _EXCHANGE_SUFFIX_RE.sub("", str(s).strip())
    s = _LEGAL_SUFFIX_RE.sub("", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.lower().split())


def build_ticker_mikey_map(
    mikeys_sp_csv: Path = MIKEYS_SP_CSV,
) -> tuple[dict[str, str], dict[str, str]]:
    """
    Read SP data/MIkeys.csv → two lookup dicts:
      ticker_map  — {ticker: mi_key}        exact ticker match
      entity_map  — {norm_entity: mi_key}   fallback entity-name match

    File has a 4-row header:
      row 0: SPGTable
      row 1: Issuer Name / MI KEY
      row 2: SPT_ field identifiers
      row 3: actual column headers (Ticker, Entity Name, …, MI KEY)
    Data starts at row 4.
    """
    raw = pd.read_csv(
        mikeys_sp_csv,
        skiprows=4,
        header=None,
        names=["ticker", "entity_name", "last_time",
               "industry_class", "sector", "industry", "mi_key"],
        dtype=str,
        encoding="utf-8-sig",
    )

    raw["ticker"]      = raw["ticker"].fillna("").str.strip()
    raw["entity_name"] = raw["entity_name"].fillna("").str.strip()
    raw["mi_key"]      = raw["mi_key"].fillna("").str.strip()

    # Drop footer / disclaimer rows (mi_key must be a pure integer string)
    raw = raw[raw["mi_key"].str.match(r"^\d+$", na=False)].copy()

    # Ticker map: exact match, prefer US-listed when ticker is ambiguous
    raw["is_us"] = raw["entity_name"].str.contains(
        r"\(NYSE|\(NASDAQ", regex=True, na=False
    )
    raw = raw.sort_values(["ticker", "is_us"], ascending=[True, False])

    valid = raw[raw["ticker"].str.len() >= 1]
    ticker_map = dict(
        zip(valid.drop_duplicates("ticker", keep="first")["ticker"],
            valid.drop_duplicates("ticker", keep="first")["mi_key"])
    )

    # Entity-name fallback map
    raw["norm_name"] = raw["entity_name"].apply(_norm_name)
    ent = raw[raw["norm_name"].str.len() > 2].drop_duplicates("norm_name", keep="first")
    entity_map = dict(zip(ent["norm_name"], ent["mi_key"]))

    return ticker_map, entity_map


# ---------------------------------------------------------------------------
# 7. Build issuer_panel: fundamentals + TLD
# ---------------------------------------------------------------------------

def build_issuer_panel(
    qoq_fund_dir: Path = QOQ_FUND_DIR,
    tld_path: Optional[Path] = None,
    mikey_csv_path: Path = MIKEYS_SP_CSV,
) -> tuple[pd.DataFrame, dict]:
    """
    Build issuer_panel (mi_key × period) from fundamentals + TLD sentiment.
    Returns (df, audit_log).
    """
    from src.parse_capital_iq import _parse_financial_highlights_file

    log: dict = {}

    print("  Parsing quarterly fundamentals…")
    all_long = []
    for p in sorted(qoq_fund_dir.glob("FinancialHighlights_*.csv")):
        all_long.append(_parse_financial_highlights_file(p))

    fund_long = pd.concat(all_long, ignore_index=True)
    fund_long = fund_long[fund_long["mi_key"].notna() & fund_long["filing_date"].notna()]

    # Deduplicate: prefer latest filing per (mi_key, period, metric)
    fund_long = (
        fund_long
        .sort_values("filing_date")
        .drop_duplicates(subset=["mi_key", "period", "metric"], keep="last")
    )

    # Pivot to wide
    wide = fund_long.pivot_table(
        index=["mi_key", "period"],
        columns="metric",
        values="value",
        aggfunc="last",
    ).reset_index()
    wide.columns.name = None

    # Attach period_end_date and filing_date (latest per period)
    dates = (
        fund_long.groupby(["mi_key", "period"])
        .agg(period_end_date=("period_end_date", "max"),
             filing_date=("filing_date", "max"))
        .reset_index()
    )
    wide = wide.merge(dates, on=["mi_key", "period"], how="left")

    log["issuer_count"]  = wide["mi_key"].nunique()
    log["period_count"]  = wide["period"].nunique()
    log["period_range"]  = (
        sorted(wide["period"].dropna().unique())[0],
        sorted(wide["period"].dropna().unique())[-1],
    )

    # TLD sentiment join
    tld_path = tld_path or (QOQ_BOND_DIR / "tld.csv")
    unjoinable_tickers: list[str] = []
    if tld_path.exists():
        print("  Parsing TLD sentiment…")
        tld = parse_tld_long(tld_path)
        ticker_map, entity_map = build_ticker_mikey_map(mikey_csv_path)

        # Stage 1: exact ticker match
        tld["mi_key"] = tld["ticker"].map(ticker_map)

        # Stage 2: entity-name fallback for rows that didn't match by ticker
        if "entity_name" in tld.columns:
            unmatched = tld["mi_key"].isna()
            tld.loc[unmatched, "mi_key"] = (
                tld.loc[unmatched, "entity_name"]
                .apply(_norm_name)
                .map(entity_map)
            )

        matched_by_ticker = tld["ticker"].map(ticker_map).notna().sum()
        matched_total     = tld["mi_key"].notna().sum()
        matched_by_entity = matched_total - matched_by_ticker

        unjoinable = (
            tld[tld["mi_key"].isna()]["ticker"].dropna().unique().tolist()
        )
        unjoinable_tickers = sorted(set(unjoinable))

        log["tld_total_tickers"]       = tld["ticker"].nunique()
        log["tld_joined_tickers"]      = matched_total // max(tld["period"].nunique(), 1)
        log["tld_matched_by_ticker"]   = matched_by_ticker // max(tld["period"].nunique(), 1)
        log["tld_matched_by_entity"]   = matched_by_entity // max(tld["period"].nunique(), 1)
        log["tld_unjoinable_tickers"]  = unjoinable_tickers
        print(
            f"    TLD: {log['tld_joined_tickers']} issuers matched "
            f"({log['tld_matched_by_ticker']} by ticker, "
            f"{log['tld_matched_by_entity']} by entity name)"
        )

        tld_join = (
            tld[tld["mi_key"].notna()]
            .groupby(["mi_key", "period"])["tld_score"]
            .mean()
            .reset_index()
        )
        wide = wide.merge(tld_join, on=["mi_key", "period"], how="left")
        log["issuer_with_tld_pct"] = round(
            wide["tld_score"].notna().sum() / len(wide) * 100, 1
        )
    else:
        warnings.warn("tld.csv not found — tld_score column will be absent")
        unjoinable_tickers = []
        log["tld_unjoinable_tickers"] = []

    # Null rates for key credit metrics
    key_metrics = [
        "Total Debt / Total Capital (%)", "EBIT / Interest Expense (x)",
        "EBIT Margin", "Net Income Margin", "Return on Assets",
        "Cash from Ops.", "Total Debt", "Total Assets", "Net Debt",
        "Total Revenue", "EBIT",
    ]
    log["fundamental_null_rates"] = {
        m: round(wide[m].isna().mean() * 100, 1) if m in wide.columns else 100.0
        for m in key_metrics
    }

    DATA_INTERIM.mkdir(parents=True, exist_ok=True)
    wide.to_parquet(ISSUER_PANEL_PARQUET, index=False)
    n_cols = wide.shape[1]
    print(f"  issuer_panel.parquet: {len(wide):,} rows × {n_cols} cols")
    return wide, log, unjoinable_tickers


# ---------------------------------------------------------------------------
# 8. Coverage report
# ---------------------------------------------------------------------------

def write_coverage_report(
    bond_panel:         pd.DataFrame,
    bond_log:           dict,
    issuer_panel:       pd.DataFrame,
    issuer_log:         dict,
    unjoinable_tickers: list[str],
) -> None:
    from datetime import date

    today = date.today().isoformat()

    # Duplicate CUSIP table
    dup_rows = ""
    if bond_log.get("duplicate_cusip_list"):
        dup_table_rows = []
        for cusip in bond_log["duplicate_cusip_list"]:
            instr_ids = (
                bond_panel[bond_panel["cusip"] == cusip]["instrument_id"]
                .drop_duplicates()
                .tolist()
            )
            dup_table_rows.append(f"| {cusip} | {', '.join(instr_ids)} |")
        dup_rows = "\n".join(dup_table_rows)
    else:
        dup_rows = "| — | — |"

    # Bond panel null-rate table
    null_rows = "\n".join(
        f"| {col} | {pct:.1f}% |"
        for col, pct in sorted(bond_log.get("null_rates", {}).items())
    )

    # Fundamental null-rate table
    fund_null_rows = "\n".join(
        f"| {m} | {pct:.1f}% |"
        for m, pct in issuer_log.get("fundamental_null_rates", {}).items()
    )

    # Unjoinable tickers
    if unjoinable_tickers:
        unjoin_block = "\n".join(f"- `{t}`" for t in unjoinable_tickers)
    else:
        unjoin_block = "_All tickers joined successfully._"

    # Sample rows: head + tail of bond_panel
    bp_cols = ["instrument_id", "cusip", "mi_key", "issuer_name", "date",
               "z_spread_mid", "oas_mid", "sp_rating", "sp_rating_numeric",
               "seniority_level", "is_duplicate_cusip", "bond_active"]
    bp_cols = [c for c in bp_cols if c in bond_panel.columns]
    sample_bp = pd.concat([bond_panel[bp_cols].head(5),
                            bond_panel[bp_cols].tail(5)])
    sample_bp_md = sample_bp.to_markdown(index=False)

    # Sample rows: issuer_panel
    ip_cols = ["mi_key", "period", "period_end_date", "filing_date",
               "Total Debt / Total Capital (%)", "EBIT / Interest Expense (x)",
               "EBIT Margin", "tld_score"]
    ip_cols = [c for c in ip_cols if c in issuer_panel.columns]
    sample_ip = pd.concat([issuer_panel[ip_cols].head(5),
                            issuer_panel[ip_cols].tail(5)])
    sample_ip_md = sample_ip.to_markdown(index=False)

    report = f"""# Bond Panel Coverage Report

**Generated**: {today}

---

## 1. Bond Panel (`bond_panel.parquet`)

| Item | Value |
|------|-------|
| Total observations (bond × date rows) | {bond_log['total_obs']:,} |
| Unique instruments (bonds) | {bond_log['unique_bonds']:,} |
| Unique observation dates | {bond_log['unique_dates']} |
| Date range | {bond_log['date_range'][0]} → {bond_log['date_range'][1]} |
| Bonds with valid rating coverage | {bond_log.get('ratings_coverage_pct', 0):.1f}% of rows |
| Duplicate-CUSIP bonds flagged | {bond_log.get('duplicate_cusip_count', 0)} CUSIPs |

### Null rates by metric column

| Metric | Null % |
|--------|--------|
{null_rows}

### Sample rows (head 5 + tail 5)

{sample_bp_md}

---

## 2. Duplicate CUSIPs (144A / Reg S tranches)

| CUSIP | Instrument IDs |
|-------|----------------|
{dup_rows}

---

## 3. Issuer Panel (`issuer_panel.parquet`)

| Item | Value |
|------|-------|
| Unique issuers (MI KEY) | {issuer_log['issuer_count']:,} |
| Unique periods | {issuer_log['period_count']} |
| Period range | {issuer_log['period_range'][0]} → {issuer_log['period_range'][1]} |
| TLD issuers matched (total) | {issuer_log.get('tld_joined_tickers', 'N/A')} |
| — matched by ticker | {issuer_log.get('tld_matched_by_ticker', 'N/A')} |
| — matched by entity name | {issuer_log.get('tld_matched_by_entity', 'N/A')} |
| Issuer-periods with TLD score | {issuer_log.get('issuer_with_tld_pct', 0):.1f}% |

### Fundamental metric null rates (key credit metrics)

| Metric | Null % |
|--------|--------|
{fund_null_rows}

### Sample rows (head 5 + tail 5)

{sample_ip_md}

---

## 4. TLD Unjoinable Tickers

Tickers present in `tld.csv` that could not be matched to a MI KEY via `mikey.csv`:

{unjoin_block}

---

## 5. Notes for Model Step

- **PIT ratings**: each bond × date row carries the rating that was current
  on that exact date; no look-ahead.
- **Pre-issuance zeros**: replaced with NaN for spread/price/duration metrics;
  rows are kept (non-survivor-biased panel).
- **Duplicate CUSIPs**: flagged with `is_duplicate_cusip`; NOT removed.
  Modelling step should decide how to handle.
- **as-of join**: bond_panel and issuer_panel share `mi_key` but have
  different time axes (daily/monthly vs quarterly). Use
  `pd.merge_asof(direction='backward')` on `date` vs `filing_date` when
  attaching issuer fundamentals to bond observations.
- **TLD alignment**: `tld_score` is stored at quarter-end. Treat it as
  known from the transcript publication date (typically mid-quarter + ~2 weeks).
  Apply backward as-of join when attaching to bond observations.
"""

    REPORTS.mkdir(parents=True, exist_ok=True)
    COVERAGE_REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"  coverage_report.md written -> {COVERAGE_REPORT_PATH}")


# ---------------------------------------------------------------------------
# 9. Entry point
# ---------------------------------------------------------------------------

def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build both panels and generate coverage report. Returns (bond_panel, issuer_panel)."""
    print("=" * 60)
    print("STEP 1: Bond panel (instrument × date)")
    print("=" * 60)
    bond_panel, bond_log = build_bond_panel()

    print()
    print("=" * 60)
    print("STEP 2: Issuer panel (issuer × quarter)")
    print("=" * 60)
    issuer_panel, issuer_log, unjoinable = build_issuer_panel()

    print()
    print("=" * 60)
    print("STEP 3: Coverage report")
    print("=" * 60)
    write_coverage_report(bond_panel, bond_log, issuer_panel, issuer_log, unjoinable)

    return bond_panel, issuer_panel


if __name__ == "__main__":
    run()
