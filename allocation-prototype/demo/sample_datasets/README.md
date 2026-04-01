# Curated Sample Datasets

These payloads are deterministic scenario samples for the allocation prototype. They are generated from hand-tuned city templates by `scripts/generate_sample_datasets.py`.

- `bengaluru_lunch_rush.json`: 42 orders and 28 partners for a dense weekday lunch rush with mostly two-wheelers and a smaller car fleet.
- `hyderabad_monsoon_mixed_fleet.json`: 48 orders and 30 partners for rain-shift demand with a broader mixed fleet.
- `gurugram_distance_pressure.json`: 56 orders and 24 partners for a suburban spread designed to surface distance-limit failures.

All files follow the same `orders` plus `partners` payload shape accepted by `POST /allocations`. The `metadata` object is for humans and frontend selection only.

To regenerate the datasets:

```bash
.venv/bin/python scripts/generate_sample_datasets.py
```
