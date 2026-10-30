# Operation Shadow — Backend & ULTRON Engine (`backend/`)

Self-contained FastAPI + SQLAlchemy 2.0 (`aiosqlite` in WAL mode) + WebSocket backend and in-process **ULTRON** autonomous planning/replanning engine for **Operation Shadow**.

## Directory Structure
- `fastapi/` — FastAPI application factory (`main.py`), REST routers (`api/`), WebSocket gateways (`websocket/`), SQLAlchemy 2.0 ORM (`db/`), Pydantic v2 contracts (`schemas/`), and domain services (`services/`).
- `ultron/` — In-process ULTRON agent state machine (`graph/`), Gemini LLM planner + fallback cache (`planner/`), safety validator (`safety/`), trigger evaluator & world model updater (`evaluator/`, `replanner/`, `world_model/`), and synthetic telemetry generator (`simulation/`).
- `ultron_stub/` — `UltronEngineAdapter` bridge (`ultron_bridge.py`), `VehicleAdapterPort`, `LockedRealVehicleAdapter`, and deterministic `MockFleetSimulator`.
- `configs/` — Scenario, geofence, vehicle, and simulation JSON configurations.
- `tests/` — Unified pytest suite (38 tests covering REST APIs, WebSockets, SQLite WAL persistence, emergency-stop fast path, and ULTRON planning/replanning).

## Commands
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run server (http://127.0.0.1:8000)
PYTHONPATH=fastapi:. uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Run unified test suite (38 tests) & strict mypy
.venv/bin/pytest -v
.venv/bin/mypy fastapi ultron_stub tests
```
