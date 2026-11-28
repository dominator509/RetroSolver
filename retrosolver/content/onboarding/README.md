# RetroSolver onboarding curriculum (text only, skin-neutral)

Audience: someone who has never played Texas hold'em. They open the app, know nothing, and need to be playing and learning within a few minutes without being lectured.

This is **copy and structure only**. It contains no frequencies, no EVs, no strategy numbers, no invented spots, and no solver output. Every teach-card template uses `{placeholder}` slots; the engine fills them from verified data it already owns. Nothing here decides an answer or grades a hand.

## Division of labor (per #185)

| Owner | Owns |
| --- | --- |
| Engine | spot selection, grading, the teach card's real values, streaks |
| Skin | art, animation, sound, verbs, UI chrome |
| **This content** | the **beats** — what is said, in what order, and when |

A beat is a sentence the learner reads or hears. The skin supplies the *voice*: a duel skin may say "One clean cut." where a space skin says "Direct hit." The beats below are written so they survive either.

## Voice rules

1. Plain words first. A term is introduced only on the screen where it is needed, never as a glossary dump.
2. One idea per screen. If a screen needs "and", it is two screens.
3. Never a number the engine did not supply. `{placeholder}` marks every slot.
4. No promises about winning. The goal stated to the learner is *understanding*, not profit.
5. Short sentences. A learner who is confused stops reading, not arguing.
6. Second person, present tense ("you hold", "you act"). No "one should".

## Files in this folder

| File | Contents |
| --- | --- |
| `README.md` | This guide: audience, rules, how the curriculum is assembled |
| `curriculum.json` | Ordered course map: units -> lessons -> screens, with recall questions |
| `01-basics.md` | Hand rankings, the flow of one hand, positions, what a "spot" is |
| `02-lessons.md` | The first three concept lessons in full prose |
| `teach-card-template.json` | Slot schema + text templates for the teach card, all placeholder |
| `editorial-checks.md` | Rules an audit can mechanically apply (no numbers, no invented claims) |

## Learning path

1. **Unit 0 — The table.** What the game is, what a hand is made of, how a hand ends. No decisions yet.
2. **Unit 1 — Hand rankings.** From strongest to weakest, taught by comparison, not by rank list.
3. **Unit 2 — The flow.** Blinds, cards dealt, the four betting rounds, showdown. Told as a story of one hand.
4. **Unit 3 — Positions.** Who acts first and why that matters. Named by seat, not by strategy.
5. **Unit 4 — Spots.** A spot is one decision point with the information you have. This is where practice begins.
6. **Lessons 1-3.** Value vs bluff; pot odds in plain words; why mixed plays exist. Each lesson ends in practice on real, engine-graded spots.

Units 0-4 are reading and recognition. Nothing is graded. Lessons 1-3 introduce grading, and a MISS always reveals the teach card.

## How a lesson screen is assembled

Each screen in `curriculum.json` has the same four fields:

- `beat`: the sentence(s) the learner sees.
- `visual`: a **slot name** the skin maps to its own art; never an asset path.
- `recall`: zero or one question, with answer key, used for the recall screen at lesson end.
- `gate`: `none` (no grading), `recognize` (tap the right thing, no score), or `solve` (engine-graded spot).

The engine reads `gate`; the skin reads `visual`; the copy is `beat`. A skin with no mapping for a `visual` slot is a build error, not a runtime fallback.

## What this content must never contain

- A frequency, an EV, a bet size, or any number presented as strategy.
- A named hand or board said to be "correct" to play a certain way.
- A claim about a real opponent, a real game, or winnings.
- Any third-party art, name, or trademark. All visual slots are abstract and named generically (`hand_back`, `felt`, `seat_ring`, `card_face_rank`).

Muse audits this card for poker correctness and for invented strategy claims. `editorial-checks.md` exists so that audit is not a matter of taste.
