"""Mission lifecycle and replay service connected to the in-process ULTRON engine (§3, §4, §7).

Uses `UltronAgentPort` (`UltronEngineAdapter` backed by the root `ultron` package by default,
or `StubUltronAgent` when explicitly injected in isolated unit tests) for mission creation,
task decomposition, dynamic hazard/target replanning, and full simulation execution.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import TYPE_CHECKING
import uuid

from core.errors import ResourceNotFoundError
from db.models import Event, Mission, ReasoningTrace, Task
from schemas.entities import (
    EventRead,
    MissionCreateRequest,
    MissionCreateResponse,
    MissionDetailRead,
    MissionReplayResponse,
    MissionReplayTimelineEntry,
    ReasoningTraceRead,
    TaskRead,
)
from schemas.enums import EventCategoryEnum, MissionStatusEnum
from services.event_service import EventService, event_service
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from ultron_stub import (
    ObservationPayloadStub,
    UltronAgentPort,
    UltronEngineAdapter,
    VehicleId,
)
from websocket.dashboard_gateway import DashboardGateway, dashboard_gateway

if TYPE_CHECKING:
    from services.vehicle_service import VehicleService

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class MissionService:
    """Adapter bridging the FastAPI service layer to ULTRON, SQLite, and DashboardGateway."""

    def __init__(
        self,
        agent: UltronAgentPort | None = None,
        *,
        gateway: DashboardGateway | None = None,
        events: EventService | None = None,
    ) -> None:
        self._agent: UltronAgentPort = (
            agent if agent is not None else UltronEngineAdapter()
        )
        self._gateway: DashboardGateway = gateway or dashboard_gateway
        self._events: EventService = events or event_service

    @property
    def agent(self) -> UltronAgentPort:
        return self._agent

    @property
    def gateway(self) -> DashboardGateway:
        return self._gateway

    def set_gateway(self, gateway: DashboardGateway) -> None:
        self._gateway = gateway
        self._events.set_gateway(gateway)

    async def _next_mission_id(self, session: AsyncSession) -> str:
        """Generate a sequential human-readable mission ID (M001, M002, ...) per §7."""
        count_result = await session.execute(select(func.count()).select_from(Mission))
        count = int(count_result.scalar_one() or 0)
        candidate_num = count + 1
        while True:
            candidate = f"M{candidate_num:03d}"
            exists = (
                await session.execute(select(Mission.id).where(Mission.id == candidate))
            ).scalar_one_or_none()
            if exists is None:
                return candidate
            candidate_num += 1

    async def create_mission(
        self,
        session: AsyncSession,
        request: MissionCreateRequest,
    ) -> MissionCreateResponse:
        """Create a mission via ULTRON, persist records, and broadcast updates (§4, §7)."""
        mission_id = await self._next_mission_id(session)
        now = datetime.now(timezone.utc)

        plan = await self._agent.create_simulated_mission(
            mission_id=mission_id,
            objective=request.objective,
        )

        mission_row = Mission(
            id=mission_id,
            objective=request.objective,
            status=plan.status,
            created_at=now,
            completed_at=None,
        )
        session.add(mission_row)

        task_rows: list[Task] = []
        for spec in plan.tasks:
            t_row = Task(
                id=spec.task_id,
                mission_id=mission_id,
                vehicle_id=spec.vehicle_id,
                type=spec.task_type,
                area=spec.area,
                target=spec.target,
                priority=spec.priority,
                status=spec.status,
            )
            session.add(t_row)
            task_rows.append(t_row)

        await session.commit()

        # Persist and broadcast initial mission event and ULTRON reasoning trace
        await self._events.record_event(
            session,
            mission_id=mission_id,
            category=EventCategoryEnum.MISSION,
            message=f"Mission {mission_id} created: {request.objective}",
            event_id=f"{mission_id}-EVT01",
            timestamp=now,
        )
        await self._events.record_reasoning_trace(
            session,
            mission_id=mission_id,
            trigger=plan.trigger,
            rationale=plan.rationale,
            resulting_task_ids=[t.id for t in task_rows],
            trace_id=f"{mission_id}-RT01",
            timestamp=now + timedelta(milliseconds=1),
        )

        detail = await self.get_mission(session, mission_id)
        await self._gateway.broadcast_mission_status(detail)

        return MissionCreateResponse(mission_id=mission_id)

    async def get_mission(
        self,
        session: AsyncSession,
        mission_id: str,
    ) -> MissionDetailRead:
        """Retrieve full mission state including ordered tasks (§7: GET /mission/{id})."""
        stmt = (
            select(Mission)
            .where(Mission.id == mission_id)
            .options(selectinload(Mission.tasks))
        )
        mission_row = (await session.execute(stmt)).scalar_one_or_none()
        if mission_row is None:
            raise ResourceNotFoundError("Mission", mission_id)

        sorted_tasks = sorted(mission_row.tasks, key=lambda t: (t.priority, t.id))
        return MissionDetailRead(
            id=mission_row.id,
            objective=mission_row.objective,
            status=MissionStatusEnum(mission_row.status),
            created_at=mission_row.created_at,
            completed_at=mission_row.completed_at,
            tasks=[TaskRead.model_validate(t) for t in sorted_tasks],
        )

    async def get_mission_replay(
        self,
        session: AsyncSession,
        mission_id: str,
    ) -> MissionReplayResponse:
        """Build ordered timeline of events and reasoning traces (§7: GET /mission/{id}/replay)."""
        mission_exists = (
            await session.execute(select(Mission.id).where(Mission.id == mission_id))
        ).scalar_one_or_none()
        if mission_exists is None:
            raise ResourceNotFoundError("Mission", mission_id)

        event_rows = (
            await session.execute(
                select(Event)
                .where(Event.mission_id == mission_id)
                .order_by(Event.timestamp.asc(), Event.id.asc())
            )
        ).scalars().all()

        trace_rows = (
            await session.execute(
                select(ReasoningTrace)
                .where(ReasoningTrace.mission_id == mission_id)
                .order_by(ReasoningTrace.timestamp.asc(), ReasoningTrace.id.asc())
            )
        ).scalars().all()

        entries: list[MissionReplayTimelineEntry] = []
        for e_row in event_rows:
            e_read = EventRead.model_validate(e_row)
            entries.append(
                MissionReplayTimelineEntry(
                    entry_type="event",
                    timestamp=e_read.timestamp,
                    event=e_read,
                    world_model_snapshot=None,
                )
            )

        for rt_row in trace_rows:
            rt_read = ReasoningTraceRead.model_validate(rt_row)
            entries.append(
                MissionReplayTimelineEntry(
                    entry_type="reasoning_trace",
                    timestamp=rt_read.timestamp,
                    reasoning_trace=rt_read,
                    world_model_snapshot={
                        "is_stub": self._agent.is_stub_implementation(),
                        "resulting_task_ids": list(rt_read.resulting_task_ids),
                    },
                )
            )

        entries.sort(
            key=lambda item: (
                item.timestamp,
                0 if item.entry_type == "event" else 1,
                item.event.id if item.event is not None else (
                    item.reasoning_trace.id if item.reasoning_trace is not None else ""
                ),
            )
        )
        return MissionReplayResponse(mission_id=mission_id, entries=entries)

    async def complete_mission(
        self,
        session: AsyncSession,
        mission_id: str,
    ) -> MissionDetailRead:
        """Complete a simulated mission, finalize tasks, persist audit records, and broadcast."""
        stmt = (
            select(Mission)
            .where(Mission.id == mission_id)
            .options(selectinload(Mission.tasks))
        )
        mission_row = (await session.execute(stmt)).scalar_one_or_none()
        if mission_row is None:
            raise ResourceNotFoundError("Mission", mission_id)

        now = datetime.now(timezone.utc)
        mission_row.status = MissionStatusEnum.COMPLETED.value
        mission_row.completed_at = now

        completed_task_ids: list[str] = []
        for task in mission_row.tasks:
            if task.status not in ("COMPLETED", "CANCELLED", "FAILED"):
                task.status = "COMPLETED"
            completed_task_ids.append(task.id)

        await session.commit()

        await self._events.record_event(
            session,
            mission_id=mission_id,
            category=EventCategoryEnum.MISSION,
            message=f"Mission {mission_id} completed ({len(completed_task_ids)} tasks finalized).",
            timestamp=now,
        )
        await self._events.record_reasoning_trace(
            session,
            mission_id=mission_id,
            trigger=f"SIMULATED_MISSION_COMPLETION:{mission_id}",
            rationale=(
                f"[SIMULATED_ULTRON_STUB] All assigned tasks for mission {mission_id} "
                f"('{mission_row.objective}') marked COMPLETED."
            ),
            resulting_task_ids=completed_task_ids,
            timestamp=now + timedelta(milliseconds=1),
        )

        detail = await self.get_mission(session, mission_id)
        await self._gateway.broadcast_mission_status(detail)
        return detail

    async def execute_ultron_simulation(
        self,
        session: AsyncSession,
        mission_id: str,
        vehicle_svc: VehicleService,
    ) -> MissionDetailRead:
        """Run the full ULTRON mission execution, hazard replanning, and target discovery pipeline."""
        from ultron.simulation.generator import SyntheticDataGenerator

        stmt = (
            select(Mission)
            .where(Mission.id == mission_id)
            .options(selectinload(Mission.tasks))
        )
        mission_row = (await session.execute(stmt)).scalar_one_or_none()
        if mission_row is None:
            raise ResourceNotFoundError("Mission", mission_id)

        # 1. Connect simulated vehicles and begin task execution
        await vehicle_svc.connect_vehicle(session, "SCOUT01")
        await vehicle_svc.connect_vehicle(session, "HAWK01")

        sim = vehicle_svc.simulator
        sim.scout.set_target_position(5.1, 3.0)
        sim.hawk.set_target_position(12.0, 4.0, alt=2.0)

        for _ in range(3):
            beats = await sim.step_all()
            for beat in beats.values():
                if beat is not None:
                    await vehicle_svc.ingest_telemetry(session, beat, force_persist=True)

        # 2. Generate synthetic hazard from HAWK01 using the friend's SyntheticDataGenerator
        generator = SyntheticDataGenerator(hazard_delay_sec=0.0)
        if isinstance(self._agent, UltronEngineAdapter):
            world = self._agent.world_model
        else:
            from ultron.schemas.world import MissionState, WorldModel

            world = WorldModel(
                mission=MissionState(id=mission_id, objective=mission_row.objective)
            )

        hazard_obs_list = generator.generate_telemetry(world)
        for u_obs in hazard_obs_list:
            src_vid = getattr(u_obs.source_vehicle, "value", str(u_obs.source_vehicle))
            vid_literal: VehicleId = "HAWK01" if src_vid == "HAWK01" else "SCOUT01"
            obs_stub = ObservationPayloadStub(
                observation_id=f"{mission_id}-OBS-{uuid.uuid4().hex[:6].upper()}",
                mission_id=mission_id,
                vehicle_id=vid_literal,
                obs_type=u_obs.event,
                confidence=u_obs.confidence,
                location_x=u_obs.location.x,
                location_y=u_obs.location.y,
                raw={
                    "temp_c": u_obs.temperature,
                    "gas_level": u_obs.gas_level,
                    "visual_evidence": u_obs.visual_evidence,
                },
            )
            await vehicle_svc.record_observation(session, obs_stub)

        # 3. If UltronEngineAdapter produced a replanned task set, persist & broadcast it
        if isinstance(self._agent, UltronEngineAdapter):
            replan = self._agent.last_replan_outcome
            if replan is not None and replan.replanned and replan.tasks:
                await session.execute(
                    delete(Task).where(Task.mission_id == mission_id)
                )
                new_task_ids: list[str] = []
                for spec in replan.tasks:
                    t_row = Task(
                        id=spec.task_id,
                        mission_id=mission_id,
                        vehicle_id=spec.vehicle_id,
                        type=spec.task_type,
                        area=spec.area,
                        target=spec.target,
                        priority=spec.priority,
                        status="IN_PROGRESS",
                    )
                    session.add(t_row)
                    new_task_ids.append(t_row.id)
                await session.commit()

                await self._events.record_event(
                    session,
                    mission_id=mission_id,
                    category=EventCategoryEnum.OBSERVATION,
                    message=f"ULTRON Replan Triggered: {replan.trigger_rationale}",
                )
                await self._events.record_reasoning_trace(
                    session,
                    mission_id=mission_id,
                    trigger=replan.trigger_rationale or "ULTRON_REPLAN",
                    rationale=replan.plan_rationale or "ULTRON replanned active tasks.",
                    resulting_task_ids=new_task_ids,
                )

        # 4. Step vehicles to target location (8.4, 2.2) and inject target discovery (red_package)
        sim.scout.set_target_position(8.4, 2.2)
        sim.hawk.set_target_position(14.0, 9.0, alt=2.2)
        for _ in range(3):
            beats = await sim.step_all()
            for beat in beats.values():
                if beat is not None:
                    await vehicle_svc.ingest_telemetry(session, beat, force_persist=True)

        target_obs_list = generator.generate_telemetry(world)
        for u_obs in target_obs_list:
            src_vid = getattr(u_obs.source_vehicle, "value", str(u_obs.source_vehicle))
            vid_target: VehicleId = "HAWK01" if src_vid == "HAWK01" else "SCOUT01"
            obs_stub = ObservationPayloadStub(
                observation_id=f"{mission_id}-OBS-{uuid.uuid4().hex[:6].upper()}",
                mission_id=mission_id,
                vehicle_id=vid_target,
                obs_type=u_obs.event,
                confidence=u_obs.confidence,
                location_x=u_obs.location.x,
                location_y=u_obs.location.y,
                raw={
                    "visual_evidence": u_obs.visual_evidence,
                    "label": u_obs.visual_evidence,
                },
            )
            await vehicle_svc.record_observation(session, obs_stub)

        # 5. Finalize mission as COMPLETED and broadcast
        return await self.complete_mission(session, mission_id)


mission_service = MissionService()
