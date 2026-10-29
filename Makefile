.PHONY: install install-frontend build-frontend test seed run dev

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	$(MAKE) install-frontend

install-frontend:
	cd frontend && npm install

build-frontend:
	cd frontend && npm run build

test:
	.venv/bin/pytest -q

seed:
	.venv/bin/python scripts/seed_demo_alerts.py

# Built SPA served by FastAPI on :8000
run: build-frontend
	.venv/bin/python -m backend.main

# API + Vite with proxy (see scripts/dev.sh)
dev:
	bash scripts/dev.sh
