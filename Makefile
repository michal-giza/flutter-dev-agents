# Top-level Makefile — shortcuts for common dev/ops tasks.
# Most actual logic lives under packages/phone-controll/scripts.

.DEFAULT_GOAL := help
VENV ?= packages/phone-controll/.venv
PY := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

.PHONY: help
help:  ## Show this help.
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- dev loop --------------------------------------------------------

.PHONY: install
install:  ## Fresh-laptop bootstrap (brew adb, uv venv, uiautomator2 init).
	./scripts/install.sh

.PHONY: test
test:  ## Run hermetic unit + integration tests (fast: ~15s).
	cd packages/phone-controll && MCP_QUIET=1 $(PYTEST) -q --no-cov

.PHONY: test-fuzz
test-fuzz:  ## Run the Hypothesis dispatcher fuzz (~90s, opt-in).
	cd packages/phone-controll && MCP_QUIET=1 MCP_FUZZ=1 $(PYTEST) tests/unit/test_dispatcher_property.py -v --no-cov

.PHONY: test-real
test-real:  ## Run real-toolchain tests (requires flutter SDK + booted device).
	cd packages/phone-controll && MCP_REAL=1 MCP_REAL_DEVICE=1 $(PYTEST) tests/integration_real -v --no-cov

.PHONY: lint
lint:  ## Run ruff + show any issues.
	cd packages/phone-controll && $(VENV)/bin/ruff check src tests scripts

.PHONY: format
format:  ## Apply ruff autofixes.
	cd packages/phone-controll && $(VENV)/bin/ruff check --fix src tests scripts

# --- interactive inspection -----------------------------------------

.PHONY: inspect
inspect:  ## Launch MCP Inspector against our server (npx + Node required).
	@if [ ! -x $(PY) ]; then \
		echo "venv not built. Run 'make install' first."; exit 1; \
	fi
	@command -v npx >/dev/null || { echo "npx not on PATH. Install Node.js."; exit 1; }
	npx @modelcontextprotocol/inspector $(abspath $(PY)) -m mcp_phone_controll

.PHONY: serve-http
serve-http:  ## Run the HTTP adapter on localhost:8765.
	cd packages/phone-controll && $(VENV)/bin/mcp-phone-controll-http

# --- ops / release --------------------------------------------------

.PHONY: catalogue
catalogue:  ## Regenerate docs/tools.md from the live registry.
	cd packages/phone-controll && MCP_QUIET=1 $(PY) -m scripts.generate_tool_catalogue

.PHONY: contract
contract:  ## Refresh docs/tools-contract.json after tool changes.
	cd packages/phone-controll && UPDATE_CONTRACT=1 MCP_QUIET=1 $(PYTEST) tests/unit/test_tools_list_contract.py -q --no-cov

.PHONY: audit-artifacts
audit-artifacts:  ## Re-cap any oversized PNGs in ~/.mcp_phone_controll/sessions.
	cd packages/phone-controll && MCP_QUIET=1 $(PY) -m scripts.audit_artifact_dimensions \
		--root ~/.mcp_phone_controll/sessions --cap --max-dim 1600 --max-bytes-kb 250

.PHONY: sbom
sbom:  ## Generate a CycloneDX SBOM at /tmp/sbom.json.
	cd packages/phone-controll && $(VENV)/bin/cyclonedx-py environment .venv --of JSON -o /tmp/sbom.json
	@echo "SBOM written to /tmp/sbom.json ($(shell wc -c < /tmp/sbom.json) bytes)"

.PHONY: cve-scan
cve-scan:  ## Run pip-audit against the venv.
	cd packages/phone-controll && $(VENV)/bin/pip-audit \
		--progress-spinner=off --skip-editable --ignore-vuln PYSEC-2022-42969

.PHONY: docker-build
docker-build:  ## Build the runtime image.
	docker build -t mcp-phone-controll:dev packages/phone-controll/

.PHONY: docker-run
docker-run: docker-build  ## Build + run the image on localhost:8765.
	docker run --rm -p 8765:8765 -e MCP_QUIET=1 mcp-phone-controll:dev
