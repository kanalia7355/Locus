---
name: local-ci-parity
description: Use before trusting a local check result, or when a local run is green while hosted CI is red (or the reverse), in this Windows checkout.
---

# Local / CI Parity (Locus, Windows checkout)

## Purpose and authority

Keep local verification evidence comparable to the hosted gate, and recognise the known ways this
Windows checkout produces a **false green**. This Skill is procedural knowledge only. It grants no
permission, authorizes no command, and does not transition a task or Phase. Hosted CI at the exact
head remains the authoritative gate (`docs/agent/CONSTRAINTS.md` §1), and
`verification-before-completion` still governs how claims are worded.

## Known divergences and how to neutralise them

1. **Scanner encoding (caused a repo-wide false green).**
   `detect_secrets` reads sources with the interpreter's default encoding and *silently skips files it
   cannot decode*. Under a Japanese Windows locale (cp932) every UTF-8 file containing Japanese text —
   most of this repository — was skipped, so `scripts/secret_scan.py` printed `0 findings` locally
   while the hosted run reported real findings. The script now forces `PYTHONUTF8=1` for the scanner
   subprocess. If you add another analyser that reads files itself, force UTF-8 the same way.
2. **Two virtualenvs.** `.venv` must be **Python 3.13** built exactly like CI
   (`python -m venv .venv`, `pip install -r backend/requirements.lock`, `pip install -e ".[dev]"`).
   `frontend/playwright.config.ts` and `frontend/e2e/a11y.spec.ts` resolve the backend interpreter from
   `.venv`, so a 3.10 or partially-broken `.venv` makes the whole Playwright suite unrunnable locally
   (symptoms seen: `ModuleNotFoundError: _cffi_backend`, `pydantic_core` import errors,
   `librt.internal` from mypy, `ImportError: cannot import name 'Self'`). `.venv313` exists for
   pytest-only runs; it is **not** what the browser E2E uses.
3. **`verify.py` budgets are tuned for Linux runners.** `scripts/verify.py` gives the Python test
   groups 120 s each; the same suites take roughly 200 s and 440 s on this machine, so a local
   `verify.py` run reports `timeout` (exit 124) even when every test passes. Run the groups directly
   for local evidence and quote the hosted run for the budgeted verdict:
   `pytest tests --ignore=tests/integration --ignore=tests/e2e -q` and `pytest tests/integration tests/e2e -q`.
4. **`verify.py` stops at the first failing check.** Checks run in a fixed order and the loop breaks on
   the first non-zero exit, so an early failure (for example the secret scan) means the later checks —
   frontend build and browser E2E — **did not run at all**. Never read "CI was green on E2E" from a run
   that failed earlier; check which checks actually executed.
5. **Line endings.** The working tree is CRLF and CI is LF. This did *not* affect secret scanning, but
   any check that matches end-of-line or compares bytes should be verified against LF content before
   trusting a local result.

## Procedure

1. Decide which gate the claim needs: a scoped local check, the full local suite, or the hosted exact-head run.
2. For local runs, confirm `.venv/Scripts/python.exe -V` reports 3.13 and `pip check` is clean first.
3. Run the directly-invoked groups (item 3) instead of the budgeted wrapper, plus
   `ruff check` / `ruff format --check` / `mypy backend/app`, `secret_scan.py`, and the frontend
   `typecheck` / `lint` / `test -- --run` / `build` / `test:e2e`.
4. When a local result contradicts the hosted result, treat the **divergence itself** as the defect to
   diagnose, and prefer a fix that makes the local gate as strict as the hosted one over a workaround.
5. Record in the task's `TEST` section which checks ran, on which head, and which environment, and name
   any check that was skipped, timed out, or could not run. Pre-existing failures must be identified by
   re-running the same check on the unmodified head before calling them pre-existing.

## Boundaries

- Do not weaken a check, an assertion, a scanner configuration, or a timeout to obtain agreement
  between environments (`docs/agent/CONSTRAINTS.md` §5-8).
- Do not write credentials into tests to make a fixture simpler; derive per-run values instead, so no
  credential literal is committed.
- Repairing the local environment (recreating `.venv`, reinstalling pinned wheels) touches no tracked
  file and no gate; it is not a substitute for the hosted run.
