Skills Claude Code actually loads. A file here is invokable as `/<name>` only if
it carries YAML frontmatter with `name` and `description`; without that it is
ignored. `.agents/skills/` is a documentation registry that nothing reads at
runtime — see the note at the end of `.agents/skills/SKILLS_REGISTRY.md`.

Installed:

- `orchestrator-shift` — one turn on duty as the `jobloop` orchestrator. Opening
  checks (`scripts/shift_check.py`), which stops are judgements rather than loop
  defects, how a ruling is recorded in both places, and how to close a shift.

Evaluate Superpowers official skills before copying any of them here; do not
auto-install until version, license and compatibility are checked. Add
project-specific requirement-review, security-review and UI-quality skills only
when a real need appears, and only with an incident behind each rule.
