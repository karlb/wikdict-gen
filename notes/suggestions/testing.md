# Testing

(The 2026-06-12 review's resolved items — the `test_entity` parse bug, the
`@skipUnless` data-test guard, closed connections, the e2e fixture, the
`gehen → åka` regression, the known-false-positive gold, and `parse.py`
edge-case coverage — have all shipped and were removed from this list.)

## Open

- **Promote confirmed FPs to `dont_expect` guards once a precision fix removes
  them.** The 32 high-confidence FPs (e.g. `de:Wahrheit→fact`, `de:Hund→bitch`,
  `fr-it:Gand→Guanto`, `fr-de:champ→Weide`, `en-sv:regret→sörja`) currently still
  ship, so they can't yet be passing absent-assertions; they wait on a net-positive
  scoring change (the fan-out penalty was measured net-negative — architecture.md
  #4 / scoring-improvement.md — so it isn't it).
