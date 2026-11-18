# Spot packs v2: a consumer guide

A v2 pack is a JSON document containing one or more solver spots. It records the setup, solver output references, strategy frequencies, convergence evidence, and integrity hashes needed to inspect and verify those spots. The format identifier is `retrosolver.spot_pack.v2`.

## Check a pack first

From the repository root, run:

```sh
python3 verify_pack.py path/to/pack.json
```

A successful check exits with status `0` and prints the pack identifier, EV mode, spot count, and computed pack hash. A failed check exits with status `1` and prints an `[invalid]` message. The command runs this repository's v2 checks; it does not perform the separate independent validation represented by the `verification` field.

The `--allow-synthetic` option is intended for test data only. Do not use it to make test data suitable for release.

## Read the pack-level fields

| Field | What it tells you |
| --- | --- |
| `schema` | The format identifier. For this format it is `retrosolver.spot_pack.v2`. |
| `pack_id` | The pack's identifier. |
| `created_at` | When the pack was created. |
| `generator` | The generator name and version. |
| `solver` | The solver name and version used for the pack; each spot must identify the same solver. |
| `ev_mode` | Whether per-action EVs are available; see [Frequencies and EVs](#frequencies-and-evs). |
| `source_sha256` | A SHA-256 digest of the primary source file: the batch manifest for TexasSolver or the raw dump for donksolver. |
| `spot_count` | The number of entries in `spots`; it must match the array length. |
| `spots` | The spots contained in the pack. |
| `hash` | Hash metadata. The committed packs describe SHA-256 over RFC 8785 JCS canonical JSON. |
| `pack_hash` | The pack's SHA-256 digest over the canonical JSON representation with the `pack_hash` field removed. It detects changes to the pack contents. |
| `contains_synthetic_test_data` | The schema declares this field required with value `true`. See the important compatibility note below before relying on that rule. |

## Read a spot

Each entry in `spots` describes one solver situation. The schema requires these fields:

- `spot_id`, `street`, and `board` identify the spot. `street` is `preflop`, `flop`, `turn`, or `river`; `board` is empty preflop and contains the cards for a postflop street.
- `table` identifies the table format. `positions` describes the seat order and first actor preflop, or the in-position and out-of-position players postflop. `hand_keying` tells you whether hands are represented as `class169` classes or `combo` card combinations.
- `ranges`, `pot`, `stacks`, `rake`, `bet_sizes`, and `accuracy_target` describe the spot setup where present. `stacks` must include `effective_stack`; postflop spots need `ranges` for both `ip` and `oop`.
- `solver` and `solver_settings` identify the engine and settings for this spot. `run_date` and `run_date_source` record the run time and where that time came from.
- `convergence` records the solver's convergence evidence; the two supported kinds are described below.
- `decision_nodes` contains the strategy at each decision point. Each node has `path`, `actor`, `actions`, `frequencies`, and `evs`. An empty `path` (`[]`) means the root. The order of values in each frequency vector matches the order of strings in `actions`.
- `provenance` identifies the solver output, including `output_file` and `output_sha256`. `verification` is either `single_source` or `verified`.

A node may also include `solver_node_id` or `action_detail`. These are additional node information, not replacements for the required fields.

For preflop spots, `class169` keys cover the 169 starting-hand classes. For postflop spots, `combo` keys represent card combinations and cannot include cards on the board. Each `frequencies` vector gives the action proportions for that hand key and sums to approximately one.

## Frequencies and EVs

`ev_mode` applies to every decision node in the pack:

- `full` means each node's `evs` contains per-action EV vectors keyed to the same hand keys as `frequencies`.
- `frequencies_only` means every node has `evs: null`; the pack provides action frequencies, not per-action EVs.

Do not infer EVs from frequencies. If `evs` is null, the pack does not provide EV data for that node.

## Understand convergence

The `convergence.method` value determines what the convergence numbers mean. These two kinds are not interchangeable.

### `root_ev_standard_error`

This is for Monte Carlo solvers. It records `iterations`, the `per_seat` root EV and standard error values, `worst_seat`, `worst_seat_se_chips`, `root_pot_chips`, `worst_seat_se_pct_of_pot`, `se_scope`, and `source`. It describes statistical uncertainty in the recorded root-EV estimate, not exploitability. It does **not** claim that an accuracy target was met or provide an exploitability bound; the schema forbids `met_target` and `exploitability_pct_of_pot` in this convergence block.

Read `se_scope` before comparing standard errors. For example, the committed donksolver sample says its root EV and SE are estimated on the last log chunk's deals only and explicitly says that this is not an exploitability bound.

### `exploitability`

This is the convergence kind used for TexasSolver. It records `iterations`, `exploitability_pct_of_pot`, `accuracy_target_pct_of_pot`, `met_target`, and `source`. The schema requires `met_target` to be `true`; the implementation also checks that the reported exploitability is no greater than the target. This is an exploitability check against the stated target, not a guarantee about real-world outcomes.

A spot may also have `accuracy_target` in its setup. For an exploitability result, use the target recorded inside `convergence` to interpret `met_target`.

## Understand `verification`

`single_source` means the extracted spot has not yet passed an independent second-source check. `verified` is reserved for an independent validator; the extractor writes `single_source`. Running `verify_pack.py` checks the pack with the repository's own validator and does not change `verification` to `verified`.

## Worked example: TexasSolver turn sample

The committed `samples/v2/v2-sample-texassolver-turn.pack.json` has `pack_id` `v2-texassolver-soak-srp-btn-bb-a72r-tks`, one spot, and `ev_mode` `frequencies_only`. Its spot is on the turn with board `Ah`, `7c`, `2d`, `Ks`; the pot is `5.5` and the effective stack is `97.5`.

At the root decision node, `actor` is `oop` and `actions` are `CHECK`, `BET 4.000000`, and `BET 97.000000`. For the combo `2h2c`, the corresponding `frequencies` vector is `[0.8935220241546631, 0.10643766820430756, 4.034644371131435e-05]`; read each value against the action in the same position. `evs` is `null`, so this sample gives no per-action EVs.

Its convergence method is `exploitability`: `exploitability_pct_of_pot` is `0.48413708806037903`, `accuracy_target_pct_of_pot` is `0.5`, and `met_target` is `true`. Its `verification` is `single_source`, so a successful self-check does not mean it has been independently verified.

The committed donksolver preflop sample shows the other convergence kind: its `method` is `root_ev_standard_error`, its `worst_seat` is `BB`, and its `worst_seat_se_pct_of_pot` is `0.7355356127549643`. That percentage is a Monte Carlo standard-error figure, not an exploitability result or target-pass claim.

## Important compatibility note

The current schema and committed sample/verifier behavior disagree about `contains_synthetic_test_data`: the schema marks it required with the constant value `true`, but neither committed sample includes it, and `verify_pack.py` accepts both samples without that field. The implementation treats a present `contains_synthetic_test_data: true` or a spot marked `synthetic_test_data: true` as synthetic and rejects it unless `--allow-synthetic` is used. The repository verifier does not run a JSON Schema validator, so a successful command does not establish that a file conforms to every schema constraint. Until these files are aligned, read the schema and the validator behavior together; do not interpret verifier success as proof of schema conformance or independent verification.
