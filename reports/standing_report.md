# Project Standing Report — Pre-Redevelopment Baseline
**As of**: 2026-06-04

---

## 1. Data Inventory

### Raw Sources

| File / Directory | Content | Status |
|------------------|---------|--------|
| `SP data/bonddata.csv` | 458 bonds × 120 cols — current-snapshot pricing, spreads, embedded fundamentals | Ready |
| `SP data/qoqbonddata/Z.csv` | Z-spread mid, 35 dates per bond | Ready |
| `SP data/qoqbonddata/OAS.csv` | OAS mid, 35 dates | Ready |
| `SP data/qoqbonddata/modified.csv` | Modified duration, 35 dates | Ready |
| `SP data/qoqbonddata/convexity.csv` | Convexity, 35 dates | Ready |
| `SP data/qoqbonddata/Macaulay.csv` | Macaulay duration, 35 dates | Ready |
| `SP data/qoqbonddata/midprice.csv` | Mid price, 35 dates | Ready |
| `SP data/qoqbonddata/yytm.csv` | YTM mid, 35 dates | Ready |
| `SP data/qoqbonddata/ytw%.csv` | YTW mid, 35 dates | Ready (non-standard date format handled) |
| `SP data/qoqbonddata/entitytrade.csv` | 30-day entity trade volume, 35 dates | Ready (4-header structure handled) |
| `SP data/qoqbonddata/sectortrade.csv` | 30-day sector trade volume, 35 dates | Ready (4-header structure handled) |
| `SP data/qoqbonddata/ratings.csv` | S&P ratings, 35 dates — PIT | Ready |
| `SP data/qoqbonddata/info.csv` | Static bond attrs (callable, seniority, maturity type) | Ready |
| `SP data/qoqbonddata/tld.csv` | Transcript Level Scores (earnings-call sentiment), 26 quarters | Ready — 50/109 issuers matched |
| `SP data/qoqfundamentals/` | 25 quarterly FinancialHighlights files (2020Q1–2026Q1) | Ready |
| `data/raw/mikey.csv` | Ticker → MI KEY crosswalk (137 rows, 73 unique tickers) | Partial — 59 TLD issuers still missing |

---

## 2. Intermediate Panels

### `bond_panel.parquet` — `data/interim/`

| Dimension | Value |
|-----------|-------|
| Rows | 16,030 (458 bonds × 35 dates) |
| Columns | 25 |
| Date range | 2020-12-31 → 2026-04-30 |
| Cadence | Quarterly Dec 2020 – Sep 2024 (16 points); Monthly Oct 2024 – Apr 2026 (19 points) |
| PIT rating coverage | 84.7% |
| Duplicate CUSIPs | 0 |

**Metric coverage (null rate)**

| Metric | Null % | Note |
|--------|--------|------|
| z_spread_mid | 41.5% | Pre-issuance NaN kept; 58.5% valid |
| oas_mid | 73.1% | Sparse — use Z-spread as primary |
| ytm_mid | 37.4% | |
| ytw_mid | 56.2% | Expected — non-callable bonds have no YTW |
| mid_price | 37.2% | |
| modified_duration | 41.0% | |
| convexity | 39.6% | |
| macaulay_duration | 41.0% | |
| entity_trade_vol | 0.0% | Full coverage |
| sector_trade_vol | 0.0% | Full coverage |

OAS by rating bucket (current bond_panel):
- IG (AAA–BBB-): 44.6% OAS coverage, 90.4% Z-spread coverage
- HY (BB+–B-): **18.1% OAS coverage**, 89.7% Z-spread coverage
- Distressed (CCC+): 54.6% OAS coverage, 100% Z-spread coverage

→ **Z-spread is the primary spread for all analysis. OAS is supplementary for IG only.**

---

### `issuer_panel.parquet` — `data/interim/`

| Dimension | Value |
|-----------|-------|
| Rows | 2,578 (109 issuers × 25 quarters) |
| Columns | 47 |
| Period range | 2020Q1 → 2026Q1 |
| TLD issuers matched | ~75 / 109 (~156 tickers → some issuers multi-matched) |
| Issuer-periods with TLD score | **69.3%** |
| TLD gap | ~31% inactive / subsidiary issuers with no equity ticker — expected |

**Key fundamental null rates**

| Metric | Null % |
|--------|--------|
| Total Debt | 0.5% |
| Net Debt | 0.5% |
| Total Assets | 0.7% |
| Total Revenue | 1.8% |
| Cash from Ops. | 2.1% |
| Net Income Margin | 2.4% |
| Return on Assets | 2.7% |
| Total Debt / Total Capital (%) | 4.3% |
| EBIT | 10.9% |
| EBIT Margin | 11.7% |
| EBIT / Interest Expense (x) | 19.7% |

EBIT/Interest at 19.7% null is the most important gap — concentrated in financial firms (banks, insurers) and regulated utilities with non-standard income structures.

---

## 3. Phase 2 ML Baseline (pre-redev)

### Model 1 — Spread Prediction (LightGBM Regressor)

| Metric | Value | Notes |
|--------|-------|-------|
| Validation | Issuer-grouped 5-fold CV | No data leakage across issuers |
| Target | Z-spread bid (primary), G-spread fallback | 332 bonds with valid spread |
| R² (OOF) | **0.435 ± 0.173** | Baseline was 0.275 ± 0.193 |
| RMSE (OOF) | **72.8 ± 36.5 bps** | Baseline was 163 ± 88 bps |
| Spearman ρ | **0.774 ± 0.061** | Baseline was 0.762 ± 0.043 |
| Features | 47 (fundamentals + bond structure + TS momentum + macro) | |

**Top 5 features by information gain**

| Rank | Feature | Gain |
|------|---------|------|
| 1 | rating_numeric | 17.5M |
| 2 | z_spread_mid_vol_12m ← *new QoQ TS feature* | 11.3M |
| 3 | mid_price_vol_6m ← *new QoQ TS feature* | 3.9M |
| 4 | ytm_mid_chg_12m ← *new QoQ TS feature* | 3.4M |
| 5 | modified_duration | 3.1M |

3 of top 5 features are QoQ time-series features — new in the current pipeline.

---

### Model 2 — Downgrade Risk (LightGBM + Cox PH Ensemble)

| Split | PR-AUC | ROC-AUC | Recall@Decile | n | Base rate |
|-------|--------|---------|---------------|---|-----------|
| Val (2024Q4) | **0.919** | **0.941** | 0.33 | 78 | 30.8% |
| Test (2025Q1) | **0.846** | **0.894** | 0.32 | 78 | 28.2% |
| Baseline (Phase 1) | 0.505 | 0.548 | 0.09 | — | 18.5% |

Training set: 7 quarterly periods (2023Q1–2024Q3), 355 issuer-period observations, 65 positives.

**Top 5 features by gain**

| Rank | Feature | Type |
|------|---------|------|
| 1 | debt_to_equity | Level |
| 2 | log_assets | Level (size) |
| 3 | cash_to_debt | Liquidity |
| 4 | vol_8q_ebit_margin ← *new quarterly trajectory* | Volatility |
| 5 | vol_8q_net_inc_margin ← *new quarterly trajectory* | Volatility |

**Cox model note**: All 5 top hazard ratios are statistically non-significant (p > 0.35). The ensemble is effectively LGB-only; Cox adds noise.

---

## 4. Pipeline State

| Component | File | Status |
|-----------|------|--------|
| Panel builder | `src/build_panel.py` | Production-ready |
| Raw parser | `src/parse_capital_iq.py` | Production-ready |
| Feature engineering | `src/features.py` | Uses Phase 2 logic; will be rewritten for redev |
| Spread model | `src/model_spreads.py` | Phase 2 baseline |
| Downgrade model | `src/model_downgrades.py` | Phase 2 baseline |
| RV framework | `src/rv_framework.py` | Phase 2 baseline |
| Evaluation | `src/evaluate.py` | Phase 2 baseline |
| Macro overlay | `src/macro.py` | FRED cache in `data/interim/macro_cache/` |
| Panel as-of join | *not yet built* | Step 2 of redev |

---

## 5. Known Gaps — Priority Order

### Blocking for redev

_None remaining._

### Acknowledged, non-blocking

| Gap | Impact | Handling in Redev |
|-----|--------|-------------------|
| TLD coverage 69.3% | 31% issuer-periods missing | Accepted — inactive/subsidiary issuers have no equity ticker; use TLD with missing-indicator flag |
| OAS null = 73.1% (HY = 18.1%) | OAS unusable for HY; use Z-spread | Z-spread as primary; OAS supplementary for IG only |
| EBIT/Interest null = 19.7% | Missing for banks, utilities | Impute with sector median or leave NaN + indicator |
| Cox model adds no signal | Minor — ensemble = LGB-only effectively | Drop Cox; use LGB-only downgrade model |
| YTW null = 56.2% | Expected for non-callables | Use YTW − YTM spread as optionality proxy where non-null |
| Panel cadence mixed (monthly + quarterly) | CV fold boundaries must respect cadence | Time-based splits aligned to quarter-ends |
| Ratings coverage 84.7% | 15.3% pre-issuance rows | Correctly NaN; model handles natively |

---

## 6. Redev Scope (pending your approval)

The redevelopment will rebuild the modelling layer to consume `bond_panel` + `issuer_panel` directly via `pd.merge_asof` (backward) rather than the existing single-snapshot pipeline. Key changes planned:

1. **As-of join module** — `src/join_panels.py`: merge bond_panel × issuer_panel on `(mi_key, date vs filing_date)` with backward fill; attach TLD scores similarly.
2. **Feature engineering rebuild** — replace `src/features.py` with panel-native trajectory and TS feature computation.
3. **Model 1 (spread)** — panel-based cross-sectional regression; retain grouped CV; add YTW-YTM spread as optionality feature.
4. **Model 2 (downgrade)** — LGB-only (drop Cox); expand to full quarterly label set (9 periods); add TLD score as feature where available.
5. **Model 3 (new)** — optional: liquidity-adjusted spread decomposition using entity/sector trade volume.

**All blockers cleared. Ready for redev on your go-ahead.**
