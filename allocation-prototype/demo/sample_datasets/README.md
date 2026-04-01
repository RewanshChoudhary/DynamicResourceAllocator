# Allocation Prototype Dataset Payloads

This directory contains the versioned sample payloads used by the frontend demo.

All three datasets are generated from the real `Zomato Dataset.csv` source by `scripts/generate_realistic_sample.py` and remain compatible with the current `POST /allocations` payload format.

Available datasets:

- `realistic_clear_weather.json`: large clear-weather slice with 172 orders sourced from Sunny, Cloudy, and Windy rows.
- `realistic_severe_weather.json`: large severe-weather slice with 288 orders sourced from Stormy and Sandstorms rows.
- `realistic_traffic_jam.json`: large traffic-heavy slice with 544 orders sourced from Jam and High traffic rows.

These datasets intentionally avoid using the dataset's distance field.

All files follow the same `orders` plus `partners` payload shape accepted by `POST /allocations`. The `metadata` object supports the dataset catalog and operator context shown in the prototype console.

To regenerate the dataset catalog:

```bash
.venv/bin/python scripts/generate_realistic_sample.py --mode clear_weather --csv ../Zomato\ Dataset.csv
.venv/bin/python scripts/generate_realistic_sample.py --mode severe_weather --csv ../Zomato\ Dataset.csv
.venv/bin/python scripts/generate_realistic_sample.py --mode traffic_jam --csv ../Zomato\ Dataset.csv
```

To validate the dataset directory:

```bash
.venv/bin/python scripts/validate_sample_datasets.py
```
