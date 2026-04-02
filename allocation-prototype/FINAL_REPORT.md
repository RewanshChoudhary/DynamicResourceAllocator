## Bugs Found: 3
## Bugs Fixed: 3
## Tests Before: 87 passed, 0 failed
## Tests After: 88 passed, 0 failed

## Fixed Issues
- FIX_001: fairness scoring depended on app-level `PartnerLoadTracker` state -> fairness now reads request/domain `current_load` and repeated identical requests produce identical allocations.
- FIX_002: `load_capacity` was enabled in the default live config and over-constrained allocation -> it is now disabled by default and verified absent from `active_hard_rules`.
- FIX_003: rule contract cleanup was incomplete -> added the required weather-safety raw-vehicle documentation and the verified `0-1` score-scale comments for the new scoring rules.
- FIX_004: additive field flow, manifest serialization, and replay reconstruction were audited -> no code change was required because the fields already round-trip correctly.
- FIX_005: traffic-jam dataset generation and checked-in sample metadata were audited -> no code change was required because the generator already performs bounded window checks and fallback metadata tagging.

## Remaining Known Limitations
- `PartnerLoadTracker` still exists and is updated after allocations, but it is now analytics-only and no longer affects scoring decisions.
- `load_capacity` still exists as an optional rule and still appears in mutation/toggle surfaces, but it is disabled by default until there is an explicit product decision to re-enable it.
- `max_rating` is registered but not used by the default config.

## Prototype Status
FULLY WORKING — all verification tests pass

## How to Demo This Prototype

1. Start the server

```bash
cd allocation-prototype
PYTHONPATH=src .venv/bin/uvicorn allocation.api.app:app --port 8000
```

If port `8000` is already in use, swap it for `8002` in the commands below.

2. Load the severe weather dataset

```bash
curl -s -X POST http://127.0.0.1:8000/allocations \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: severe-demo-$(date +%s)" \
  --data @demo/sample_datasets/realistic_severe_weather.json \
  | python -m json.tool
```

3. Show vehicle condition and weather rules firing

Vehicle condition:

```bash
curl -s -X POST http://127.0.0.1:8000/allocations \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: vehicle-demo-$(date +%s)" \
  -d '{
    "orders": [{
      "order_id": "VDEMO001",
      "restaurant_location": {"lat": 12.97, "lon": 77.59},
      "delivery_location": {"lat": 13.02, "lon": 77.64},
      "vehicle_required": "bike",
      "priority": "NORMAL",
      "weather_condition": "Sunny",
      "traffic_density": "Low"
    }],
    "partners": [
      {
        "partner_id": "PGOOD",
        "rating": 4.5,
        "vehicle_type": "bike",
        "current_location": {"lat": 12.98, "lon": 77.60},
        "is_available": true,
        "vehicle_condition": 2,
        "avg_time_taken_min": 20
      },
      {
        "partner_id": "PBAD",
        "rating": 4.9,
        "vehicle_type": "bike",
        "current_location": {"lat": 12.975, "lon": 77.595},
        "is_available": true,
        "vehicle_condition": 0,
        "avg_time_taken_min": 15
      }
    ]
  }' | python -m json.tool
```

```bash
curl -s http://127.0.0.1:8000/audit/trace/VDEMO001 \
  | python -m json.tool | grep -E "selected_partner_id|VEHICLE_CONDITION_BELOW_MINIMUM"
```

Weather safety:

```bash
curl -s -X POST http://127.0.0.1:8000/allocations \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: weather-demo-$(date +%s)" \
  -d '{
    "orders": [{
      "order_id": "WDEMO001",
      "restaurant_location": {"lat": 12.97, "lon": 77.59},
      "delivery_location": {"lat": 13.02, "lon": 77.64},
      "vehicle_required": "bike",
      "priority": "NORMAL",
      "weather_condition": "Stormy",
      "traffic_density": "Low"
    }],
    "partners": [
      {
        "partner_id": "PMOTO",
        "rating": 4.8,
        "vehicle_type": "bike",
        "current_location": {"lat": 12.98, "lon": 77.60},
        "is_available": true,
        "vehicle_condition": 2,
        "avg_time_taken_min": 20,
        "raw_vehicle_type": "MOTORCYCLE"
      },
      {
        "partner_id": "PELEC",
        "rating": 4.2,
        "vehicle_type": "scooter",
        "current_location": {"lat": 12.98, "lon": 77.60},
        "is_available": true,
        "vehicle_condition": 2,
        "avg_time_taken_min": 25,
        "raw_vehicle_type": "ELECTRIC_SCOOTER"
      }
    ]
  }' | python -m json.tool
```

```bash
curl -s http://127.0.0.1:8000/audit/trace/WDEMO001 \
  | python -m json.tool | grep -E "selected_partner_id|VEHICLE_UNSAFE_IN_WEATHER"
```

4. Show the manifest and verify it

```bash
curl -s -X POST http://127.0.0.1:8000/allocations \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: verify-demo-$(date +%s)" \
  -d '{
    "orders": [{
      "order_id": "VERIFY001",
      "restaurant_location": {"lat": 12.97, "lon": 77.59},
      "delivery_location": {"lat": 13.02, "lon": 77.64},
      "vehicle_required": "bike",
      "priority": "NORMAL",
      "weather_condition": "Sunny",
      "traffic_density": "Low"
    }],
    "partners": [{
      "partner_id": "PVERIFY",
      "rating": 4.5,
      "vehicle_type": "bike",
      "current_location": {"lat": 12.98, "lon": 77.60},
      "is_available": true,
      "vehicle_condition": 2,
      "avg_time_taken_min": 20
    }]
  }' > /tmp/verify_demo.json
```

```bash
python - <<'PY'
import json
data = json.load(open('/tmp/verify_demo.json'))
print(data['manifest_id'])
PY
```

```bash
MANIFEST_ID=$(python - <<'PY'
import json
data = json.load(open('/tmp/verify_demo.json'))
print(data['manifest_id'])
PY
)
curl -s http://127.0.0.1:8000/audit/verify/$MANIFEST_ID | python -m json.tool
```

5. Run the traffic simulation preset

```bash
curl -s -X POST http://127.0.0.1:8000/allocations \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: traffic-base-$(date +%s)" \
  --data @demo/sample_datasets/realistic_traffic_jam.json \
  > /tmp/traffic_base.json
```

```bash
python - <<'PY'
import json
base = json.load(open('/tmp/traffic_base.json'))
presets = json.load(open('data/simulation_presets.json'))
traffic = next(p for p in presets if p['name'] == 'Enable Traffic-Aware Proximity')
payload = {'manifest_id': base['manifest_id'], 'mutations': traffic['mutations']}
print(json.dumps(payload))
PY
```

```bash
python - <<'PY' > /tmp/traffic_simulation_payload.json
import json
base = json.load(open('/tmp/traffic_base.json'))
presets = json.load(open('data/simulation_presets.json'))
traffic = next(p for p in presets if p['name'] == 'Enable Traffic-Aware Proximity')
json.dump({'manifest_id': base['manifest_id'], 'mutations': traffic['mutations']}, open('/tmp/traffic_simulation_payload.json', 'w'))
PY
curl -s -X POST http://127.0.0.1:8000/simulations \
  -H "Content-Type: application/json" \
  --data @/tmp/traffic_simulation_payload.json \
  | python -m json.tool
```
