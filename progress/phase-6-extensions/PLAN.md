Plan for T-PH6-124 SecureContext clipboard restrictions

Changes:
1. ProvisionUser.tsx: Add guidance text to clipboard-unavailable fallback span
2. frontend/eslint.config.js: Fix no-restricted-properties with 6 SecureContext APIs, fix no-restricted-syntax selectors, add eslint-disable-next-line for api.ts crypto.randomUUID
3. ProvisionUser.test.tsx: Add afterEach to restore navigator.clipboard after each test
4. appearance.spec.ts: Existing test already covers SecureContext copy button behavior; verify it's adequate
5. Delete frontend/e2e/appearance.spec.ts.bak (drift copy)

Verification:
- npm --prefix frontend run test passes
- npm --prefix frontend run lint passes  
- npm --prefix frontend run test:appearance passes
- python scripts/secret_scan.py returns 0 findings