from __future__ import annotations

from enum import StrEnum


class VehicleType(StrEnum):
    BIKE = "bike"
    SCOOTER = "scooter"
    CAR = "car"


class AllocationStatus(StrEnum):
    ASSIGNED = "assigned"
    UNALLOCATED = "unallocated"


class ConflictType(StrEnum):
    LOGICAL = "logical"
    WEIGHT = "weight"
    DEPENDENCY = "dependency"


class ConflictResolution(StrEnum):
    AUTO_RESOLVED = "auto_resolved"
    REQUIRES_OPERATOR_ACTION = "requires_operator_action"
