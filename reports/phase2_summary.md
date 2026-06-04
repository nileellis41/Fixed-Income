# Bond ML Phase 2 — Summary Report

**Generated**: 2026-05-29
**Dataset**: 458 bonds, 168 issuers, 25 quarterly snapshots (2020Q1–2026Q1)
**New data**: QoQ bond time-series (z-spread, OAS, YTM, price, duration, trade volume — 35-date history per bond)

---

## Data Coverage

| Item | Count |
|------|-------|
| Bond observations | 458 |
| Unique issuers | 168 |
| Issuers with valid spread model | 126 |
| Bonds with valid spread | 332 (Z/G/A-spread) |
| Quarterly fundamental periods | 25 (2020Q1–2026Q1) |
| Downgrade label periods | 9 quarterly (2023Q1–2025Q1) |
| Downgrade labels (positive) | 142 of 702 issuer-periods (20.2%) |

---

## Model 1 — Spread Prediction

**Algorithm**: LightGBM Regressor with monotonic constraints
**Validation**: Issuer-grouped 5-fold cross-validation

| Metric | Mean | ± Std |
|--------|------|-------|
| Grouped-CV R² | 0.435 | ±0.173 |
| RMSE (bps) | 72.8 | ±36.5 |
| Spearman ρ | 0.774 | ±0.061 |

*Note: 332 bonds had valid spread data (Z/G/A-spread). OAS was not available in this CIQ export.*

---

## Model 2 — Downgrade Risk

**Algorithm**: LightGBM classifier + Cox PH ensemble
**Validation**: Time-forward holdout (train 2023Q1–2024Q3, val 2024Q4, test 2025Q1)

| Metric | Test |
|--------|------|
| PR-AUC (primary) | 0.846 |
| ROC-AUC | 0.894 |
| Brier Score | 0.164 |
| Recall @ Top Decile | 0.32 |
| Base Rate | 28.2% |

*Top features: debt/equity ratio, issuer size (log assets), cash/debt buffer, 8-quarter EBIT margin volatility, 8-quarter net income volatility.*

---

## RV Framework — Top Longs (Cheap + Safe)

| issuer_name                    | sp_rating   |   actual_spread |   cheapness_bps |   downgrade_prob_4q |   modified_duration |
|:-------------------------------|:------------|----------------:|----------------:|--------------------:|--------------------:|
| Vericast Corp.                 | CCC         |         784.489 |        521.363  |         nan         |             1.29494 |
| Vericast Corp.                 | CCC         |         784.489 |        521.363  |         nan         |             1.29494 |
| LGI Homes, Inc.                | B           |         308.435 |        179.119  |           0.0681366 |             2.17342 |
| Yellowstone Energy LP          | BBB         |         431.979 |        311.43   |         nan         |             0.54831 |
| Warner Media, LLC              | BB          |         591.722 |        283.16   |         nan         |             7.89096 |
| Bath & Body Works, Inc.        | BB-         |         293.986 |        137.169  |           0.0931837 |             5.21364 |
| Bath & Body Works, Inc.        | BB-         |         293.986 |        137.169  |           0.0931837 |             5.21364 |
| Warner Media, LLC              | BB          |         606.207 |        240.3    |         nan         |             9.13513 |
| iHeartCommunications, Inc.     | CCC+        |         504.102 |        226.871  |         nan         |             3.71535 |
| Valero Energy Corporation      | BBB         |         304.31  |        213.662  |         nan         |             0.08571 |
| Warner Media, LLC              | BB          |         536.024 |        196.745  |         nan         |             8.05474 |
| USF&G Capital III              | BBB+        |         333.227 |        191.136  |         nan         |             9.55471 |
| Warner Media, LLC              | BB          |         534.45  |        190.083  |         nan         |             8.78852 |
| Talcott Resolution Life, Inc.  | BB+         |         271.517 |        188.945  |         nan         |             0.95698 |
| Jefferies Financial Group Inc. | BBB         |         388.218 |        155.32   |           0.394155  |             6.83156 |
| Warner Media, LLC              | BB          |         510.585 |        181.612  |         nan         |             9.09024 |
| Bath & Body Works, Inc.        | BB-         |         293.986 |         97.5312 |           0.0931837 |             5.21364 |
| Southwest Gas Corporation      | BBB+        |         223.846 |         94.6846 |           0.0772742 |             0.9514  |
| Warner Media, LLC              | BB          |         485.389 |        151.245  |         nan         |             9.57217 |
| Warner Media, LLC              | BB          |         492.379 |        151.106  |         nan         |             9.05129 |

---

## RV Framework — Top Shorts (Rich + Risky)

| issuer_name                          | sp_rating   |   actual_spread |   cheapness_bps |   downgrade_prob_4q |   modified_duration |
|:-------------------------------------|:------------|----------------:|----------------:|--------------------:|--------------------:|
| Occidental Petroleum Corporation     | BB+         |        58.5973  |       -237.562  |          nan        |             1.3789  |
| Anadarko Petroleum Corporation       | BB+         |        88.619   |       -189.676  |          nan        |             1.49687 |
| Alcoa Nederland Holding B.V          | BB+         |         0       |       -165.483  |          nan        |             0       |
| Occidental Petroleum Corporation     | BB+         |        89.2456  |       -120.639  |          nan        |             2.49052 |
| Howard Hughes Holdings Inc.          | BB-         |       166.825   |       -122.526  |            0.388425 |             4.07801 |
| BellSouth, LLC                       | BBB         |       -21.9664  |        -94.3957 |          nan        |             0.45233 |
| Dell Inc.                            | BBB         |        16.3573  |        -90.4191 |          nan        |             1.74219 |
| Anadarko Petroleum Corporation       | BB+         |        91.3969  |        -81.5646 |          nan        |             2.49017 |
| Indiana Gas Company, Inc.            | BBB+        |         5.32963 |        -78.8347 |          nan        |             2.9545  |
| Historic TW Inc.                     | BB          |       230.326   |        -78.2895 |          nan        |             6.36148 |
| Occidental Petroleum Corporation     | BB+         |       142.781   |        -76.4258 |          nan        |            11.1323  |
| Kinder Morgan, Inc.                  | BBB+        |         7.55057 |        -67.5382 |          nan        |             1.62175 |
| Historic TW Inc.                     | BB          |       283.036   |        -65.7152 |          nan        |             1.47643 |
| Blue Owl Credit Income Corp.         | BBB-        |       179.008   |        -58.7532 |          nan        |             1.80513 |
| Blue Owl Finance LLC                 | BBB         |       108.922   |        -58.7124 |          nan        |             1.84079 |
| Blue Owl Finance LLC                 | BBB         |       108.922   |        -58.7124 |          nan        |             1.84079 |
| Blue Owl Finance LLC                 | BBB         |       108.922   |        -58.7124 |          nan        |             1.84079 |
| Southern California Edison Company   | BBB+        |       -80.5173  |       -174.201  |            0.161434 |             0.00539 |
| Northrop Grumman Systems Corporation | BBB+        |        58.8579  |        -55.7352 |          nan        |             2.59461 |
| Sabine Pass Liquefaction, LLC        | BBB+        |        76.2534  |        -55.7096 |          nan        |             5.12024 |

---

## Caveats

1. **Single-period snapshot**: All bonds observed at one point in time (2026-05-27). Cross-sectional spread regression has limited power vs. a full panel model.
2. **S&P ratings only**: No Moody's/Fitch confirmation. Rating outliers are not validated.
3. **No recovery modeling**: Z-spread/G-spread contains credit spread and some liquidity premium; not decomposed.
4. **No liquidity adjustment**: Bid-ask spread is included as a feature but spreads themselves are not liquidity-adjusted.
5. **Downgrade base rate is elevated**: 2025Q1 test set has 28% base rate vs historical ~15%; PR-AUC benefits from denser signal.
6. **Cox model adds noise**: All Cox hazard ratio p-values > 0.35; the ensemble is effectively LGB-only for downgrade prediction.
7. **No Sharpe ratio reported**: Requires a paper-portfolio backtest with realistic bid-ask costs; not done here.

