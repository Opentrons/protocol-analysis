# Modernization Audit

Audit date: 2026-07-13. Repository state before modernization work.

## Current behavior (working)

- Two-service architecture: FastAPI API plus filesystem-queued processor daemon.
- Multi-version analysis via isolated `.venvs/` per configured robot version (6.2.1 through 8.8.0, `next`, `edge`).
- HTTP upload of protocol `.py`, optional labware `.json`, CSV/TXT, and RTP JSON.
- Async job model: submit, poll status, fetch analysis or simulation result.
- Processor heartbeat for `/ready` endpoint.
- Venv cache reuse with corruption detection (unusable Python, missing `opentrons`, version mismatch).
- CI runs ruff lint/format, unit/integration tests, and e2e tests with venv caching.
- Client library (`EvaluationClient`, `AsyncEvaluationClient`) used by `private-protocol-testing`.
- 56 fast tests passing; e2e covers multiple protocol scenarios.

## Obsolete or inconsistent behavior

| Item | Location | Issue |
|------|----------|-------|
| Package name | `pyproject.toml` | Named `protocol-analysis`; repo is `protocol-evaluation` |
| Python version docs | `README.md` vs `pyproject.toml` | README says `>=3.10`; project requires `3.12` |
| `run_client.py` | Referenced in Makefile, client README, copilot instructions | File does not exist |
| `make run-client` | `Makefile` | Broken target |
| Copilot instructions | `.github/copilot-instructions.md` | Duplicates README; `next` alpha version outdated (says 8.8.0a8, config has 8.8.0a13) |
| Version constant | `api/main.py` | Hardcoded `0.1.0` instead of package metadata |
| Generic description | `pyproject.toml` | Placeholder "Add your description here" |

## Broken or risky behavior

| Item | Risk | Details |
|------|------|---------|
| Internal `_analyze` API | High | Uses `opentrons.cli.analyze._analyze` directly; may break on Opentrons refactors. CLI `opentrons analyze` is the supported surface. |
| Synchronous subprocess | Medium | `subprocess.run` blocks processor during analysis; no cancellation cleanup. |
| No venv file locking | Medium | Concurrent processors or warm-up plus job processing could corrupt the same venv. |
| Hardcoded `edge` only | High | No configurable release branch, tag, or commit SHA. Mutable `edge` ref not resolved to immutable SHA. |
| `python_path` in results | Low | Environment-specific paths leak into `completed_*.json` metadata. |
| E2E uses bare `python` | Low | `make test-e2e` uses `python -c` instead of `uv run python`. |
| Build | Medium | `uv build` fails: no package discovery configuration, multiple top-level packages. |
| No type checking | Medium | No mypy in CI or Makefile. |
| Sequential job processing | Low | Single processor handles one job at a time; acceptable for now but limits throughput. |

## Missing test coverage

- Git ref resolution (branch, tag, commit, release branch)
- Environment identity generation for arbitrary refs
- Concurrent environment requests / locking
- Analysis timeout behavior (unit level)
- Subprocess crash handling
- Invalid analysis output parsing
- Error classification taxonomy
- Structured result serialization contracts
- Backward compatibility tests for API changes
- Processor analysis path (`_run_analysis`) unit tests
- CSV parameter extraction edge cases
- Force environment rebuild
- Integration tests that exercise real venv creation (marked slow)

## Dependency gaps

| Area | Current | Needed |
|------|---------|--------|
| Type checking | None | mypy + config |
| Build backend | Implicit setuptools legacy | Explicit hatchling or setuptools config |
| Dev deps | ruff, pytest, httpx | mypy, types for httpx if needed |
| Runtime | fastapi, python-multipart | May need git/python helpers for ref resolution (Stage 3) |

No unused runtime dependencies identified. `pandas==1.4.3` is pinned in every Opentrons venv for protocol compatibility.

## GitHub Actions gaps

| Item | Current | Opentrons pattern |
|------|---------|-------------------|
| Runner | `ubuntu-latest` | `ubuntu-24.04` |
| Action pinning | `@v5`, `@v7` tags | Immutable commit SHAs with version comments |
| Concurrency | None | `concurrency: group + cancel-in-progress` |
| Permissions | Default (broad) | Least privilege per job |
| Type check job | Missing | Add mypy job |
| Build verification | Missing | Add `uv build` |
| Security scanning | Missing | zizmor for `.github/**` changes |
| Dependabot | Missing | Python and GitHub Actions updates |
| Push trigger | PR only | Consider `push` to `main` |
| Test markers | All e2e in one job | Separate slow/integration markers |

Shared actions adopted from Opentrons monorepo patterns:

- `actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0` (v7.0.0)
- `astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990` (v8.3.2)
- `actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9` and `actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9` (v6.1.0)
- `actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` (v7.0.1)
- `zizmorcore/zizmor-action@192e21d79ab29983730a13d1382995c2307fbcaa` (v0.5.7)

Local composite actions (`.github/actions/setup`, `cache-venvs`) remain appropriate for this repo's venv caching needs.

## Documentation gaps

- No architecture doc (being added)
- README overstates simulation as a primary feature; engine focus should be analysis
- No development guide for adding Opentrons versions or Git refs
- No troubleshooting section
- No documented verification command sequence
- No Cursor rules (being added)
- RTP override behavior marked TODO in README but partially implemented

## Cursor rule gaps

- No `.cursor/rules/` for this repository
- `.github/copilot-instructions.md` exists but is not Cursor-native and contains stale details

## Backward-compatibility risks

| Change | Risk |
|--------|------|
| Rename `robot_version` to `opentrons_ref` | Breaks `private-protocol-testing` and existing clients |
| Remove `next` or version entries | Breaks callers depending on `/info` list |
| Change result JSON shape | Breaks downstream result parsers in private testing repo |
| Remove simulation | Would break callers using `result_type=simulation` |
| Resolve `edge` to SHA and change env identity | Existing cached venvs may need rebuild; behavior change for repeatability |

Recommended approach: add `opentrons_ref` as an alias while keeping `robot_version`; extend metadata with resolved SHA without removing existing fields.

## Intentionally out of scope

- Protocol Library downloading
- Snapshot management, PR automation, GitHub Pages
- AWS infrastructure
- Web frontend / JavaScript frameworks
- Corpus scheduling (lives in `private-protocol-testing`)
