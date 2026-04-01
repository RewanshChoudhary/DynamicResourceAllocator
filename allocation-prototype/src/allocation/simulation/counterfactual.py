from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Annotated, Literal

from pydantic import BaseModel, Field

from allocation.engine.replay import snapshot_to_orders, snapshot_to_partners
from allocation.engine.loads import initial_partner_loads_for_replay
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.rules.conflict import RuleConflictDetector, RuleConflictError
from allocation.rules.registry import build_rule_set


class RuleParameterMutation(BaseModel):
    mutation_type: Literal["rule_parameter"] = "rule_parameter"
    rule_name: str
    parameter: str
    new_value: Any


class RuleWeightMutation(BaseModel):
    mutation_type: Literal["rule_weight"] = "rule_weight"
    rule_name: str
    new_weight: float


class RuleToggleMutation(BaseModel):
    mutation_type: Literal["rule_toggle"] = "rule_toggle"
    rule_name: str
    enabled: bool


class PartnerPayload(BaseModel):
    partner_id: str
    latitude: float
    longitude: float
    is_available: bool
    rating: float
    vehicle_types: list[str]
    active: bool = True


class PartnerPoolMutation(BaseModel):
    mutation_type: Literal["partner_pool"] = "partner_pool"
    add: list[PartnerPayload] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)
    modify: list[PartnerPayload] = Field(default_factory=list)


Mutation = Annotated[
    RuleParameterMutation | RuleWeightMutation | RuleToggleMutation | PartnerPoolMutation,
    Field(discriminator="mutation_type"),
]


class SimulationSpec(BaseModel):
    mutations: list[Mutation]


@dataclass(frozen=True)
class SimulationResult:
    manifest_id: str
    hypothetical_allocations: list[dict[str, Any]]
    trace_diff: list[dict[str, Any]]
    counterfactual_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "hypothetical_allocations": self.hypothetical_allocations,
            "trace_diff": self.trace_diff,
            "counterfactual_summary": self.counterfactual_summary,
        }


class CounterfactualSimulator:
    def __init__(self, manifest_repo: Any, input_snapshot_repo: Any, config_store: Any) -> None:
        self.manifest_repo = manifest_repo
        self.input_snapshot_repo = input_snapshot_repo
        self.config_store = config_store
        self.conflict_detector = RuleConflictDetector()

    def simulate(self, manifest_id: str, spec: SimulationSpec) -> SimulationResult:
        manifest = self.manifest_repo.get(manifest_id)
        if manifest is None:
            raise ValueError(f"Manifest {manifest_id} not found")

        snapshot = self.input_snapshot_repo.get(manifest.input_hash)
        if snapshot is None:
            raise ValueError(f"Input snapshot {manifest.input_hash} not found")

        config_record = self.config_store.get_by_hash(manifest.config_version_hash)
        if config_record is None:
            raise ValueError(f"Config version {manifest.config_version_hash} not found")

        mutated_config = copy.deepcopy(config_record["config"])
        mutated_snapshot = copy.deepcopy(snapshot)

        applied_mutations: list[str] = []
        for mutation in spec.mutations:
            if isinstance(mutation, RuleParameterMutation):
                self._apply_rule_parameter_mutation(mutated_config, mutation)
                applied_mutations.append(
                    f"rule_parameter:{mutation.rule_name}.{mutation.parameter}={mutation.new_value}"
                )
            elif isinstance(mutation, RuleWeightMutation):
                self._apply_rule_weight_mutation(mutated_config, mutation)
                applied_mutations.append(f"rule_weight:{mutation.rule_name}={mutation.new_weight}")
            elif isinstance(mutation, RuleToggleMutation):
                self._apply_rule_toggle_mutation(mutated_config, mutation)
                applied_mutations.append(f"rule_toggle:{mutation.rule_name}={mutation.enabled}")
            elif isinstance(mutation, PartnerPoolMutation):
                self._apply_partner_pool_mutation(mutated_snapshot, mutation)
                applied_mutations.append("partner_pool")
            else:
                raise ValueError(f"Unsupported mutation type: {mutation}")

        report = self.conflict_detector.detect(mutated_config)
        if report.blocking:
            raise RuleConflictError(report)
        mutated_config["weights"] = report.weights_after_resolution

        hard_rules, scoring_rules = build_rule_set(mutated_config)
        pipeline = DeterministicAllocationPipeline(hard_rules=hard_rules, scoring_rules=scoring_rules)

        orders = snapshot_to_orders(snapshot)
        hypothetical_partners = snapshot_to_partners(mutated_snapshot)

        simulated = pipeline.evaluate(
            orders=orders,
            partners=hypothetical_partners,
            scoring_weights=mutated_config.get("weights", {}),
            partner_loads=initial_partner_loads_for_replay(manifest.evaluation_trace, hypothetical_partners),
            fairness_escalation_event=manifest.fairness_escalation_event,
            conflict_resolution_report_hash=report.sha256(),
        )

        hypothetical_allocations = [
            {
                "order_id": a.order_id,
                "partner_id": a.partner_id,
                "status": a.status.value,
                "reason": a.reason,
                "weighted_score": a.weighted_score,
            }
            for a in simulated.allocations
        ]

        trace_diff = self._diff_traces(manifest.evaluation_trace, simulated.trace.to_dict())
        summary = {
            "applied_mutations": applied_mutations,
            "changed_orders": [entry["order_id"] for entry in trace_diff if entry.get("changed")],
            "total_changed_orders": sum(1 for entry in trace_diff if entry.get("changed")),
        }

        return SimulationResult(
            manifest_id=manifest_id,
            hypothetical_allocations=hypothetical_allocations,
            trace_diff=trace_diff,
            counterfactual_summary=summary,
        )

    @staticmethod
    def _find_rule_entry(config: dict[str, Any], rule_name: str) -> dict[str, Any] | None:
        for section in ("hard_rules", "scoring_rules"):
            for entry in config.get(section, []):
                if entry.get("name") == rule_name:
                    return entry
        return None

    def _apply_rule_parameter_mutation(self, config: dict[str, Any], mutation: RuleParameterMutation) -> None:
        entry = self._find_rule_entry(config, mutation.rule_name)
        if entry is None:
            raise ValueError(f"Unknown rule in simulation spec: {mutation.rule_name}")
        params = entry.setdefault("params", {})
        params[mutation.parameter] = mutation.new_value

    def _apply_rule_weight_mutation(self, config: dict[str, Any], mutation: RuleWeightMutation) -> None:
        if self._find_rule_entry(config, mutation.rule_name) is None:
            raise ValueError(f"Unknown rule in simulation spec: {mutation.rule_name}")
        weights = config.setdefault("weights", {})
        weights[mutation.rule_name] = mutation.new_weight

    def _apply_rule_toggle_mutation(self, config: dict[str, Any], mutation: RuleToggleMutation) -> None:
        entry = self._find_rule_entry(config, mutation.rule_name)
        if entry is None:
            raise ValueError(f"Unknown rule in simulation spec: {mutation.rule_name}")
        entry["enabled"] = mutation.enabled

    @staticmethod
    def _apply_partner_pool_mutation(snapshot: dict[str, Any], mutation: PartnerPoolMutation) -> None:
        partners = {p["partner_id"]: p for p in snapshot.get("partners", [])}

        for partner_id in mutation.remove:
            partners.pop(partner_id, None)

        for payload in mutation.modify:
            partners[payload.partner_id] = payload.model_dump()

        for payload in mutation.add:
            partners[payload.partner_id] = payload.model_dump()

        snapshot["partners"] = [partners[k] for k in sorted(partners)]

    @staticmethod
    def _diff_traces(original_trace: dict[str, Any], simulated_trace: dict[str, Any]) -> list[dict[str, Any]]:
        original_orders = {order["order_id"]: order for order in original_trace.get("orders", [])}
        simulated_orders = {order["order_id"]: order for order in simulated_trace.get("orders", [])}

        diff: list[dict[str, Any]] = []
        for order_id in sorted(set(original_orders) | set(simulated_orders)):
            original = original_orders.get(order_id)
            hypothetical = simulated_orders.get(order_id)
            old_partner = original.get("selected_partner_id") if original else None
            new_partner = hypothetical.get("selected_partner_id") if hypothetical else None
            changed = old_partner != new_partner

            diff.append(
                {
                    "order_id": order_id,
                    "changed": changed,
                    "original_partner": old_partner,
                    "hypothetical_partner": new_partner,
                    "original_reason": original.get("decision_reason") if original else None,
                    "hypothetical_reason": hypothetical.get("decision_reason") if hypothetical else None,
                    "original_order_trace": original,
                    "hypothetical_order_trace": hypothetical,
                }
            )

        return diff
