.PHONY: install test run dev

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

test:
	.venv/bin/pytest -q

run:
	.venv/bin/python -m backend.main

# Stage 1: API only. Later stages will also start the Vite frontend here.
dev: run
