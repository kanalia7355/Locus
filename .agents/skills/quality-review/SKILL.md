---
name: quality-review
description: Independently review task diff, regression evidence and Goal alignment in the loop's read-only review context.
---
Compare actual diff with immutable acceptance and allowed scope. Inspect meaningful test coverage, unavailable/skipped required checks and any changed tests or verification scripts as separate review surfaces. Report unsupported claims and regressions with reproducible evidence. Emit the review schema; do not edit, execute external mutations, spawn agents or approve your own implementation. Passing local checks never substitutes for required CI or trusted merge review.
