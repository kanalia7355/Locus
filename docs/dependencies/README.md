# Dependency inventory

The autonomous loop addition is managed separately by root `pyproject.toml` (runtime/development requirements and pinned build backend). Its installed runtime/build inventory is `loop-engine-licenses.json`. The original research-application inventories below remain historical application-bootstrap evidence, not a complete lock of the added engine.

The development environment uses exact versions in `backend/requirements.lock` and `frontend/package-lock.json`. Python metadata is recorded in `python-licenses.json`; npm lockfile license metadata, including optional platform packages, is recorded in `npm-licenses.json`. These are inventories, not legal clearance for production distribution. The application's own redistribution license remains undecided.

Core dependencies: FastAPI/Pydantic/React/Vite/TypeScript/Tailwind/Lucide use their packaged license metadata; Argon2id is supplied by argon2-cffi. Python's certificate bundle includes MPL-2.0 metadata. Keep upstream license notices when distributing dependencies or compiled bundles, and review missing/compound license expressions before production packaging.

Verification invokes pip check, pip-audit and npm audit rather than treating an inventory as proof of safety. The initial venv pip 24.3.1 was flagged and updated to 26.2.2 before recording the passing advisory scan.

## Superpowers evaluation

Bootstrap evaluated the official [Superpowers repository](https://github.com/obra/superpowers) and its [test-first](https://github.com/obra/superpowers/blob/main/skills/test-driven-development/SKILL.md), [verification](https://github.com/obra/superpowers/blob/main/skills/verification-before-completion/SKILL.md) and [debugging](https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md) source documentation. These workflows can be followed by a single implementer. Subagent-driven development, parallel dispatch and subagent-based skill testing conflict with this project's governance and were not selected. No Superpowers package, hook, telemetry companion or remote script was installed/executed. Existing project governance remains authoritative.

## Unenforced runtime controls

The active Codex tool surface does not provide a project hook to intercept agent-spawn calls or give reviewer-specific filesystem/network permissions. Installed Claude/Codex CLI executables do not establish those controls for this session. Only independent audit agents were invoked under explicit read-only instructions. The lack of technical enforcement is recorded as a risk; it is not disguised as a tested guardrail.
