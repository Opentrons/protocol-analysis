.PHONY: setup
setup:
	uv sync --dev --frozen

.PHONY: teardown
teardown:
	uv venv --rm

.PHONY: test-unit
test-unit:
	uv run pytest tests/unit/ -v

.PHONY: test-integration
test-integration:
	uv run pytest tests/integration/ -v

.PHONY: test
test:
	uv run pytest -v --ignore=tests/e2e

.PHONY: test-all
test-all: lint test test-e2e

.PHONY: format
format:
	uv run ruff check --fix . --exclude test-files
	uv run ruff format . --exclude test-files

.PHONY: lint
lint:
	uv run ruff check . --exclude test-files
	uv run ruff format --check . --exclude test-files

.PHONY: clean-storage
clean-storage:
	rm -rf storage/jobs/*

.PHONY: clean-venvs
clean-venvs:
	rm -rf .venvs

.PHONY: clean-e2e-artifacts
clean-e2e-artifacts:
	rm -f e2e-api.log e2e-processor.log e2e-api.pid e2e-processor.pid

.PHONY: clean
clean: clean-storage clean-venvs clean-e2e-artifacts

.PHONY: run-api
run-api:
	uv run fastapi dev api/main.py

.PHONY: run-processor
run-processor:
	uv run python run_processor.py

.PHONY: run-processor-once
run-processor-once:
	uv run python run_processor.py --mode once

.PHONY: run
run:
	@echo "Starting API server and processor..."
	@echo "API will be available at http://127.0.0.1:8000"
	@echo "Press Ctrl+C to stop both services"
	@(trap 'kill 0' SIGINT; \
		uv run fastapi dev api/main.py & \
		sleep 2 && \
		uv run python run_processor.py & \
		wait)

.PHONY: run-client
run-client:
	uv run python run_client.py

.PHONY: test-e2e
test-e2e:
	@echo "Starting services for e2e tests..."
	@make clean-storage > /dev/null 2>&1
	@PORT=$$(python -c "import socket; s=socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1]); s.close()"); \
	BASE_URL=http://127.0.0.1:$$PORT; \
	echo "Using $$BASE_URL"; \
	PYTHONUNBUFFERED=1 uv run uvicorn api.main:app --host 127.0.0.1 --port $$PORT > e2e-api.log 2>&1 & echo $$! > e2e-api.pid; \
	PYTHONUNBUFFERED=1 uv run python run_processor.py > e2e-processor.log 2>&1 & echo $$! > e2e-processor.pid; \
	sleep 3 && \
	echo "Running e2e tests..." && \
	PROTOCOL_EVALUATION_BASE_URL=$$BASE_URL uv run pytest tests/e2e/ -v; \
	TEST_EXIT=$$?; \
	echo "Stopping services..."; \
	kill $$(cat e2e-api.pid 2>/dev/null) 2>/dev/null || true; \
	kill $$(cat e2e-processor.pid 2>/dev/null) 2>/dev/null || true; \
	exit $$TEST_EXIT
