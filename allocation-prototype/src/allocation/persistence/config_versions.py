from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from allocation.persistence.models import ConfigVersionModel


@dataclass(frozen=True)
class ConfigVersion:
    config_version_hash: str
    config_yaml: str
    config: dict[str, Any]


def canonical_config_json(config: dict[str, Any]) -> str:
    return json.dumps(config, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_config_json(config).encode("utf-8")).hexdigest()


class ConfigVersionStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def put_if_absent(self, config: dict[str, Any], commit: bool = True) -> ConfigVersion:
        version_hash = config_hash(config)
        existing = self.session.get(ConfigVersionModel, version_hash)
        if existing:
            return ConfigVersion(
                config_version_hash=existing.config_version_hash,
                config_yaml=existing.config_yaml,
                config=json.loads(existing.config_json),
            )

        yaml_payload = yaml.safe_dump(config, sort_keys=True)
        row = ConfigVersionModel(
            config_version_hash=version_hash,
            config_yaml=yaml_payload,
            config_json=canonical_config_json(config),
        )
        self.session.add(row)
        if commit:
            self.session.commit()

        return ConfigVersion(config_version_hash=version_hash, config_yaml=yaml_payload, config=config)

    def get_by_hash(self, version_hash: str) -> dict[str, Any] | None:
        row = self.session.get(ConfigVersionModel, version_hash)
        if not row:
            return None
        return {
            "config_version_hash": row.config_version_hash,
            "config_yaml": row.config_yaml,
            "config": json.loads(row.config_json),
        }

    def latest(self) -> dict[str, Any] | None:
        stmt = select(ConfigVersionModel).order_by(ConfigVersionModel.inserted_at.desc()).limit(1)
        row = self.session.execute(stmt).scalar_one_or_none()
        if row is None:
            return None
        return {
            "config_version_hash": row.config_version_hash,
            "config_yaml": row.config_yaml,
            "config": json.loads(row.config_json),
        }
