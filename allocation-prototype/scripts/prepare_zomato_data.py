from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from allocation.data.zomato_adapter import (  # noqa: E402
    audit_zomato_csv,
    build_allocation_payload_from_zomato,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and adapt Zomato CSV for allocation prototype")
    parser.add_argument(
        "--input",
        default=str((PROJECT_ROOT / ".." / "Zomato Dataset.csv").resolve()),
        help="Path to Zomato CSV",
    )
    parser.add_argument(
        "--audit-out",
        default=str(PROJECT_ROOT / "demo" / "zomato_audit_report.json"),
        help="Output path for data quality report JSON",
    )
    parser.add_argument(
        "--payload-out",
        default=str(PROJECT_ROOT / "demo" / "zomato_allocation_payload.json"),
        help="Output path for allocation payload JSON",
    )
    parser.add_argument("--max-orders", type=int, default=250)
    parser.add_argument("--max-partners", type=int, default=150)
    parser.add_argument("--max-delivery-radius-km", type=float, default=30.0)

    args = parser.parse_args()

    audit = audit_zomato_csv(args.input)
    payload = build_allocation_payload_from_zomato(
        args.input,
        max_orders=args.max_orders,
        max_partners=args.max_partners,
        max_delivery_radius_km=args.max_delivery_radius_km,
    )

    write_json(args.audit_out, audit.to_dict())
    write_json(args.payload_out, payload)

    print("Audit Summary")
    print(json.dumps(audit.to_dict(), indent=2, sort_keys=True))
    print("\nPayload Metadata")
    print(json.dumps(payload["metadata"], indent=2, sort_keys=True))
    print(f"\nWrote audit report to: {args.audit_out}")
    print(f"Wrote allocation payload to: {args.payload_out}")


if __name__ == "__main__":
    main()
