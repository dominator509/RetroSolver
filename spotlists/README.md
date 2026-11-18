# Spot list v1, DRAFT (pipeline follow-on item 3). Config only, nothing solved.

- `build_spotlist_v1.py`: builds the list from the range files that ship in the official TexasSolver v0.2.0 release (`ranges/6max_range/...`). The ranges are copied verbatim, and each source file's SHA-256 is recorded in `range_sources`. No range, frequency or EV was written by hand.
- `spotlist_v1_draft.json`: 72 spots, 6 pot families × 12 flops, all at 100bb, rake-free.
  - SRP: BTN vs BB, CO vs BB, SB vs BB.
  - 3-bet pots: BB vs BTN, BB vs CO, SB vs BB.
  - Pot and stack come from the action line: open 2.5bb, or 3bb from the SB; 3-bet to 11bb, or 9bb from the BB vs SB; 0.5bb dead SB where it folded.
- `spotlist_v1_batch/`: `batch_generate.py` output, ready for whichever box runs the volume. It has 72 `input.txt` files, `manifest.json`, and `run_all.bat` / `run_all.sh`. The runners set `OMP_STACKSIZE=64M`.
- Tree, the same for all spots:
  - flop: 33% plus all-in
  - turn: 75% plus all-in
  - river: 75% plus all-in
  - accuracy 0.5% of pot, max 300 iterations
  - A richer tree (flop 33/75 plus raise 60, turn and river 50/100 plus raise 60, all-in) was OOM-killed on the 15 GB box with full ranges.

Open questions:
1. The bundled ranges don't state their stack depth. 100bb is assumed and needs confirming.
2. The card asks for 2-3 stack depths, but only one depth has sourced ranges. Other depths need a range source, and I won't invent ranges.
3. "Standard rake" can't be expressed: the TexasSolver CLI has no rake setting. wasm-postflop supports `rake_rate` and `rake_cap`.
4. The flop subset and the tree sizes are curation choices and need review.

## Coverage matrix v2

See `coverage_matrix_v2/` for the 16 matchup x 3 depth x 16 texture-class grid, tier manifests (T0-T3), the board ledger, and 100bb spot lists for T1 and T3. T0 is this v1 72-spot list. 40bb and 200bb cells are marked NO_RANGE because the bundled files do not state a depth.
