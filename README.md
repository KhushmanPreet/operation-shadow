# Operation Shadow

Operation Shadow is a local, indoor multi-vehicle mission-control system coordinating two autonomous vehicles (`SCOUT01` ground rover and `HAWK01` indoor drone) with an in-process **ULTRON** AI agent engine, a FastAPI + SQLite (WAL) + WebSocket backend, and a military tactical command-and-control React + TypeScript dashboard.

## Segregated Repository Architecture

The repository is cleanly segregated into three self-contained engineering tiers (`frontend/`, `backend/`, and `hardware/`) plus the specification suite (`docs/`):

```text
OperationShadow/
├── frontend/                              # Segregated React + TypeScript + Vite Tactical UI
│   ├── README.md
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx                        # Global operations bar & 3-column tactical C2 grid
│       ├── api/client.ts                  # Typed REST client for all backend endpoints
│       ├── components/                    # FloorMap, VehicleStatusCard, MissionPanel, CameraFeed,
│       │                                  # EventLog, ReasoningTracePanel, MissionReplayScrubber,
│       │                                  # SimulatedModeToggle, EmergencyStopButton
│       ├── hooks/useDashboardSocket.ts    # Managed WebSocket client + reconnect resynchronization
│       ├── state/store.tsx                # React Context + useReducer store with sequence guards
│       ├── styles/tactical.css            # Military tactical C2 design tokens & layout
│       └── __tests__/App.test.tsx         # Vitest + React Testing Library suite (8 suites)
├── backend/                               # Segregated FastAPI C2 Backend + In-Process ULTRON Engine
│   ├── README.md
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── fastapi/                           # FastAPI application modules (§3)
│   │   ├── main.py                        # FastAPI app, lifespan, /health, and /ws/dashboard
│   │   ├── api/                           # REST endpoints (/mission, /vehicle, /events, /map, /emergency-stop)
│   │   ├── websocket/                     # DashboardGateway & VehicleGatewayFastPath (§5, §10)
│   │   ├── db/                            # SQLAlchemy 2.0 ORM models & async WAL session lifecycle (§6)
│   │   ├── schemas/                       # Pydantic v2 domain, error, and WebSocket contracts (§5, §6, §7)
│   │   ├── core/                          # Settings, security, structured logging, error handlers
│   │   └── services/                      # MissionService, VehicleService, and EventService
│   ├── ultron/                            # In-Process ULTRON Agent System (§4, §26)
│   │   ├── planner/                       # Gemini LLM planner, structured schemas & fallback cache
│   │   ├── replanner/ & evaluator/        # Dynamic cross-vehicle replanning & trigger evaluation
│   │   ├── safety/                        # Deterministic safety validator & repair prompts
│   │   ├── world_model/ & memory/         # Shared World Model state & snapshot store
│   │   ├── simulation/                    # Synthetic telemetry & hazard/target generator
│   │   └── graph/                         # State machine workflow (plan -> validate -> assign -> evaluate)
│   ├── ultron_stub/                       # UltronEngineAdapter bridge, VehicleAdapterPort & simulator
│   ├── configs/                           # Scenario configs (mission_demo.json, geofence.json, vehicles.json)
│   └── tests/                             # Unified pytest suite (38 backend + ULTRON tests)
├── hardware/                              # Segregated Onboard Vehicle & Embedded Firmware Tier
│   ├── README.md
│   ├── scout/                             # SCOUT01 Raspberry Pi ground rover navigation & sensors
│   ├── hawk/                              # HAWK01 aerial drone flight interface & geofence safety
│   └── firmware/esp32/                    # ESP32 C++ PWM motor controller & hardware kill switch
├── docs/                                  # Complete Product & Architecture Specification Suite
│   ├── Operation Shadow — PRD v2.0.md
│   ├── Operation Shadow — TRD v2.0.md
│   ├── Operation Shadow — ULTRON Agent Architecture.md
│   ├── Operation Shadow — Backend & Frontend Architecture.md
│   ├── ui-design-spec.md
│   ├── implementation-plan.md
│   └── assumptions.md
└── Makefile                               # One-command runner (`make backend`, `make frontend`, `make test`)
```

## Quick Start

### 1. Start the Backend (`backend/`)
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=fastapi:. uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Start the Frontend (`frontend/`)
```bash
cd frontend
npm install
npm run dev
```
Open **`http://127.0.0.1:5173`** in your browser.

### 3. Run All Automated Tests & Type Checks
```bash
# Backend + ULTRON unified test suite (38 tests) & strict mypy (44 files)
cd backend
.venv/bin/pytest -v
.venv/bin/mypy fastapi ultron_stub tests

# Frontend TypeScript check, Vitest suite (8 tests), and production build
cd ../frontend
npm run typecheck
npm test -- --run
npm run build
```
