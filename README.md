# RetroSolver pipeline

Deterministic poker-solver data pipeline: batch spot generation, solver-output extraction, and pack validation. Every strategy number in a pack comes from a real solver output file; nothing is LLM-written. Packs are tagged `single_source` until an independent validator recomputes them from committed raw outputs.

## License and solver posture

- The code in this repository is the project's own. No solver code or solver binaries are committed here, ever.
- Solvers run as separate internal, offline data-generation tools under their own licenses (TexasSolver: AGPL-3.0; donksolver: MIT). They are never distributed, never embedded in any shipped artifact, and never network-served; only their computed output data flows through this pipeline.
- Generated strategy data is data, not solver code. Downstream commercial use of a solver's output should be confirmed with that solver's vendor.

---
# RetroSolver data pipeline (lane 2)

These are Python 3 scripts that use only the standard library. They take Instinct's curated spot list, turn it into TexasSolver CLI batches, and pack the solver results into hash-pinned spot packs.

**Provenance rule:** these scripts move and validate solver output. They never create strategy content. Every frequency and EV in a pack is copied from a TexasSolver output file. A spot with anything missing is rejected and logged, never filled in. The only numbers in this folder that look like strategy are the unit-test fixtures in `tests/synthetic.py`. They are labeled SYNTHETIC and carry a marker that makes the pipeline refuse to ship them.

## Files

| File | Purpose |
|---|---|
| `batch_generate.py` | Turns a spot list (JSON or CSV) into a batch folder: `manifest.json`, `run_all.bat`, `run_all.sh` and `spots/<id>/input.txt`. It has a `--dry-run` mode and never overwrites anything. |
| `extract_pack.py` | Turns a solved batch folder into `PACK.json` plus `PACK.json.rejections.jsonl`. |
| `verify_pack.py` | Checks a pack's schema, required fields and `pack_hash`. Exits 1 on failure. An independent validator is the independent validator. |
| `retrosolver_pipeline/spotlist.py` | Spot-list validation and normalization, CSV parsing, and rendering of TexasSolver command files. |
| `retrosolver_pipeline/extract.py` | Parses solver output and runs the reject rules. |
| `retrosolver_pipeline/pack.py` | Spot-pack checks and the pack hash. |
| `retrosolver_pipeline/canonical.py` | RFC 8785 (JCS) canonical JSON and SHA-256. |
| `schemas/spot_list.schema.json`, `schemas/spot_pack.schema.json` | JSON Schema documentation for both formats. The Python code enforces them. |
| `samples/sample_spots_3.json` | Three sample spots (flop, turn, river). These are inputs only, and the ranges are placeholders. |
| `logs/dryrun_sample_3.log` | Dry-run log of the generator on the 3-spot sample. |
| `logs/box_e2e_real_solver_3.log` | Real end-to-end run on a build host with the official v0.2.0 Linux `console_solver`. All 3 spots converged and all 3 were rejected with `MISSING_EVS`. No strategy values are in the log. |
| `tests/` | `test_pipeline.py` (23 tests) and `synthetic.py` (synthetic fixtures). |

## How to run

```sh
# 0) tests (synthetic fixtures only)
python3 -m unittest discover -s tests -v

# 1) validate a list and preview the batch without writing anything
python3 batch_generate.py samples/sample_spots_3.json --out batch-001 --dry-run

# 2) write the batch (the folder must not already exist)
python3 batch_generate.py my_spots.json --out batch-001
#    for CSV input:
python3 batch_generate.py my_spots.csv --out batch-001 --solver-name TexasSolver --solver-version v0.2.0

# 3) solve (Instinct runs this on the solver PC)
batch-001\run_all.bat <console_solver.exe> <resources_dir>
#    POSIX: sh batch-001/run_all.sh /path/to/console_solver /path/to/resources

# 4) extract and verify
python3 extract_pack.py batch-001 --out pack-001.json --pack-id pack-001
python3 verify_pack.py pack-001.json
```

`extract_pack.py` exit codes:
- **0:** every spot was accepted.
- **2:** the pack was written, but some spots were rejected. See the `.rejections.jsonl` file.
- **1:** no pack was written.

## How the runner behaves

Each spot runs in its own folder. TexasSolver always writes its convergence log to `./tmp_log.txt`, so separate folders keep each spot's log apart.

For each spot, the runner records:
- `solve_stdout.log`
- `solver_exit_code.txt`
- `run_started_at.txt` and `run_finished_at.txt` (UTC)

If a spot folder already has any output, the runner skips it. Nothing is ever overwritten.

## TexasSolver facts the code relies on

These were checked against the v0.2.0 source and the official v0.2.0 release binaries.

- The CLI is `console_solver -i input.txt -r <resources> -m holdem`.
- Command lines are split on spaces and may have at most 2 tokens, so ranges can't contain spaces.
- `std::getline` keeps the `\r`, so `input.txt` must use LF line endings.
- There is no comment syntax.
- `set_accuracy` is the exploitability target in percent of the pot. It has no default, so it is always emitted.
- The v0.2.0 release binary has no `set_raise_limit` command.
- `tmp_log.txt` holds JSON lines: `{"iteration", "exploitibility" (sic), "time_ms"}`. stdout prints `Total exploitability X precent`. The extractor requires the final figure to be at or below the spot's `accuracy_target`, and it rejects the spot if the two sources disagree.
- Root decisions belong to player 1, which is OOP. Player 0 is IP.
- **The stock CLI `dump_result` exports strategy frequencies only, not EVs.** EVs are computed (`get_evs`/`dump_evs`), but only the GUI reads them. The extractor accepts EVs only in the `dump_evs` shape on each node (`node["evs"] = {"actions": [...], "evs": {combo: [...]}}`). Until an EV-bearing export exists, every stock CLI spot is rejected with `MISSING_EVS`.

## Reject codes

- `MISSING_INPUT`, `INPUT_TAMPERED`: the input file is missing or doesn't match its manifest hash.
- `SOLVER_FAILED`: the solver exited with a nonzero code.
- `MISSING_OUTPUT`, `BAD_OUTPUT_JSON`: the output file is missing or isn't valid JSON.
- `MISSING_CONVERGENCE`, `BAD_CONVERGENCE_LOG`, `CONVERGENCE_MISMATCH`, `NOT_CONVERGED`: no usable convergence figure, the two sources disagree, or the target wasn't met.
- `MISSING_FIELD`, `MISSING_FREQUENCIES`, `MISSING_EVS`: a required part of the solver output is absent.
- `ACTION_MISMATCH`, `EV_COMBO_MISMATCH`: actions or combos don't line up between strategy and EVs.
- `BAD_VECTOR`, `BAD_FREQUENCY`: a value is malformed, or frequencies don't sum to 1.
- `BAD_COMBO`: a combo is malformed or overlaps the board.
- `UNEXPECTED_ROOT`: the root node isn't OOP.
- `BAD_RUN_DATE`: the run date can't be read.
- `SYNTHETIC_DATA`: the output is a synthetic test fixture.

## Pack hash

`pack_hash` is the SHA-256 hex digest of the RFC 8785 (JCS) canonical JSON of the whole pack, with the `pack_hash` key removed. JCS sorts keys, uses no whitespace and formats numbers the way ECMAScript does, so the TypeScript loader  can recompute it byte for byte. The Python number formatter was cross-checked against Node.js on about 40,000 random doubles. Each spot also stores its `input_sha256` and `output_sha256`.
