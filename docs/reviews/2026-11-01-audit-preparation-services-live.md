# Audit preparation service — live validation

Owner completed the audited one-shot recovery helper. Returned installed=true,
activated=false and app_services_preserved=true. Original audit artifact remains
`ed5564dc26d2a34b20790da9bea9c8983339ce9b24acdf5b46da5df58dc9a83c`;
its runtime source is 329494b72226bacec8094c78b9408c0b273dfbc2. Recovery helper
source is 25b2c10e4efe107cd3401893b603c8bbf7842331. Runtime was not recopied.

The operator then ran the authenticated fixed health/preflight endpoints. Live
responses established separate audit identity, absent App keys, denied App state
access, denied profile/log writes, oversized synthetic encrypted storage with
fresh-process read and a zero-tool inference request to the rejecting local
probe relay. No real model inference or existing operator credential was used.
Preflight configured only the dedicated account's approved crash-reporting policy;
subsequent health reported account_crash_reporting_disabled=true.

Stopped and started the audit service through its existing authorized SCM rights.
After restart, authenticated health and cached capability/key-metadata checks
passed without retransmitting any credential. Real auth_status remains false:
the dedicated account has not completed owner device enrolment. This does not
claim a real OAuth restart/read or model audit succeeded.

All three services are Running. Ordinary PowerShell Stop-Service requested
dependent-service enumeration beyond the intentionally restricted ACL and failed;
the fixed sc.exe stop/start operations succeeded using the already allowed rights.
No ACL was widened. No existing App service was stopped or reconfigured.

Owner-only private-console device authentication is the next dependent step.
Never collect its code or tokens in assistant tools. Protected Review/Controller
evidence wiring, App review/check publication, branch writer rules, exact-head
merge and the complete live loop remain unverified; preparation stays inactive.
