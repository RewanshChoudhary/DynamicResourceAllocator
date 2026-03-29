from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from allocation.domain.allocation import Allocation
from allocation.domain.enums import AllocationStatus
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import HardRule, ScoringRule


def build_aggregate_diagnostics(
    order_traces: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    hard_rule_names: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    hard_rule_elimination_counts: dict[str, int] = {
        rule_name: 0 for rule_name in (hard_rule_names or [])
    }
    unallocated_orders_by_failure_combination: dict[str, int] = {}
    allocated = 0
    unallocated = 0

    for order_trace in order_traces:
        selected_partner_id = order_trace.get("selected_partner_id")
        if selected_partner_id is None:
            unallocated += 1
        else:
            allocated += 1

        failure_codes: set[str] = set()

        for candidate in order_trace.get("candidates", []):
            first_failure = next(
                (
                    hard_result
                    for hard_result in candidate.get("hard_results", [])
                    if not hard_result.get("passed", False)
                ),
                None,
            )
            if first_failure is None:
                continue

            rule_name = first_failure.get("rule")
            if rule_name is not None:
                hard_rule_elimination_counts.setdefault(rule_name, 0)
                hard_rule_elimination_counts[rule_name] += 1

            failure_code = first_failure.get("failure_code")
            if selected_partner_id is None and failure_code:
                failure_codes.add(str(failure_code))

        if selected_partner_id is None:
            combination_key = "+".join(sorted(failure_codes)) if failure_codes else "NO_FAILURE_CODES"
            unallocated_orders_by_failure_combination[combination_key] = (
                unallocated_orders_by_failure_combination.get(combination_key, 0) + 1
            )

    return {
        "total_orders": len(order_traces),
        "allocated": allocated,
        "unallocated": unallocated,
        "hard_rule_elimination_counts": hard_rule_elimination_counts,
        "unallocated_orders_by_failure_combination": unallocated_orders_by_failure_combination,
    }


@dataclass(frozen=True)
class EvaluationTrace:
    orders: tuple[dict[str, Any], ...]
    scoring_weights: dict[str, float]
    initial_partner_loads: dict[str, int]
    fairness_escalation_event: dict[str, Any] | None
    conflict_resolution_report_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "orders": list(self.orders),
            "scoring_weights": self.scoring_weights,
            "initial_partner_loads": self.initial_partner_loads,
            "fairness_escalation_event": self.fairness_escalation_event,
            "conflict_resolution_report_hash": self.conflict_resolution_report_hash,
        }


@dataclass(frozen=True)
class PipelineResult:
    allocations: tuple[Allocation, ...]
    trace: EvaluationTrace
    aggregate_diagnostics: dict[str, Any]


class DeterministicAllocationPipeline:
    def __init__(self, hard_rules: list[HardRule], scoring_rules: list[ScoringRule]) -> None:
        self.hard_rules = [rule for rule in hard_rules if rule.enabled]
        self.scoring_rules = [rule for rule in scoring_rules if rule.enabled]

    def evaluate(
        self,
        orders: list[Order],
        partners: list[DeliveryPartner],
        scoring_weights: dict[str, float],
        partner_loads: dict[str, int] | None = None,
        fairness_escalation_event: dict[str, Any] | None = None,
        conflict_resolution_report_hash: str | None = None,
    ) -> PipelineResult:
        sorted_orders = sorted(orders, key=lambda x: x.order_id)
        sorted_partners = sorted(partners, key=lambda x: x.partner_id)
        local_partner_loads = dict(partner_loads or {})
        for partner in sorted_partners:
            local_partner_loads.setdefault(partner.partner_id, 0)
        initial_partner_loads = {partner_id: int(load) for partner_id, load in sorted(local_partner_loads.items())}

        allocations: list[Allocation] = []
        order_traces: list[dict[str, Any]] = []

        for order in sorted_orders:
            best_partner_id: str | None = None
            best_score = -1.0
            best_reason = "NO_ELIGIBLE_PARTNER"
            candidate_traces: list[dict[str, Any]] = []

            for partner in sorted_partners:
                hard_results: list[dict[str, Any]] = []
                hard_passed = True

                for hard_rule in self.hard_rules:
                    result = hard_rule.evaluate(order, partner)
                    hard_results.append(
                        {
                            "rule": hard_rule.rule_name,
                            "passed": result.passed,
                            "failure_code": result.failure_code,
                            "rationale": result.rationale,
                        }
                    )
                    if not result.passed:
                        hard_passed = False
                        break

                if not hard_passed:
                    candidate_traces.append(
                        {
                            "partner_id": partner.partner_id,
                            "hard_passed": False,
                            "hard_results": hard_results,
                            "scoring_results": [],
                            "weighted_score": None,
                        }
                    )
                    continue

                scoring_results: list[dict[str, Any]] = []
                weighted = 0.0
                context = {"partner_loads": dict(local_partner_loads)}

                for scoring_rule in self.scoring_rules:
                    result = scoring_rule.score(order, partner, context)
                    weight = float(scoring_weights.get(scoring_rule.rule_name, 0.0))
                    contribution = result.raw_score * weight
                    weighted += contribution
                    scoring_results.append(
                        {
                            "rule": scoring_rule.rule_name,
                            "raw_score": round(result.raw_score, 8),
                            "weight": round(weight, 8),
                            "weighted_contribution": round(contribution, 8),
                            "score_breakdown": result.score_breakdown,
                        }
                    )

                candidate_traces.append(
                    {
                        "partner_id": partner.partner_id,
                        "hard_passed": True,
                        "hard_results": hard_results,
                        "scoring_results": scoring_results,
                        "weighted_score": round(weighted, 8),
                    }
                )

                if weighted > best_score:
                    best_score = weighted
                    best_partner_id = partner.partner_id
                    best_reason = "BEST_WEIGHTED_SCORE"
                elif abs(weighted - best_score) < 1e-12 and best_partner_id is not None:
                    if partner.partner_id < best_partner_id:
                        best_partner_id = partner.partner_id
                        best_reason = "BEST_WEIGHTED_SCORE_TIE_BREAKER"

            if best_partner_id is None:
                allocations.append(
                    Allocation(
                        order_id=order.order_id,
                        partner_id=None,
                        status=AllocationStatus.UNALLOCATED,
                        reason="NO_PARTNER_PASSED_HARD_RULES",
                        weighted_score=None,
                    )
                )
            else:
                allocations.append(
                    Allocation(
                        order_id=order.order_id,
                        partner_id=best_partner_id,
                        status=AllocationStatus.ASSIGNED,
                        reason=best_reason,
                        weighted_score=round(best_score, 8),
                    )
                )
                local_partner_loads[best_partner_id] = local_partner_loads.get(best_partner_id, 0) + 1

            order_traces.append(
                {
                    "order_id": order.order_id,
                    "candidates": candidate_traces,
                    "selected_partner_id": best_partner_id,
                    "selected_weighted_score": round(best_score, 8) if best_partner_id else None,
                    "decision_reason": best_reason,
                }
            )

        trace = EvaluationTrace(
            orders=tuple(order_traces),
            scoring_weights={k: round(v, 8) for k, v in sorted(scoring_weights.items())},
            initial_partner_loads=initial_partner_loads,
            fairness_escalation_event=fairness_escalation_event,
            conflict_resolution_report_hash=conflict_resolution_report_hash,
        )
        aggregate_diagnostics = build_aggregate_diagnostics(
            order_traces=order_traces,
            hard_rule_names=[rule.rule_name for rule in self.hard_rules],
        )
        return PipelineResult(
            allocations=tuple(allocations),
            trace=trace,
            aggregate_diagnostics=aggregate_diagnostics,
        )
