.PHONY: help backend frontend test typecheck build

help:
	@echo "Operation Shadow — Segregated Monorepo Commands:"
	@echo "  make backend    - Start FastAPI + ULTRON backend server on http://127.0.0.1:8000"
	@echo "  make frontend   - Start React tactical dashboard on http://127.0.0.1:5173"
	@echo "  make test       - Run all 38 backend/ULTRON tests and 8 frontend Vitest suites"
	@echo "  make typecheck  - Run strict mypy (backend) and tsc --noEmit (frontend)"
	@echo "  make build      - Build production frontend bundle"

backend:
	cd backend && PYTHONPATH=fastapi:. .venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest -v
	cd frontend && npm test -- --run

typecheck:
	cd backend && .venv/bin/mypy fastapi ultron_stub tests
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build
