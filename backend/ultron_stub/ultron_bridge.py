"""In-process adapter connecting FastAPI backend services to the root `ultron` package.

Implements `UltronAgentPort` by delegating mission planning, safety validation,
world-model updates, and dynamic cross-vehicle replanning to `ultron.graph.workflow`,
`ultron.evaluator.updater`, and `ultron.evaluator.triggers`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import sys
from typing import Any, cast

# Ensure repository root is importable so `import ultron` resolves cleanly
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ultron.evaluator.updater import update_world_model
from ultron.graph.workflow import build_ultron_graph
from ultron.schemas.commands import Position2D, Position3D
from ultron.schemas.mission import MissionPlan, MissionStatus, VehicleID
from ultron.schemas.observations import StructuredObservation
from ultron.schemas.world import (
    ConnectionStatus,
    HawkState,
    MissionState,
    ScoutState,
    VehicleMode as UltronVehicleMode,
    WorldModel,
)
from ultron_stub.interface import (
    ObservationPayloadStub,
    SimulatedMissionPlanStub,
    SimulatedTaskSpecStub,
    UltronAgentPort,
    VehicleId,
    VehicleMode,
    WorldModelSnapshotStub,
)


@dataclass(frozen=True)
class UltronReplanOutcome:
    """Result of evaluating an inbound observation through the ULTRON replanner."""

    replanned: bool
    trigger_rationale: str | None
    plan_rationale: str | None
    tasks: list[SimulatedTaskSpecStub]


def _map_connection_to_ultron(conn: str) -> ConnectionStatus:
    if conn == "CONNECTED":
        return ConnectionStatus.ONLINE
    if conn == "UNKNOWN":
        return ConnectionStatus.UNKNOWN
    return ConnectionStatus.OFFLINE


def _map_obs_type_to_ultron_event(obs_type: str) -> str:
    lower = obs_type.lower()
    if "target" in lower or "package" in lower or "marker" in lower:
        return "target_detected"
    if "obstacle" in lower or "blocked" in lower:
        return "obstacle_blocked"
    return "possible_hazard"


class UltronEngineAdapter(UltronAgentPort):
    """Bridges the FastAPI C2 backend (`UltronAgentPort`) to the `ultron/` agent package."""

    def __init__(self) -> None:
        self._graph: Any = build_ultron_graph()  # type: ignore[no-untyped-call]
        self._active_mission_id: str | None = None
        self._world: WorldModel = WorldModel(
            mission=MissionState(
                id="M000",
                objective="Standby",
                status=MissionStatus.IDLE,
            ),
            vehicles={
                "SCOUT01": ScoutState(
                    mode=UltronVehicleMode.SIMULATED,
                    position=Position2D(x=0.0, y=0.0),
                    battery=100.0,
                    status="IDLE",
                    connection=ConnectionStatus.OFFLINE,
                ),
                "HAWK01": HawkState(
                    mode=UltronVehicleMode.SIMULATED,
                    position=Position3D(x=0.0, y=0.0, alt=0.0),
                    battery=100.0,
                    status="IDLE",
                    connection=ConnectionStatus.OFFLINE,
                ),
            },
        )
        self._state: dict[str, Any] = {
            "world": self._world,
            "proposed_plan": None,
            "validation_errors": [],
            "repair_prompt": None,
            "retry_count": 0,
            "trigger_rationale": None,
        }
        self._vehicles: dict[str, dict[str, Any]] = {
            "SCOUT01": {
                "id": "SCOUT01",
                "vehicle_type": "ground",
                "status": "IDLE",
                "connection": "DISCONNECTED",
                "mode": "simulated",
                "battery": 100.0,
                "position_x": 0.0,
                "position_y": 0.0,
                "position_alt": 0.0,
                "last_heartbeat": None,
            },
            "HAWK01": {
                "id": "HAWK01",
                "vehicle_type": "aerial",
                "status": "IDLE",
                "connection": "DISCONNECTED",
                "mode": "simulated",
                "battery": 100.0,
                "position_x": 0.0,
                "position_y": 0.0,
                "position_alt": 0.0,
                "last_heartbeat": None,
            },
        }
        self._observations: list[dict[str, Any]] = []
        self._unknown_transitions: list[tuple[VehicleId, datetime]] = []
        self._last_replan_outcome: UltronReplanOutcome | None = None

    @property
    def unknown_transitions(self) -> list[tuple[VehicleId, datetime]]:
        return list(self._unknown_transitions)

    @property
    def last_replan_outcome(self) -> UltronReplanOutcome | None:
        return self._last_replan_outcome

    @property
    def world_model(self) -> WorldModel:
        return self._world

    def is_stub_implementation(self) -> bool:
        """Return True when using cached offline fallback (no GEMINI_API_KEY), False when live."""
        return not bool(os.getenv("GEMINI_API_KEY"))

    async def get_world_model_snapshot(self) -> WorldModelSnapshotStub:
        return WorldModelSnapshotStub(
            active_mission_id=self._active_mission_id,
            vehicles={k: dict(v) for k, v in self._vehicles.items()},
            observations=[dict(obs) for obs in self._observations],
            is_stub=self.is_stub_implementation(),
        )

    def _convert_plan_tasks(
        self,
        mission_id: str,
        plan: MissionPlan,
        *,
        prefix: str = "T",
    ) -> list[SimulatedTaskSpecStub]:
        specs: list[SimulatedTaskSpecStub] = []
        for idx, task in enumerate(plan.tasks, start=1):
            veh_val = getattr(task.vehicle, "value", str(task.vehicle))
            vid: VehicleId = "HAWK01" if veh_val == "HAWK01" else "SCOUT01"
            prio_val = int(getattr(task.priority, "value", int(task.priority)))
            specs.append(
                SimulatedTaskSpecStub(
                    task_id=f"{mission_id}-{prefix}{idx:02d}",
                    vehicle_id=vid,
                    task_type=task.type.upper(),
                    area=task.area,
                    target=task.target or plan.objective[:120],
                    priority=max(1, min(100, prio_val)),
                    status="ASSIGNED",
                )
            )
        return specs

    async def create_simulated_mission(
        self,
        mission_id: str,
        objective: str,
    ) -> SimulatedMissionPlanStub:
        """Invoke the `ultron` state machine (`plan -> validate -> assign`) for a new mission."""
        self._active_mission_id = mission_id
        scout_info = self._vehicles["SCOUT01"]
        hawk_info = self._vehicles["HAWK01"]

        self._world = WorldModel(
            mission=MissionState(
                id=mission_id,
                objective=objective,
                status=MissionStatus.IN_PROGRESS,
            ),
            vehicles={
                "SCOUT01": ScoutState(
                    mode=UltronVehicleMode.SIMULATED,
                    position=Position2D(
                        x=float(scout_info["position_x"]),
                        y=float(scout_info["position_y"]),
                    ),
                    battery=float(scout_info["battery"]),
                    status=str(scout_info["status"]),
                    connection=_map_connection_to_ultron(str(scout_info["connection"])),
                ),
                "HAWK01": HawkState(
                    mode=UltronVehicleMode.SIMULATED,
                    position=Position3D(
                        x=float(hawk_info["position_x"]),
                        y=float(hawk_info["position_y"]),
                        alt=float(hawk_info["position_alt"]),
                    ),
                    battery=float(hawk_info["battery"]),
                    status=str(hawk_info["status"]),
                    connection=_map_connection_to_ultron(str(hawk_info["connection"])),
                ),
            },
        )
        self._state = {
            "world": self._world,
            "proposed_plan": None,
            "validation_errors": [],
            "repair_prompt": None,
            "retry_count": 0,
            "trigger_rationale": None,
        }

        result_state = cast(dict[str, Any], self._graph.invoke(self._state))
        self._state = result_state
        self._world = cast(WorldModel, result_state["world"])
        proposed_plan = cast(MissionPlan | None, result_state.get("proposed_plan"))

        if proposed_plan is None:
            from ultron.planner.cache import get_fallback_plan

            proposed_plan = get_fallback_plan(mission_id)

        task_specs = self._convert_plan_tasks(mission_id, proposed_plan, prefix="T")
        return SimulatedMissionPlanStub(
            mission_id=mission_id,
            objective=objective,
            status="ACTIVE",
            tasks=task_specs,
            trigger=f"ULTRON Planner invoked for mission {mission_id}",
            rationale=f"[ULTRON_ENGINE] {proposed_plan.rationale}",
            is_stub=self.is_stub_implementation(),
        )

    async def update_vehicle_state(
        self,
        vehicle_id: VehicleId,
        *,
        status: str | None = None,
        connection: str | None = None,
        mode: VehicleMode | None = None,
        battery: float | None = None,
        position_x: float | None = None,
        position_y: float | None = None,
        position_alt: float | None = None,
        last_heartbeat: datetime | None = None,
    ) -> None:
        entry = self._vehicles[vehicle_id]
        if status is not None:
            entry["status"] = status
        if connection is not None:
            entry["connection"] = connection
        if mode is not None:
            entry["mode"] = mode
        if battery is not None:
            entry["battery"] = battery
        if position_x is not None:
            entry["position_x"] = position_x
        if position_y is not None:
            entry["position_y"] = position_y
        if position_alt is not None:
            entry["position_alt"] = position_alt
        if last_heartbeat is not None:
            entry["last_heartbeat"] = last_heartbeat

        # Synchronize with ULTRON's WorldModel
        ultron_veh = self._world.vehicles.get(vehicle_id)
        if isinstance(ultron_veh, ScoutState):
            ultron_veh.position = Position2D(
                x=float(entry["position_x"]),
                y=float(entry["position_y"]),
            )
            ultron_veh.battery = float(entry["battery"])
            ultron_veh.status = str(entry["status"])
            ultron_veh.connection = _map_connection_to_ultron(str(entry["connection"]))
        elif isinstance(ultron_veh, HawkState):
            ultron_veh.position = Position3D(
                x=float(entry["position_x"]),
                y=float(entry["position_y"]),
                alt=float(entry["position_alt"]),
            )
            ultron_veh.battery = float(entry["battery"])
            ultron_veh.status = str(entry["status"])
            ultron_veh.connection = _map_connection_to_ultron(str(entry["connection"]))

    async def mark_vehicle_unknown(
        self,
        vehicle_id: VehicleId,
        *,
        detected_at: datetime,
    ) -> None:
        entry = self._vehicles.get(vehicle_id)
        if entry is not None:
            entry["connection"] = "UNKNOWN"
            entry["status"] = "UNKNOWN"
        ultron_veh = self._world.vehicles.get(vehicle_id)
        if ultron_veh is not None:
            ultron_veh.connection = ConnectionStatus.UNKNOWN
            ultron_veh.status = "UNKNOWN"
        self._unknown_transitions.append((vehicle_id, detected_at))

    async def record_observation(
        self,
        observation: ObservationPayloadStub,
    ) -> None:
        self._observations.append(
            {
                "id": observation.observation_id,
                "mission_id": observation.mission_id,
                "vehicle_id": observation.vehicle_id,
                "obs_type": observation.obs_type,
                "confidence": observation.confidence,
                "location_x": observation.location_x,
                "location_y": observation.location_y,
                "timestamp": observation.timestamp,
                "raw": observation.raw,
            }
        )

        # Merge observation into ULTRON WorldModel and evaluate replanning triggers
        raw_dict = observation.raw or {}
        ultron_obs = StructuredObservation(
            event=_map_obs_type_to_ultron_event(observation.obs_type),
            source_vehicle=(
                VehicleID.HAWK if observation.vehicle_id == "HAWK01" else VehicleID.SCOUT
            ),
            confidence=observation.confidence,
            location=Position2D(x=observation.location_x, y=observation.location_y),
            temperature=(
                float(raw_dict["temp_c"])
                if isinstance(raw_dict.get("temp_c"), (int, float))
                else None
            ),
            gas_level=(
                str(raw_dict["gas_level"])
                if isinstance(raw_dict.get("gas_level"), str)
                else None
            ),
            visual_evidence=(
                str(raw_dict.get("visual_evidence") or raw_dict.get("label") or observation.obs_type)
            ),
            timestamp=observation.timestamp.timestamp(),
        )
        self._world = update_world_model(self._world, ultron_obs)
        self._state["world"] = self._world

        # Ensure proposed_plan is populated so route_start routes to 'evaluate'
        if self._state.get("proposed_plan") is None:
            from ultron.planner.cache import get_fallback_plan

            self._state["proposed_plan"] = get_fallback_plan(observation.mission_id)

        result_state = cast(dict[str, Any], self._graph.invoke(self._state))
        self._state = result_state
        self._world = cast(WorldModel, result_state["world"])

        trigger_rationale = cast(str | None, result_state.get("trigger_rationale"))
        proposed_plan = cast(MissionPlan | None, result_state.get("proposed_plan"))
        if trigger_rationale and proposed_plan is not None:
            replanned_tasks = self._convert_plan_tasks(
                observation.mission_id,
                proposed_plan,
                prefix="RT",
            )
            self._last_replan_outcome = UltronReplanOutcome(
                replanned=True,
                trigger_rationale=trigger_rationale,
                plan_rationale=f"[ULTRON_REPLANNER] {proposed_plan.rationale}",
                tasks=replanned_tasks,
            )
        else:
            self._last_replan_outcome = UltronReplanOutcome(
                replanned=False,
                trigger_rationale=None,
                plan_rationale=None,
                tasks=[],
            )
