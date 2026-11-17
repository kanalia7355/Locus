# Skill: screen-invariants

**Trust level**: untrusted procedural reference. **Required permissions**: none.

## When this applies

A job changed anything under `frontend/`. Unit tests render components; they do
not lay out a page, so they cannot see that the top bar scrolled away, that text
ran off the right edge, or that a control became unreachable. Those are the
faults people actually report, and they are the ones nobody writes a test for.

## The rule

**A screenshot is not a check.** Nobody looks at it twice, and the second time
nobody notices the difference. Write the thing you noticed as an invariant a
machine can fail on, at the real viewport, in a real browser.

The suite is `frontend/e2e/appearance.spec.ts`, run by
`npm --prefix frontend run test:appearance`. The job loop runs it automatically
for any job touching `frontend/` (`jobloop/gates.py`, `frontend_gates`).

## What is already asserted

| Invariant | Why it exists |
|---|---|
| No page scrolls sideways at 1280 / 768 / 360 | the classic broken layout, invisible at one width |
| Nothing renders past the right edge | a long document name pushing controls out of reach |
| No error thrown by our own code while walking the screens | silent breakage that still "looks fine" |
| No emoji anywhere on screen | owner decision, 2026-11-17 |
| Every icon-only button has an accessible name | icons carry the main actions here |
| The top bar stays put while the conversation scrolls | measured broken 2026-11-17, `T-PH6-109` |
| The message box stays reachable | measured broken 2026-11-17, `T-PH6-111` |

## Adding one

1. **Reproduce first.** Drive the real screen and *measure* the fault — a
   bounding box, a scroll offset, a count. If you cannot measure it, you cannot
   assert it, and you do not yet understand it.
2. Write the assertion so it fails **now**, before any fix. An assertion that
   never failed has never been tested.
3. State the viewport. A layout fault usually lives at one width.
4. Put the measurement and the date in a comment. "Measured 2026-11-17: the top
   bar's y became -111" tells the next person what was true; "looks wrong" does not.

## Known-broken bugs

Mark a measured-but-unfixed fault with `test.fail()` and name the job that fixes
it. Playwright then **fails the test when it starts passing**, which is the
signal to delete the marker — in that same job, as part of its acceptance.

Never weaken an assertion to get a green gate. If a check is wrong, fix the
check and say why in the comment; if the screen is wrong, fix the screen.

## Two traps already hit

- **Browser noise is not an application error.** The console logs every non-2xx
  response as an error. A 401 before sign-in is the product working. Matching on
  "console error" alone fails forever and teaches everyone to ignore the gate.
  Filter to faults thrown by our own code.
- **A weak repro passes for the wrong reason.** The first "message box stays
  reachable" check sent one question, which did not make the page tall enough to
  scroll — so it passed while the bug was present. Build the state the fault
  needs, then assert.

## Operational note

The suite binds `127.0.0.1:8000` and `:5174`. A development server left running
on those ports fails the gate with a port conflict, not a layout finding. Stop
the development servers before an unattended loop run.
