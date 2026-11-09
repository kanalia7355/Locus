# GitHub Actions workflows

`quality.yml` verifies the application, `loop-ci.yml` verifies the Controller on
Linux/Windows and Python3.11/3.13, and `pr-title.yml` checks Conventional Commits.
Repository connection, CI execution and PR publication are authorized and have
been exercised. The previous unverified/unauthorized placeholder was historical.

The application verifier's Python check runs the full `tests` tree, including
engine tests; the separate entrypoints described in ADR0003 do not make their
Python test selections disjoint. This existing scope is retained. Integration/E2E
and all remaining tests now run in two processes under the same original 120-second
deadline, including coverage combination/reporting. Each run uses fresh separate
coverage files and combines them for the unchanged `backend/app` coverage target.
Missing data, either group's failure, or postprocessing failure blocks success.
The engine's Windows groups, shared 600 seconds, startup probes and check names
remain unchanged. Changing these scripts does not migrate frozen Loop approvals;
source/snapshot mismatches still require the existing exact approval procedure.

The operator requested workflow-level `contents: write` and
`pull-requests: write` in `loop-ci.yml`. Its `engine` verification job explicitly
overrides these to `contents: read` and `pull-requests: none`, and checkout does
not persist credentials. Untrusted PR code must not receive publication tokens.
The other two verification workflows remain read-only. A future trusted
publication job must declare its own permissions and receive independent review.
No Actions publication job is introduced by this permission declaration.

The current local Controller publishes through existing GitHub CLI keyring
authentication, not the Actions `GITHUB_TOKEN`. GitHub's setting that allows
Actions to create/approve PRs does not authorize the implementation agent to
approve its own review. The operator now requests conditional auto-merge after
making the repository public; see `../../docs/operations/SAFE_AUTO_MERGE_SETUP.md`.
Branch protection,
trusted independent-review publication and atomic merge-base enforcement remain
separate prerequisites for safe automatic merging.
