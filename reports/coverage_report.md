# Bond Panel Coverage Report

**Generated**: 2026-06-04

---

## 1. Bond Panel (`bond_panel.parquet`)

| Item | Value |
|------|-------|
| Total observations (bond × date rows) | 16,030 |
| Unique instruments (bonds) | 458 |
| Unique observation dates | 35 |
| Date range | 2020-12-31 → 2026-04-30 |
| Bonds with valid rating coverage | 84.7% of rows |
| Duplicate-CUSIP bonds flagged | 0 CUSIPs |

### Null rates by metric column

| Metric | Null % |
|--------|--------|
| convexity | 39.6% |
| entity_trade_vol | 0.0% |
| macaulay_duration | 41.0% |
| mid_price | 37.2% |
| modified_duration | 41.0% |
| oas_mid | 73.1% |
| sector_trade_vol | 0.0% |
| ytm_mid | 37.4% |
| z_spread_mid | 41.5% |

### Sample rows (head 5 + tail 5)

| instrument_id   | cusip     |   mi_key | issuer_name                        | date                |   z_spread_mid |   oas_mid | sp_rating   |   sp_rating_numeric | seniority_level   | is_duplicate_cusip   | bond_active   |
|:----------------|:----------|---------:|:-----------------------------------|:--------------------|---------------:|----------:|:------------|--------------------:|:------------------|:---------------------|:--------------|
| SPS100451023    | 126408GR8 |  4004350 | CSX Corporation                    | 2020-12-31 00:00:00 |        nan     |       nan | BBB+        |                   8 | Senior Unsecured  | False                | True          |
| SPS100451023    | 126408GR8 |  4004350 | CSX Corporation                    | 2021-03-31 00:00:00 |        nan     |       nan | BBB+        |                   8 | Senior Unsecured  | False                | True          |
| SPS100451023    | 126408GR8 |  4004350 | CSX Corporation                    | 2021-06-30 00:00:00 |        nan     |       nan | BBB+        |                   8 | Senior Unsecured  | False                | True          |
| SPS100451023    | 126408GR8 |  4004350 | CSX Corporation                    | 2021-09-30 00:00:00 |        nan     |       nan | BBB+        |                   8 | Senior Unsecured  | False                | True          |
| SPS100451023    | 126408GR8 |  4004350 | CSX Corporation                    | 2021-12-31 00:00:00 |        nan     |       nan | BBB+        |                   8 | Senior Unsecured  | False                | True          |
| SPS99254812     | 842400FP3 |  4009083 | Southern California Edison Company | 2025-12-31 00:00:00 |        142.017 |       nan | BBB+        |                   8 | Senior Secured    | False                | True          |
| SPS99254812     | 842400FP3 |  4009083 | Southern California Edison Company | 2026-01-30 00:00:00 |        138.965 |       nan | BBB+        |                   8 | Senior Secured    | False                | True          |
| SPS99254812     | 842400FP3 |  4009083 | Southern California Edison Company | 2026-02-27 00:00:00 |        153.736 |       nan | BBB+        |                   8 | Senior Secured    | False                | True          |
| SPS99254812     | 842400FP3 |  4009083 | Southern California Edison Company | 2026-03-31 00:00:00 |        152.876 |       nan | BBB+        |                   8 | Senior Secured    | False                | True          |
| SPS99254812     | 842400FP3 |  4009083 | Southern California Edison Company | 2026-04-30 00:00:00 |        148.258 |       nan | BBB+        |                   8 | Senior Secured    | False                | True          |

---

## 2. Duplicate CUSIPs (144A / Reg S tranches)

| CUSIP | Instrument IDs |
|-------|----------------|
| — | — |

---

## 3. Issuer Panel (`issuer_panel.parquet`)

| Item | Value |
|------|-------|
| Unique issuers (MI KEY) | 109 |
| Unique periods | 25 |
| Period range | 2020Q1 → 2026Q1 |
| TLD tickers matched | 109 |
| Issuer-periods with TLD score | 47.3% |

### Fundamental metric null rates (key credit metrics)

| Metric | Null % |
|--------|--------|
| Total Debt / Total Capital (%) | 4.3% |
| EBIT / Interest Expense (x) | 19.7% |
| EBIT Margin | 11.7% |
| Net Income Margin | 2.4% |
| Return on Assets | 2.7% |
| Cash from Ops. | 2.1% |
| Total Debt | 0.5% |
| Total Assets | 0.7% |
| Net Debt | 0.5% |
| Total Revenue | 1.8% |
| EBIT | 10.9% |

### Sample rows (head 5 + tail 5)

|   mi_key | period   | period_end_date     | filing_date         |   Total Debt / Total Capital (%) |   EBIT / Interest Expense (x) |   EBIT Margin |   tld_score |
|---------:|:---------|:--------------------|:--------------------|---------------------------------:|------------------------------:|--------------:|------------:|
|   100144 | 2020Q1   | 2020-03-31 00:00:00 | 2021-05-06 00:00:00 |                              nan |                        nan    |       nan     |         nan |
|   100144 | 2020Q2   | 2020-06-30 00:00:00 | 2021-08-05 00:00:00 |                              nan |                        nan    |       nan     |         nan |
|   100144 | 2020Q3   | 2020-09-30 00:00:00 | 2021-11-05 00:00:00 |                              nan |                        nan    |       nan     |         nan |
|   100144 | 2020Q4   | 2020-12-31 00:00:00 | 2022-02-25 00:00:00 |                              nan |                        nan    |       nan     |         nan |
|   100144 | 2021Q1   | 2021-03-31 00:00:00 | 2022-05-06 00:00:00 |                              nan |                        nan    |       nan     |         nan |
|  6588911 | 2025Q1   | 2025-03-31 00:00:00 | 2026-05-07 00:00:00 |                               63 |                        nan    |       -14.033 |         nan |
|  6588911 | 2025Q2   | 2025-06-30 00:00:00 | 2025-11-07 00:00:00 |                               62 |                          3.16 |        13.953 |         nan |
|  6588911 | 2025Q3   | 2025-09-30 00:00:00 | 2025-11-07 00:00:00 |                               60 |                         16.62 |        34.015 |         nan |
|  6588911 | 2025Q4   | 2025-12-31 00:00:00 | 2026-02-24 00:00:00 |                               59 |                          1.86 |        21.29  |         nan |
|  6588911 | 2026Q1   | 2026-03-31 00:00:00 | 2026-05-07 00:00:00 |                               64 |                        nan    |       -63.366 |         nan |

---

## 4. TLD Unjoinable Tickers

Tickers present in `tld.csv` that could not be matched to a MI KEY via `mikey.csv`:

- `ALL`
- `ALLY`
- `AT`
- `BHF`
- `BLS`
- `BNY`
- `BPLP.L`
- `C`
- `CIN`
- `CINF`
- `CLG`
- `CRBG`
- `CSR`
- `DFS`
- `DZA`
- `EJXR`
- `EPR`
- `EXSP`
- `FIID`
- `FUN`
- `GPN`
- `GS`
- `HHH`
- `ITC`
- `JEF`
- `KSU`
- `MAIN`
- `MAY`
- `MBG`
- `MOG.A`
- `MSCI`
- `NAVI`
- `NHI`
- `NSRT`
- `PCG`
- `PGS`
- `PPW`
- `PSIE`
- `RITM`
- `RTN`
- `SCHW`
- `TWC`
- `TWX`
- `UNM`
- `VYX`
- `WFC`
- `WY`

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
