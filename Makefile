.PHONY: setup
setup:
	uv sync --dev --frozen

.PHONY: teardown
teardown:
	uv venv --rm

.PHONY: test-unit
test-unit:
	uv run pytest tests/unit/ -v -m unit

.PHONY: test-integration
test-integration:
	uv run pytest tests/integration/ -v -m integration

.PHONY: test
test:
	uv run pytest -v --ignore=tests/e2e -m "not e2e and not slow"

.PHONY: test-all
test-all: verify test-e2e

.PHONY: format
format:
	uv run ruff check --fix . --exclude test-files
	uv run ruff format . --exclude test-files

.PHONY: lint
lint:
	uv run ruff check . --exclude test-files
	uv run ruff format --check . --exclude test-files

.PHONY: typecheck
typecheck:
	uv run mypy api evaluate client run_processor.py run_client.py

.PHONY: build
build:
	uv build

.PHONY: verify
verify: lint typecheck test build

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
	uv run python run_client.py test-files/simple/Flex_S_v2_24_P50_PAPI_Changes.py

.PHONY: test-edge
test-edge:
	PROTOCOL_EVALUATION_ENABLE_EDGE=1 uv run pytest tests/integration/test_edge_analysis.py -v -m slow

.PHONY: verify-edge
verify-edge:
	rm -rf .venvs/opentrons-edge
	$(MAKE) test-edge

	@echo "Starting services for e2e tests..."
	@make clean-storage > /dev/null 2>&1
	@PORT=$$(uv run python -c "import socket; s=socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1]); s.close()"); \
	BASE_URL=http://127.0.0.1:$$PORT; \
	echo "Using $$BASE_URL"; \
	PYTHONUNBUFFERED=1 uv run uvicorn api.main:app --host 127.0.0.1 --port $$PORT > e2e-api.log 2>&1 & echo $$! > e2e-api.pid; \
	PYTHONUNBUFFERED=1 uv run python run_processor.py > e2e-processor.log 2>&1 & echo $$! > e2e-processor.pid; \
	sleep 3 && \
	echo "Running e2e tests..." && \
	PROTOCOL_EVALUATION_BASE_URL=$$BASE_URL uv run pytest tests/e2e/ -v -m e2e; \
	TEST_EXIT=$$?; \
	echo "Stopping services..."; \
	kill $$(cat e2e-api.pid 2>/dev/null) 2>/dev/null || true; \
	kill $$(cat e2e-processor.pid 2>/dev/null) 2>/dev/null || true; \
	exit $$TEST_EXIT
