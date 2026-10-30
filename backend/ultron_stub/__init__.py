"""Isolated ULTRON agent bridge, development stub, and deterministic vehicle simulator.

Provides explicit protocol interfaces, the live `UltronEngineAdapter` connecting
to the root `ultron` package, a locked real-hardware adapter guard, and a
deterministic mock vehicle simulator.
"""

from ultron_stub.interface import (
    CommandAcknowledgementStub,
    CommandAckStatus,
    EmergencyStopDispatchResultStub,
    EmergencyStopTarget,
    ObservationPayloadStub,
    SimulatedMissionPlanStub,
    SimulatedTaskSpecStub,
    TelemetryPayloadStub,
    UltronAgentPort,
    VehicleCommandEnvelopeStub,
    VehicleId,
    VehicleMode,
    VehicleType,
    WorldModelSnapshotStub,
)
from ultron_stub.simulator import (
    FaultInjectionConfig,
    MockFleetSimulator,
    MockVehicleAdapter,
    MockVehicleConfig,
)
from ultron_stub.stub_agent import StubUltronAgent
from ultron_stub.ultron_bridge import UltronEngineAdapter, UltronReplanOutcome
from ultron_stub.vehicle_adapter import (
    ClockPort,
    LockedRealVehicleAdapter,
    ManualClock,
    RealHardwareLockedError,
    SystemClock,
    VehicleAdapterPort,
    VehicleAdapterState,
)

__all__ = [
    "ClockPort",
    "CommandAckStatus",
    "CommandAcknowledgementStub",
    "EmergencyStopDispatchResultStub",
    "EmergencyStopTarget",
    "FaultInjectionConfig",
    "LockedRealVehicleAdapter",
    "ManualClock",
    "MockFleetSimulator",
    "MockVehicleAdapter",
    "MockVehicleConfig",
    "ObservationPayloadStub",
    "RealHardwareLockedError",
    "SimulatedMissionPlanStub",
    "SimulatedTaskSpecStub",
    "StubUltronAgent",
    "SystemClock",
    "TelemetryPayloadStub",
    "UltronAgentPort",
    "UltronEngineAdapter",
    "UltronReplanOutcome",
    "VehicleAdapterPort",
    "VehicleAdapterState",
    "VehicleCommandEnvelopeStub",
    "VehicleId",
    "VehicleMode",
    "VehicleType",
    "WorldModelSnapshotStub",
]
