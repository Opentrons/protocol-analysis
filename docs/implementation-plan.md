# Implementation Plan

Incremental modernization of `protocol-evaluation` into a reliable standalone analysis engine for `private-protocol-testing` and other callers.

## Stage 1: Discovery and audit (complete)

**Deliverables**

- [x] `docs/architecture.md`
- [x] `docs/modernization-audit.md`
- [x] `docs/implementation-plan.md`

**Outcome**: Documented current behavior, gaps, and risks before functional changes.

## Stage 2: Tooling and CI modernization (in progress)

**Goals**: Restore build, add type checking, align CI with Opentrons shared action patterns.

**Tasks**

- [ ] Fix `pyproject.toml`: metadata, build backend, package discovery (`api`, `evaluate`, `client`)
- [ ] Add `[tool.ruff]` and `[tool.mypy]` configuration
- [ ] Add `mypy` dev dependency
- [ ] Add Makefile targets: `typecheck`, `build`, `verify`
- [ ] Update `.github/workflows/test.yml`: pinned SHAs, `ubuntu-24.04`, concurrency, permissions
- [ ] Add typecheck and build jobs to CI
- [ ] Add `.github/workflows/gh-actions-security-zizmor.yaml`
- [ ] Add `dependabot.yml` for pip and github-actions
- [ ] Add pytest markers: `unit`, `integration`, `e2e`, `slow`
- [ ] Add `.cursor/rules/protocol-evaluation.mdc`
- [ ] Remove or fix broken `run_client.py` references

**Verification**

```bash
uv sync --dev --frozen
make verify   # lint + typecheck + test + build
```

## Stage 3: Git-ref and environment hardening

**Goals**: Configurable Opentrons source revision with immutable commit recording.

**Tasks**

- [ ] Introduce `OpentronsRef` model: requested ref, resolved SHA, ref type
- [ ] Add Git ref resolver (branch, tag, commit, release branch from config/env)
- [ ] Environment identity from `(python_version, resolved_sha, install_specs_hash)`
- [ ] Store environment manifest (`.venvs/{id}/manifest.json`)
- [ ] File locking during venv create/install (fcntl or filelock)
- [ ] `PROTOCOL_EVALUATION_FORCE_REBUILD` and `PROTOCOL_EVALUATION_RELEASE_BRANCH` config
- [ ] Extend `ENVIRONMENT_CONFIGS` or dynamic config builder for arbitrary refs
- [ ] Keep `robot_version` for PyPI releases; accept `opentrons_ref` as superset
- [ ] Unit tests with mocked git/subprocess

**API shape (backward compatible)**

```
POST /evaluate
  robot_version=8.7.0          # existing
  opentrons_ref=chore_release-x.y.z  # new, optional override
```

## Stage 4: Analysis execution modernization

**Goals**: Latest supported analysis path, async-safe subprocesses, structured errors.

**Tasks**

- [ ] Evaluate `opentrons analyze` CLI vs `_analyze`; migrate to supported entry point
- [ ] Replace `subprocess.run` with `asyncio.create_subprocess_exec` in async wrapper
- [ ] Configurable timeouts per request
- [ ] Subprocess cleanup on timeout/cancel
- [ ] Formal `AnalysisErrorCategory` enum
- [ ] Strip unstable paths from result metadata
- [ ] Optional concurrency limit for parallel jobs

## Stage 5: API and compatibility cleanup

**Goals**: Typed request/result models; optional in-process API.

**Tasks**

- [ ] Pydantic models for evaluation request, result, failure
- [ ] `evaluate_protocol()` async function wrapping core logic (for library use)
- [ ] Result metadata: requested ref, resolved SHA, engine version, Python version, env id
- [ ] Deprecation notes for any breaking changes
- [ ] Compatibility tests against `private-protocol-testing` client expectations

## Stage 6: Documentation and Cursor rules

**Goals**: Accurate README, development guide, troubleshooting.

**Tasks**

- [ ] Rewrite `README.md` per spec (scope, examples for edge/release/tag/commit)
- [ ] Add `docs/development.md`
- [ ] Update `client/README.md`
- [ ] Remove stale `.github/copilot-instructions.md` or merge into Cursor rules
- [ ] Document slow test invocation: `pytest -m e2e`

## Stage 7: Final verification

**Tasks**

- [ ] Full `make verify`
- [ ] E2E against `8.7.0`, `next`, and `edge` (if enabled)
- [ ] Example against configurable release branch (Stage 3)
- [ ] Example against pinned commit SHA (Stage 3)
- [ ] Confirm venv reuse across repeated runs
- [ ] Manual test with `private-protocol-testing` batch evaluator

## Recommended next pull request

**Title**: Tooling and CI modernization (Stage 2)

**Scope**

- Documentation (architecture, audit, plan)
- `pyproject.toml` build and lint/typecheck config
- Makefile `verify` target
- GitHub Actions pinned actions, concurrency, typecheck, build, zizmor, dependabot
- Cursor rules
- Pytest markers (no functional behavior change)

**Why first**: Restores `uv build`, establishes CI parity with Opentrons repos, and creates a verification baseline before Git-ref and analysis refactors in Stages 3 and 4.

## Pull request sequence (after Stage 2)

1. **Git-ref resolution and environment manifests** (Stage 3)
2. **Analysis execution and error taxonomy** (Stage 4)
3. **Typed API models and metadata** (Stage 5)
4. **Documentation completion** (Stage 6)
