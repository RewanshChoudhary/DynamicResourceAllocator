from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from allocation.api.schemas import SimulationRequest
from allocation.simulation.counterfactual import CounterfactualSimulator, SimulationSpec
from allocation.persistence.config_versions import ConfigVersionStore
from allocation.persistence.repository import InputSnapshotRepository, ManifestRepository


router = APIRouter()


@router.post("/simulations")
def run_simulation(payload: SimulationRequest, request: Request):
    session = request.app.state.session_factory()
    try:
        try:
            spec = SimulationSpec.model_validate({"mutations": payload.mutations})
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid simulation spec: {exc}") from exc

        manifest_repo = ManifestRepository(session)
        input_repo = InputSnapshotRepository(session)
        config_store = ConfigVersionStore(session)
        simulator = CounterfactualSimulator(manifest_repo, input_repo, config_store)

        try:
            result = simulator.simulate(manifest_id=payload.manifest_id, spec=spec)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return result.to_dict()
    finally:
        session.close()
