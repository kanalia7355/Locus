# Development-tool dependency mitigation — 2026-10-31

Final npm audit found GHSA-g3hv-75wg-m249 (CVE-2026-118764), moderate denial of
service through minimatch pattern preprocessing. The dependency tree used
minimatch 10.2.6 through ESLint/config-array and TypeScript-ESLint. npm audit
reported 11 affected dependency nodes, not 11 distinct root vulnerabilities.

Primary sources:
[GitHub advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249),
[upstream fixed release](https://github.com/isaacs/minimatch/releases/tag/v11.0.1).
The advisory lists versions below 11.0.1 as affected. Registry metadata verified
11.0.3 available and its Node engines `18 || 20 || >=22`, including local 22.16.

Latest parent releases still require minimatch 10.x, so an explicit exact npm
override selects 11.0.3. This is a deliberate transitive major override requiring
compatibility checks, not a claim of upstream semver support. No application
feature, test, lint rule or audit threshold changed. Installation used
`npm install --ignore-scripts --no-audit --no-fund`; no force-fix or downgrade.
The lockfile preserves integrity hashes and changed only minimatch plus its
newly required shared dependency. A hash-bound dependency Decision is pending
human review before integration; auto-merge stays disabled.

Validation after the override: ESLint passed, UI tests 4/4, production build
passed, Chromium E2E 5/5, fresh npm audit reported zero vulnerabilities, and
Secret Scan reported zero findings. The earlier full verifier's npm-advisories
result was failure and is retained as historical evidence; the affected frontend
checks were explicitly rerun after the dependency change.

Independent read-only dependency-only reviewer `/root/dependency_patch_audit`
found no concrete defect in the diff or weakened controls. The review inspected
dev-only scope, integrity hashes and ESM/CommonJS/named APIs used by consumers;
it did not run tests or use network/credentials. Parent ranges still exclude
11.x, so passing current checks is empirical compatibility, not universal
semver support. The pending dependency Decision remains. Remove the override
when parent packages adopt a supported fix.

GitHub's Python 3.11 engine job subsequently exposed runner-installed setuptools
79.0.1 in the environment-wide advisory audit (tests and Secret Scan passed).
The isolated build already required 84.2.1, but that did not upgrade the runner's
global package. The dev extra now also pins the same 84.2.1. This aligns the
build/dev tools instead of suppressing the advisory or excluding installed
packages from audit. Python 3.13 and the application CI had passed at that HEAD;
the corrected engine matrix requires a fresh current-head run.
The [setuptools advisory](https://github.com/advisories/GHSA-xmj3-9gf7-h52w)
lists 84.1.0 as fixed; the existing 84.2.1 build pin is newer. Local editable
installation and pip dependency consistency passed with the aligned pin.
Fresh local pip audit reported no known vulnerabilities (the unpublished local
engine is still explicitly skipped by PyPI lookup). The dependency-only
reviewer's first re-review found no defect in the aligned pin and confirmed
Python >=3.10 support and unchanged environment-wide audit controls. Fresh
remote matrix evidence is still required; both dependency Decisions remain.
