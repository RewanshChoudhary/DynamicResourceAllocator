# Allocation Prototype Dataset Payloads

This directory contains two kinds of allocation payloads:

- Synthetic scenario payloads generated from hand-tuned city templates by `scripts/generate_sample_datasets.py`
- CSV-derived payloads generated from the real `Zomato Dataset.csv` source by `scripts/generate_zomato_sample_datasets.py`

Synthetic scenario payloads:

- `bengaluru_lunch_rush.json`: 42 orders and 28 partners for a dense weekday lunch rush with mostly two-wheelers and a smaller car fleet.
- `hyderabad_monsoon_mixed_fleet.json`: 48 orders and 30 partners for rain-shift demand with a broader mixed fleet.
- `gurugram_distance_pressure.json`: 56 orders and 24 partners for a suburban spread designed to surface distance-limit failures.

CSV-derived Zomato payloads:

- `zomato_national_high_volume.json`: a large multi-city allocation payload derived from the full CSV.
- `zomato_metro_jam_core.json`: a metropolitan jam-traffic slice for dense demand and rejection analysis.
- `zomato_urban_low_traffic.json`: a lighter urban slice for baseline allocation and replay checks.
- `zomato_festival_jam_surge.json`: a festival-period metropolitan jam slice for surge-style validation.
- `zomato_metro_high_traffic.json`: a metropolitan high-traffic slice for medium-sized diagnostics and replay runs.

All files follow the same `orders` plus `partners` payload shape accepted by `POST /allocations`. The `metadata` object supports the dataset catalog and operator context shown in the prototype console.

To regenerate the synthetic scenario datasets:

```bash
.venv/bin/python scripts/generate_sample_datasets.py
```

To regenerate the CSV-derived Zomato datasets:

```bash
.venv/bin/python scripts/generate_zomato_sample_datasets.py
```
