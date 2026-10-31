# GitHub Actions workflows

`quality.yml` verifies the application, `loop-ci.yml` verifies the Controller on
Linux/Windows and Python3.11/3.13, and `pr-title.yml` checks Conventional Commits.
Repository connection, CI execution and PR publication are authorized and have
been exercised. The previous unverified/unauthorized placeholder was historical.

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
approve its own review or lift the operator's merge hold. Branch protection,
trusted independent-review publication and atomic merge-base enforcement remain
separate prerequisites for safe automatic merging.
