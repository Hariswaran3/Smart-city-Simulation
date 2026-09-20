# NeuraX Smart Cities Dataset Profile Report

- **Generated:** 2026-09-20T02:31:05.032336
- **Segments:** 436 road segments (collector & arterial)
- **Nodes:** 120 intersection nodes
- **Sampling:** 5-minute intervals
- **Training Data:** 1,883,520 rows (15 days)
- **Validation Data:** 502,272 rows (4 days)
- **Targets:** Speed, Flow, Congestion across 15m, 30m, 45m, 60m horizons

## Leakage Prevention Rules
1. `forecast_targets_train.csv` and `forecast_targets_validation.csv` are NEVER used as feature inputs.
2. Temporal data is sorted by `(segment_id, timestamp)` before computing lag features.
3. Validation targets are evaluated strictly out-of-sample.
