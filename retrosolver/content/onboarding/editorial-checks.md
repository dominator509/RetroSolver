# Editorial checks (mechanically applyable)

These are the rules Muse audits against. Each has a way to check it that does not depend on taste. `check_onboarding.py` in this folder implements the automatic ones; the rest are stated so a human reviewer can apply them the same way twice.

## Automatic (script-checkable)

| # | Rule | How checked |
| --- | --- | --- |
| A1 | No strategy numbers in prose | scan `*.md` body text for digit tokens adjacent to poker terms (`bb`, `%`, `ev`, `frequency`, `pot odds`, `x`) — flag for human read; the script lists every line containing a digit so the reviewer sees all of them |
| A2 | `curriculum.json` is valid JSON and matches the schema name | parse + `schema == "retrosolver.onboarding_curriculum.v1"` |
| A3 | `teach-card-template.json` is valid JSON, schema `retrosolver.teach_card_template.v1` | parse + schema check |
| A4 | Every `{slot}` in every template text is defined in `common_slots` or that template's `extra_phrase_sets` | script extracts `{...}` from each `text` and diffs against the union of defined names |
| A5 | No numeric slot except `cost_to_call` and `pot_size`, and only in `tc.l2` | script checks the numeric slot allow-list per template |
| A6 | Every screen's `gate` is one of `none`, `recognize`, `solve` | script checks the enum |
| A7 | Every screen `visual` value is a bare slot name (no `/`, no file extension) | script regex; a path here would mean art leaked into content |
| A8 | Every unit/lesson referenced in `order` exists | script set comparison |
| A9 | Every lesson `l1..l3` has `teach_card_template_id` pointing at an existing template | script cross-reference |
| A10 | Only `solve` screens appear in graded units, and no `solve` screen appears in an ungraded unit | script: ungraded unit must have zero `gate == "solve"` |

## Manual (reviewer applies the written rule)

| # | Rule |
| --- | --- |
| M1 | Poker correctness: every factual statement about the game (rankings, streets, blinds, positions, showdown) is true for no-limit Texas hold'em. |
| M2 | No invented strategy: no claim that a specific hand should be played a specific way outside a real, engine-graded spot. |
| M3 | No promise of winnings; the stated goal is understanding, not profit. |
| M4 | Teach card is never hidden on MISS/GLANCE (mirrors #185 §1). |
| M5 | Skin-neutral: no verb is hard-coded as the *only* verb; each beat survives a skin that renames the action words. |
| M6 | A miss is never mocked; the copy treats a miss as the lesson arriving. |
| M7 | Every term (blind, flop, button, spot, mixed) is introduced on the screen where it is first needed, not defined twice. |
| M8 | Original only: no third-party art, names, or trademarks; all visuals are abstract slots. |

## What "done" for an audit means

A card is auditable when: A1-A10 pass by script, and a human (or a different model) can read M1-M8 and find no violation without needing to consult anything outside this folder. If an audit needs an outside fact to judge a line, that line is too clever and should be rewritten plainer.
