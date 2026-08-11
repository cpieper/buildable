.PHONY: dev test check

dev:
	trap 'kill 0' EXIT; (cd backend && uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000) & (cd frontend && npm run dev -- --port 5173) & wait

test:
	cd backend && uv run pytest
	cd frontend && npm test

check:
	cd backend && uv run ruff check app tests
	cd frontend && npm run check
	cd frontend && npm run build
