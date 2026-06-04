"""
Feature engineering.

Key invariants (enforced by tests):
  - PIT joins use filing_date, never period_end_date.
  - Trajectory features return NaN when prior periods are absent; never extrapolate.
  - Fundamentals stale by more than MAX_STALENESS_QUARTERS are dropped.
  - Missing fundamentals: issuer-specific forward-fill up to staleness limit, then drop.
"""
from __future__ import annotations

import calendar
import re
from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd

from src.config import (
    DATA_PROCESSED,
    FEATURES_DOWNGRADES,
    FEATURES_SPREADS,
    FUNDAMENTALS_PARQUET,
    IG_CUTOFF_NUMERIC,
    MAX_STALENESS_QUARTERS,
    QOQ_BOND_PANEL_PARQUET,
    RATING_NA_STRINGS,
    SP_RATING_SCALE,
)

# ---------------------------------------------------------------------------
# Rating helpers
# ---------------------------------------------------------------------------

def rating_to_numeric(rating: Optional[str]) -> Optional[float]:
    if not isinstance(rating, str) or rating.strip() in RATING_NA_STRINGS:
        return np.nan
    return float(SP_RATING_SCALE.get(rating.strip(), np.nan))


# ---------------------------------------------------------------------------
# 1. PIT join — CRITICAL: use filing_date, not period_end_date
# ---------------------------------------------------------------------------

def pit_join_fundamentals(
    bonds_df: pd.DataFrame,
    fundamentals_long: pd.DataFrame,
) -> pd.DataFrame:
    """
    For each bond observation on as_of_date, attach the most recent
    fundamentals where filing_date <= as_of_date.

    Uses filing_date (the date S&P received/published the filing),
    NOT period_end_date (which is the quarter-end and would introduce
    look-ahead bias of up to 3 months).

    Returns wide-format DataFrame: one row per bond, fundamentals as columns.
    """
    # Pivot long → wide per (mi_key, filing_date)
    # For each mi_key, keep the snapshot with the latest filing_date <= as_of_date
    fund = fundamentals_long.copy()
    fund = fund[fund["mi_key"].notna() & fund["filing_date"].notna()]
    fund["mi_key"] = fund["mi_key"].astype(str)

    # Keep only the latest filing per (mi_key, period, metric) — already deduped in parser
    # Now find, per mi_key, the latest period whose filing_date <= as_of_date
    as_of = pd.Timestamp(bonds_df["as_of_date"].iloc[0])

    eligible = fund[fund["filing_date"] <= as_of].copy()
    # For each mi_key, pick the period with the max filing_date
    latest_period = (
        eligible.sort_values("filing_date")
        .drop_duplicates(subset=["mi_key", "metric"], keep="last")
    )

    # Pivot to wide
    wide = latest_period.pivot_table(
        index="mi_key", columns="metric", values="value", aggfunc="last"
    )
    wide.columns.name = None
    wide = wide.reset_index()

    # Merge onto bonds
    bonds = bonds_df.copy()
    bonds["mi_key"] = bonds["mi_key"].astype(str)
    merged = bonds.merge(wide, on="mi_key", how="left")
    return merged


# ---------------------------------------------------------------------------
# 2. Trajectory features — computed from the full historical panel
# ---------------------------------------------------------------------------

def _pivot_period_wide(fundamentals_long: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot long fundamentals to wide: rows = (mi_key, period), cols = metrics.
    Includes period_end_date and filing_date for staleness checks.
    """
    fund = fundamentals_long.copy()
    fund["mi_key"] = fund["mi_key"].astype(str)

    wide = fund.pivot_table(
        index=["mi_key", "period"],
        columns="metric",
        values="value",
        aggfunc="last",
    )
    wide.columns.name = None
    wide = wide.reset_index()

    # Attach the latest filing_date per (mi_key, period)
    fd = (
        fund.groupby(["mi_key", "period"])["filing_date"]
        .max()
        .reset_index()
        .rename(columns={"filing_date": "filing_date"})
    )
    pe = (
        fund.groupby(["mi_key", "period"])["period_end_date"]
        .max()
        .reset_index()
    )
    wide = wide.merge(fd, on=["mi_key", "period"], how="left")
    wide = wide.merge(pe, on=["mi_key", "period"], how="left")
    return wide


def _gen_period_order(
    start_year: int = 2020, start_q: int = 1,
    end_year:   int = 2026, end_q:   int = 1,
) -> list[str]:
    """Generate ordered list of quarterly periods, e.g. ['2020Q1', '2020Q2', ...]."""
    periods: list[str] = []
    year, q = start_year, start_q
    while (year, q) <= (end_year, end_q):
        periods.append(f"{year}Q{q}")
        q += 1
        if q > 4:
            q = 1
            year += 1
    return periods


# All quarterly periods 2020Q1 → 2026Q1 (25 periods)
_PERIOD_ORDER = _gen_period_order()


def _period_lag(period: str, n_quarters: int) -> Optional[str]:
    """Return the period n_quarters before the given period, or None if out of range."""
    if period not in _PERIOD_ORDER:
        return None
    idx = _PERIOD_ORDER.index(period)
    lag_idx = idx - n_quarters
    return _PERIOD_ORDER[lag_idx] if lag_idx >= 0 else None


def compute_trajectories(panel_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Add trajectory features to a panel of (mi_key, period) rows.

    Uses EBIT-based metrics aligned with QoQ fundamentals files:
      - Total Debt / Total Capital (%)  — capital structure leverage
      - EBIT / Interest Expense (x)     — interest coverage
      - EBIT Margin                     — operating profitability
      - Net Income Margin               — bottom-line profitability
      - Return on Assets                — asset efficiency

    Lags are in quarters (n_quarters):
      delta_1q  = Δ vs 1 quarter ago  (~3 months)
      delta_4q  = Δ vs 4 quarters ago (~1 year)
      delta_8q  = Δ vs 8 quarters ago (~2 years)

    Rolling windows are calibrated to quarterly data:
      vol_8q   = rolling 8-quarter std  (~2-year volatility)
      max_16q  = rolling 16-quarter max (~4-year peak leverage)

    Returns NaN when prior period is absent — never extrapolates.
    """
    panel = panel_wide.copy().sort_values(["mi_key", "period"])
    panel = panel.set_index(["mi_key", "period"])

    def lag_col(col: str, n_quarters: int) -> pd.Series:
        result = {}
        for (mk, per) in panel.index:
            lag_per = _period_lag(per, n_quarters)
            if lag_per and (mk, lag_per) in panel.index:
                result[(mk, per)] = panel.loc[(mk, lag_per), col]
            else:
                result[(mk, per)] = np.nan
        return pd.Series(result)

    def _col_clean(col: str) -> str:
        return (
            col.split(" (")[0]
            .lower()
            .replace(" ", "_")
            .replace("/", "_to_")
            .replace(",", "")
            .replace(".", "")
            .replace("-", "_")
        )

    # Trajectory features: (metric_column, {n_quarters: suffix_label})
    _TRAJ_SPECS = [
        ("Total Debt / Total Capital (%)", {1: "delta_1q", 4: "delta_4q", 8: "delta_8q"}),
        ("EBIT / Interest Expense (x)",    {1: "delta_1q", 4: "delta_4q"}),
        ("EBIT Margin",                    {1: "delta_1q", 4: "delta_4q"}),
        ("Net Income Margin",              {1: "delta_1q", 4: "delta_4q"}),
        ("Return on Assets",              {1: "delta_1q", 4: "delta_4q"}),
    ]

    for col, suffix_map in _TRAJ_SPECS:
        if col not in panel.columns:
            continue
        for n_q, suffix in suffix_map.items():
            lag_s = lag_col(col, n_q)
            panel[f"{_col_clean(col)}_{suffix}"] = panel[col] - lag_s

    # Rolling 8-quarter (~2yr) volatility of margin metrics
    for margin_col, out_col in [
        ("EBIT Margin",       "vol_8q_ebit_margin"),
        ("Net Income Margin", "vol_8q_net_inc_margin"),
    ]:
        if margin_col in panel.columns:
            panel[out_col] = (
                panel[margin_col]
                .groupby(level=0)
                .transform(lambda s: s.rolling(8, min_periods=4).std())
            )

    # Distance to issuer's own 16-quarter (~4yr) max leverage
    lev_col = "Total Debt / Total Capital (%)"
    if lev_col in panel.columns:
        panel["issuer_16q_max_leverage_pct"] = (
            panel[lev_col]
            .groupby(level=0)
            .transform(lambda s: s.rolling(16, min_periods=4).max())
        )
        panel["distance_to_max_leverage_pct"] = (
            panel[lev_col] - panel["issuer_16q_max_leverage_pct"]
        )

    return panel.reset_index()


# ---------------------------------------------------------------------------
# 3. Ratio engineering (computed from raw metric columns)
# ---------------------------------------------------------------------------

def compute_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived financial ratios from raw metric columns.
    Returns NaN for any ratio where denominator is zero or missing.
    """
    d = df.copy()

    def safe_div(num_col: str, denom_col: str, out_col: str) -> None:
        num = d.get(num_col, pd.Series(np.nan, index=d.index))
        den = d.get(denom_col, pd.Series(np.nan, index=d.index))
        d[out_col] = np.where(
            den.isna() | (den == 0), np.nan, num / den
        )

    safe_div("Net Debt",                   "EBITDA",        "net_debt_to_ebitda")
    safe_div("Total Debt",                 "Total Assets",  "total_debt_to_assets")
    safe_div("Net Debt",                   "Total Assets",  "net_debt_to_assets")
    safe_div("Total Debt",                 "Total Common Equity", "debt_to_equity")
    safe_div("Levered Free Cash Flow",     "Total Debt",    "fcf_to_debt")
    safe_div("Cash from Ops.",             "Total Debt",    "cfo_to_debt")
    safe_div("EBITDA",                     "Total Revenue", "ebitda_margin_calc")
    safe_div("EBIT",                       "Total Revenue", "ebit_margin_calc")
    safe_div("Net Income",                 "Total Revenue", "net_income_margin_calc")
    safe_div("Cash from Ops.",             "Total Revenue", "cfo_to_revenue")
    safe_div("Unlevered Free Cash Flow",   "Total Revenue", "fcf_margin")
    safe_div("Cash & Short-term Investments", "Total Debt", "cash_to_debt")

    # log transforms
    for raw_col, out_col in [("Total Assets", "log_assets")]:
        col = d.get(raw_col, pd.Series(np.nan, index=d.index))
        d[out_col] = np.where(col > 0, np.log(col), np.nan)

    return d


# ---------------------------------------------------------------------------
# 4. Bond-level features
# ---------------------------------------------------------------------------

def compute_bond_features(bonds_df: pd.DataFrame) -> pd.DataFrame:
    b = bonds_df.copy()

    as_of = pd.Timestamp(b["as_of_date"].iloc[0])

    b["time_to_maturity_yrs"] = (b["maturity_date"] - as_of).dt.days / 365.25
    b["age_yrs"] = (as_of - b["issue_date"]).dt.days / 365.25
    b["log_amt_outstanding"] = np.where(
        b["amount_outstanding_000"] > 0,
        np.log(b["amount_outstanding_000"]),
        np.nan,
    )
    b["seniority_senior_unsecured"] = (
        b["seniority"].str.strip().str.lower() == "senior unsecured"
    ).astype(float)

    b["rating_numeric"] = b["sp_rating"].apply(rating_to_numeric)
    b["rating_is_ig"] = (b["rating_numeric"] <= IG_CUTOFF_NUMERIC).astype(float)

    return b


# ---------------------------------------------------------------------------
# 5. Downgrade label construction
# ---------------------------------------------------------------------------

_NEGATIVE_ACTIONS = re.compile(
    r"\b(downgrade|creditwatch negative|outlook.*negative|outlook revised to negative)\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\((\d{2}/\d{2}/\d{4})\)")


def _parse_action_history(history_str: str) -> list[tuple[str, pd.Timestamp]]:
    """Parse a semicolon-separated rating action string into (action, date) list."""
    if not isinstance(history_str, str):
        return []
    events = []
    for chunk in history_str.split(";"):
        chunk = chunk.strip()
        date_match = _DATE_RE.search(chunk)
        if not date_match:
            continue
        date = pd.to_datetime(date_match.group(1), format="%m/%d/%Y", errors="coerce")
        if pd.isna(date):
            continue
        action = _DATE_RE.sub("", chunk).strip(" |").strip()
        events.append((action, date))
    return events


def build_downgrade_labels(bonds_df: pd.DataFrame) -> pd.DataFrame:
    """
    Construct issuer-level downgrade labels from rating action history.

    For each issuer-period, label = 1 if any negative action (Downgrade,
    CreditWatch Negative, Outlook Negative) falls within 1 year AFTER
    the period end date.

    Returns DataFrame with columns: mi_key, period, period_end_date,
    downgrade_next_yr (0/1), any_negative_next_yr (0/1).
    """
    # Collect all negative events per mi_key (take the union across bonds)
    issuer_events: dict[str, list[pd.Timestamp]] = {}
    for _, row in bonds_df.iterrows():
        mi_key = str(row.get("mi_key", ""))
        if not mi_key or mi_key == "<NA>":
            continue
        history = str(row.get("sp_rating_action_history_3y", ""))
        for action, date in _parse_action_history(history):
            if _NEGATIVE_ACTIONS.search(action):
                issuer_events.setdefault(mi_key, []).append(date)

    # Use all quarterly periods whose 1-year forward window falls within the
    # ~3-year rating history available in bonddata (covers ~May 2023 to May 2026).
    # Eligible: period_end + 1yr ≤ 2026-05-27  →  2023Q1 through 2025Q1 (9 quarters).
    _HISTORY_CUTOFF = pd.Timestamp("2026-05-27")

    def _quarter_end(year: int, q: int) -> pd.Timestamp:
        month = q * 3
        day = calendar.monthrange(year, month)[1]
        return pd.Timestamp(year, month, day)

    eligible_periods = []
    for p in _gen_period_order(2023, 1, 2026, 1):
        yr, qn = int(p[:4]), int(p[5])
        pe = _quarter_end(yr, qn)
        if pe + pd.DateOffset(years=1) <= _HISTORY_CUTOFF:
            eligible_periods.append((p, pe))

    records = []
    for period, pe in eligible_periods:
        window_start = pe
        window_end = pe + pd.DateOffset(years=1)

        # Get all unique mi_keys in fundamentals
        mi_keys = bonds_df["mi_key"].dropna().astype(str).unique()
        for mi_key in mi_keys:
            events = issuer_events.get(mi_key, [])
            neg_in_window = any(window_start < e <= window_end for e in events)
            records.append({
                "mi_key": mi_key,
                "period": period,
                "period_end_date": pe,
                "downgrade_next_yr": int(neg_in_window),
            })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# 6. Staleness filter
# ---------------------------------------------------------------------------

def apply_staleness_filter(
    df_with_filing: pd.DataFrame,
    as_of_date: pd.Timestamp,
    max_staleness_quarters: int = MAX_STALENESS_QUARTERS,
) -> pd.DataFrame:
    """
    Drop rows where the most recent fundamental has a filing_date more than
    max_staleness_quarters × 91 days before as_of_date.
    """
    cutoff = as_of_date - timedelta(days=max_staleness_quarters * 91)
    if "filing_date" not in df_with_filing.columns:
        return df_with_filing
    mask = df_with_filing["filing_date"] >= cutoff
    n_dropped = (~mask).sum()
    if n_dropped:
        print(f"Staleness filter: dropping {n_dropped} rows (filing_date < {cutoff.date()})")
    return df_with_filing[mask].copy()


# ---------------------------------------------------------------------------
# 7. QoQ bond time-series features
# ---------------------------------------------------------------------------

# Metric columns where 0 means pre-issuance / missing data (not a real 0)
_ZERO_MASK_METRICS = frozenset({
    "z_spread_mid", "oas_mid", "ytm_mid",
    "mid_price", "modified_duration", "convexity", "macaulay_duration",
})


def compute_bond_ts_features(
    qoq_bond_panel: pd.DataFrame,
    as_of_date: pd.Timestamp,
) -> pd.DataFrame:
    """
    Compute per-bond time-series features from the QoQ bond metrics panel.

    Features computed per bond:
      *_ts_cur      — most recent value ≤ as_of_date
      *_chg_1m      — change vs ~30 days ago
      *_chg_3m      — change vs ~90 days ago
      *_chg_12m     — change vs ~365 days ago
      *_vol_6m      — rolling std over last 180 days
      *_vol_12m     — rolling std over last 365 days (z-spread only)

    Returns wide DataFrame keyed by instrument_id.
    """
    panel = qoq_bond_panel.copy()
    panel = panel[panel["value"].notna() & (panel["date"] <= as_of_date)]

    # Treat 0 as pre-issuance/missing for financial metrics
    mask_zero = panel["metric"].isin(_ZERO_MASK_METRICS) & (panel["value"] == 0)
    panel.loc[mask_zero, "value"] = np.nan

    wide = (
        panel
        .pivot_table(
            index=["instrument_id", "cusip", "mi_key", "date"],
            columns="metric",
            values="value",
            aggfunc="last",
        )
        .reset_index()
    )
    wide.columns.name = None
    wide = wide.sort_values(["instrument_id", "date"]).reset_index(drop=True)

    # Feature spec: (metric, [(suffix, days, is_volatility)])
    _FEAT_CFG = [
        ("z_spread_mid",      [
            ("chg_1m",  30,  False), ("chg_3m",  90,  False),
            ("chg_12m", 365, False), ("vol_6m",  180, True),
            ("vol_12m", 365, True),
        ]),
        ("oas_mid",           [
            ("chg_1m",  30,  False), ("chg_3m",  90,  False),
            ("chg_12m", 365, False),
        ]),
        ("ytm_mid",           [
            ("chg_1m",  30,  False), ("chg_3m",  90,  False),
            ("chg_12m", 365, False),
        ]),
        ("mid_price",         [
            ("chg_1m",  30,  False), ("chg_3m",  90,  False),
            ("vol_6m",  180, True),
        ]),
        ("modified_duration", [("chg_12m", 365, False)]),
        ("entity_trade_vol",  [("chg_3m",  90,  False), ("vol_6m", 180, True)]),
    ]

    all_rows: list[dict] = []

    for inst_id, grp in wide.groupby("instrument_id", sort=False):
        grp = grp.set_index("date").sort_index()
        eligible = grp[grp.index <= as_of_date]
        if eligible.empty:
            continue

        latest_date = eligible.index[-1]
        latest = eligible.loc[latest_date]

        def _closest(col: str, ref_date: pd.Timestamp, tol_days: int = 20) -> float:
            if col not in eligible.columns:
                return np.nan
            s = eligible[col].dropna()
            if s.empty:
                return np.nan
            diffs = np.abs((s.index - ref_date).days)
            best = int(diffs.argmin())
            return float(s.iloc[best]) if diffs[best] <= tol_days else np.nan

        def _mom(col: str, days: int) -> float:
            cur = _closest(col, latest_date, tol_days=5)
            ref = _closest(col, latest_date - pd.Timedelta(days=days))
            return cur - ref if not (np.isnan(cur) or np.isnan(ref)) else np.nan

        def _vol(col: str, days: int) -> float:
            if col not in eligible.columns:
                return np.nan
            cutoff = latest_date - pd.Timedelta(days=days)
            s = eligible[col].dropna()
            s = s[s.index >= cutoff]
            return float(s.std()) if len(s) >= 3 else np.nan

        row: dict = {
            "instrument_id": inst_id,
            "cusip":         str(latest.get("cusip", "")),
            "mi_key":        str(latest.get("mi_key", "")),
        }

        for metric, specs in _FEAT_CFG:
            if metric not in eligible.columns:
                continue
            row[f"{metric}_ts_cur"] = _closest(metric, latest_date, tol_days=5)
            for suffix, days, is_vol in specs:
                row[f"{metric}_{suffix}"] = (
                    _vol(metric, days) if is_vol else _mom(metric, days)
                )

        all_rows.append(row)

    return pd.DataFrame(all_rows)


# ---------------------------------------------------------------------------
# 8. Build feature matrices
# ---------------------------------------------------------------------------

def build_feature_matrix_spreads(
    bonds_df: pd.DataFrame,
    crosswalk_df: pd.DataFrame,
    fundamentals_long: pd.DataFrame,
) -> pd.DataFrame:
    """
    Full pipeline → feature_matrix_spreads.parquet.

    One row per bond observation with:
      - Bond characteristics
      - PIT-joined current fundamentals (using filing_date)
      - Derived ratios
      - OAS as target
    """
    # Attach mi_key from crosswalk to bonds that lack it
    cw = crosswalk_df[["issuer_name", "mi_key"]].rename(columns={"mi_key": "cw_mi_key"})
    bonds = bonds_df.merge(cw, on="issuer_name", how="left")
    bonds["mi_key"] = bonds["mi_key"].where(bonds["mi_key"].notna(), bonds["cw_mi_key"])
    bonds = bonds.drop(columns=["cw_mi_key"])

    # Drop bonds with no mi_key (the 4 excluded issuers + others without fundamentals)
    bonds = bonds[bonds["mi_key"].notna() & (bonds["mi_key"] != "<NA>")].copy()

    # Bond-level features
    bonds = compute_bond_features(bonds)

    # PIT join fundamentals
    bonds = pit_join_fundamentals(bonds, fundamentals_long)

    # Back-fill QoQ panel gaps with bonddata embedded snapshot values
    _BD_FALLBACKS = {
        "EBITDA":            "ebitda_cur",
        "Total Debt":        "total_debt_cur",
        "Net Debt":          "net_debt_cur",
        "Total Assets":      "total_assets_cur",
        "Cash from Ops.":    "cfo_cur",
        "Levered Free Cash Flow":   "levered_fcf_cur",
        "Unlevered Free Cash Flow": "unlevered_fcf_cur",
        "EBIT / Interest Expense (x)": "ebitda_interest_cov_cur",
        "Current Ratio (x)": "current_ratio_cur",
    }
    for fh_col, bd_col in _BD_FALLBACKS.items():
        if bd_col not in bonds.columns:
            continue
        if fh_col not in bonds.columns:
            bonds[fh_col] = bonds[bd_col]
        else:
            bonds[fh_col] = bonds[fh_col].where(bonds[fh_col].notna(), bonds[bd_col])

    # Derived ratios
    bonds = compute_ratios(bonds)

    # Join QoQ bond time-series features if the panel parquet exists
    as_of = pd.Timestamp(bonds["as_of_date"].iloc[0])
    if QOQ_BOND_PANEL_PARQUET.exists():
        qoq_panel = pd.read_parquet(QOQ_BOND_PANEL_PARQUET)
        ts_feats = compute_bond_ts_features(qoq_panel, as_of)
        # Drop redundant identifier columns before merging
        ts_feats = ts_feats.drop(columns=["cusip", "mi_key"], errors="ignore")
        bonds = bonds.merge(ts_feats, on="instrument_id", how="left")
        n_joined = ts_feats["instrument_id"].notna().sum()
        n_ts_cols = len(ts_feats.columns) - 1  # exclude instrument_id
        print(f"  Joined {n_ts_cols} bond TS features for {n_joined} bonds")

    # OAS sanity filter is applied in model_spreads, not here

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    bonds.to_parquet(FEATURES_SPREADS, index=False)
    n_valid_oas = bonds["oas_bid"].notna().sum()
    print(
        f"feature_matrix_spreads.parquet: {len(bonds)} bonds, "
        f"{n_valid_oas} with valid OAS"
    )
    return bonds


def build_feature_matrix_downgrades(
    bonds_df: pd.DataFrame,
    crosswalk_df: pd.DataFrame,
    fundamentals_long: pd.DataFrame,
) -> pd.DataFrame:
    """
    Full pipeline → feature_matrix_downgrades.parquet.

    One row per (issuer, period) with fundamentals and downgrade label.
    """
    # Build downgrade labels
    labels_df = build_downgrade_labels(bonds_df)

    # Get trajectories on the full historical panel
    panel_wide = _pivot_period_wide(fundamentals_long)
    panel_traj = compute_trajectories(panel_wide)
    panel_ratios = compute_ratios(panel_traj)

    # Merge labels with features
    panel_ratios["mi_key"] = panel_ratios["mi_key"].astype(str)
    labels_df["mi_key"] = labels_df["mi_key"].astype(str)

    merged = labels_df.merge(panel_ratios, on=["mi_key", "period"], how="inner")

    # Add issuer rating (from bonds_df, current)
    rating_map = (
        bonds_df[["mi_key", "rating_numeric"]]
        .dropna(subset=["mi_key"])
        .assign(mi_key=lambda d: d["mi_key"].astype(str))
        .groupby("mi_key")["rating_numeric"]
        .first()
    ) if "rating_numeric" in bonds_df.columns else pd.Series(dtype=float)

    # Compute bond features once (for the current snapshot) to add to issuer level
    bonds_tmp = compute_bond_features(bonds_df.copy())
    if "rating_numeric" in bonds_tmp.columns:
        rating_map = (
            bonds_tmp[["mi_key", "rating_numeric"]]
            .dropna(subset=["mi_key"])
            .assign(mi_key=lambda d: d["mi_key"].astype(str))
            .drop_duplicates(subset=["mi_key"])
            .set_index("mi_key")["rating_numeric"]
        )
        merged["rating_numeric"] = merged["mi_key"].map(rating_map)

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(FEATURES_DOWNGRADES, index=False)
    pos = merged["downgrade_next_yr"].sum()
    print(
        f"feature_matrix_downgrades.parquet: {len(merged)} issuer-periods, "
        f"{int(pos)} positive ({pos/len(merged):.1%} base rate)"
    )
    return merged


def run_feature_engineering(
    bonds_df: pd.DataFrame,
    crosswalk_df: pd.DataFrame,
    fundamentals_long: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run all feature engineering. Returns (spreads_df, downgrades_df)."""
    if fundamentals_long is None:
        fundamentals_long = pd.read_parquet(FUNDAMENTALS_PARQUET)

    spreads_df = build_feature_matrix_spreads(bonds_df, crosswalk_df, fundamentals_long)
    downgrades_df = build_feature_matrix_downgrades(bonds_df, crosswalk_df, fundamentals_long)
    return spreads_df, downgrades_df
