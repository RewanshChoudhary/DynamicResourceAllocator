from __future__ import annotations

import json

from common import get_broken_config_path

from allocation.config.loader import ConfigLoader
from allocation.rules.conflict import RuleConflictError


if __name__ == "__main__":
    loader = ConfigLoader(get_broken_config_path())
    print("Running conflict detection against rules_broken.yaml ...")

    try:
        loader.load()
    except RuleConflictError as exc:
        print("Configuration activation blocked as expected.")
        print(json.dumps(exc.report.to_dict(), indent=2, sort_keys=True))
    else:
        raise SystemExit("Expected conflict error but config loaded successfully")
