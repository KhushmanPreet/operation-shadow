# Operation Shadow — Frontend (`frontend/`)

Tactical military command-and-control (C2) React + TypeScript + Vite dashboard for **Operation Shadow**.

## Key Modules
- `src/App.tsx` — Global operations bar & 3-column tactical C2 grid.
- `src/api/client.ts` — Typed REST client consuming the FastAPI backend.
- `src/hooks/useDashboardSocket.ts` — Managed WebSocket hook (`/ws/dashboard`) with snapshot hydration and auto-reconnect resynchronization.
- `src/state/store.tsx` — Shared React Context + `useReducer` store with monotonic sequence guards.
- `src/components/` — `FloorMap`, `VehicleStatusCard`, `MissionPanel`, `CameraFeed`, `EventLog`, `ReasoningTracePanel`, `MissionReplayScrubber`, `SimulatedModeToggle`, and `EmergencyStopButton`.

## Commands
```bash
npm install
npm run dev          # Start dev server at http://127.0.0.1:5173
npm run typecheck    # Strict TypeScript check (tsc --noEmit)
npm test -- --run    # Run Vitest + React Testing Library suite (8 suites)
npm run build        # Production build
```
