# Coverage matrix v2

Config only. No solver was run to produce this directory. Ranges are copied verbatim from the official TexasSolver v0.2.0 release (`ranges/6max_range/`); SHA-256 of each source file is in `range_sources.json`.

## Grid and tiers

- 16 matchups x 3 depths (40, 100, 200bb) x 16 flop texture classes = 768 flop-root cells.
- T0: the existing 72-spot v1 draft (6 pot families x 12 flops at 100bb) in `spotlists/spotlist_v1_draft.json`. Production batches start here. T0 includes SB vs BB 3-bet pots, which are not one of the 16 brief matchups; that family stays on the T0 list and is not part of the 16x3x16 grid.
- T1: 16 matchups at 100bb x the first 8 texture classes (128 cells).
- T2: 40bb and 200bb x those same 8 classes (256 cells).
- T3: the remaining 8 classes across all matchups and depths (384 cells).

## Cell status

- 256 configured (all 16 matchups x 16 classes at 100bb).
- 512 NO_RANGE (every 40bb and 200bb cell). The bundled files do not state a stack depth; 100bb is the assumption already used by the v1 draft, and ranges were not copied across depths. No other verified range source was used.
- 0 UNCOMPARABLE. Configured spots are rake-free because TexasSolver v0.2.0 `console_solver` has no rake setting. That limitation is recorded rather than used to blank out the 100bb cells, which follow the same rake-free convention as the v1 draft.

## Canonical boards

One board per texture class, used in every matchup/depth cell of that class. v1 boards are reused when they satisfy the class definition; otherwise the first matching flop in a fixed card order (ranks 2-A, suits c-d-h-s, `itertools.combinations`). See `board_ledger.json`.

| Class | Tier group | Board | Key | Source |
|---|---|---|---|---|
| A-high dry | T1/T2 | `Ah,7c,2d` | `a72r` | v1_reuse |
| K-high dry | T1/T2 | `Kd,8s,3h` | `k83r` | v1_reuse |
| Q/J-high dry | T1/T2 | `Qh,Tc,5d` | `qt5r` | v1_reuse |
| mid dry | T1/T2 | `8h,3d,2c` | `832r` | lex_first |
| low dry | T1/T2 | `7s,5d,2c` | `752r` | v1_reuse |
| paired high | T1/T2 | `Tc,Td,2c` | `tt2tt` | lex_first |
| paired low | T1/T2 | `8d,8c,3h` | `883r` | v1_reuse |
| monotone high | T1/T2 | `Ks,Qs,4s` | `kq4m` | v1_reuse |
| monotone low | T3 | `4c,3c,2c` | `432m` | lex_first |
| two-tone A/K high | T3 | `Kd,3c,2c` | `k32tt` | lex_first |
| two-tone broadway | T3 | `Qd,Jd,2c` | `qj2tt` | v1_reuse |
| two-tone connected mid | T3 | `9h,8h,7c` | `987tt` | v1_reuse |
| rainbow connected mid | T3 | `Jd,9c,8h` | `j98r` | v1_reuse |
| rainbow connected low | T3 | `6h,4d,3c` | `643r` | v1_reuse |
| A-low wet | T3 | `Ad,3c,2c` | `a32tt` | lex_first |
| trips-board | T3 | `2c,2d,2h` | `222t` | lex_first |

## Matchups and pot math (100bb)

The bundled tree uses MP for the 6-max seat between UTG and CO. Brief names that say HJ use those MP files (`bundled_seat_map`).

| Matchup | Type | Path | Pot (bb) | Effective stack (bb) |
|---|---|---|---|---|
| UTG-BB | SRP | `UTG/2.5bb/BB/Call` | 5.5 | 97.5 |
| HJ-BB | SRP | `MP/2.5bb/BB/Call` | 5.5 | 97.5 |
| CO-BB | SRP | `CO/2.5bb/BB/Call` | 5.5 | 97.5 |
| BTN-BB | SRP | `BTN/2.5bb/BB/Call` | 5.5 | 97.5 |
| SB-BB | SRP | `SB/3.0bb/BB/Call` | 6.0 | 97.0 |
| CO-BTN | SRP | `CO/2.5bb/BTN/Call` | 6.5 | 97.5 |
| HJ-BTN | SRP | `MP/2.5bb/BTN/Call` | 6.5 | 97.5 |
| BB v BTN | 3BP | `BTN/2.5bb/BB/11.0bb/BTN/Call` | 22.5 | 89.0 |
| BB v CO | 3BP | `CO/2.5bb/BB/11.0bb/CO/Call` | 22.5 | 89.0 |
| BB v UTG | 3BP | `UTG/2.5bb/BB/11.0bb/UTG/Call` | 22.5 | 89.0 |
| SB v BTN | 3BP | `BTN/2.5bb/SB/11.0bb/BTN/Call` | 23.0 | 89.0 |
| BTN(3b) v CO | 3BP | `CO/2.5bb/BTN/8.5bb/CO/Call` | 18.5 | 91.5 |
| CO(3b) v HJ | 3BP | `MP/2.5bb/CO/8.5bb/MP/Call` | 18.5 | 91.5 |
| BTN v BB | 4BP | `BTN/2.5bb/BB/11.0bb/BTN/24.0bb/BB/Call` | 48.5 | 76.0 |
| CO v BTN | 4BP | `CO/2.5bb/BTN/8.5bb/CO/22.0bb/BTN/Call` | 45.5 | 78.0 |
| UTG v BB | 4BP | `UTG/2.5bb/BB/11.0bb/UTG/24.0bb/BB/Call` | 48.5 | 76.0 |

## Balance check

- T0: 6 families x 12 flops, 12 spots per family, 6 per flop, 36 SRP and 36 3-bet. Equal inside that list. The other 10 brief matchups and the 40/200bb depths are outside T0 by definition.
- T1: 128/128 configured. 8 spots per matchup, 16 per class, all at 100bb. No under-representation.
- T2: 256/256 NO_RANGE. Every matchup and both depths are equally empty of ranges.
- T3: 128 configured (100bb) and 256 NO_RANGE (40bb and 200bb). Every matchup has 8 configured spots (the 100bb half of its 24 cells). The 40bb and 200bb depths have zero configured spots; that is the missing range source, not a curation imbalance.

## Tree

Same light tree as the v1 draft: flop 33% plus all-in, turn 75% plus all-in, river 75% plus all-in, accuracy 0.5% of pot, max 300 iterations. The richer tree was memory-killed on a 15 GiB host with full ranges.

