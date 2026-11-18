"""SYNTHETIC test fixtures. Every number produced here is a made-up placeholder
for unit tests (0.25/0.75 splits, EVs 1.0/2.0/...). They are NOT solver output,
NOT poker strategy, and are marked with _SYNTHETIC_TEST_FIXTURE so the pipeline
refuses to ship them."""
import json
import os

SYNTHETIC = "_SYNTHETIC_TEST_FIXTURE"

SPOT_LIST = {
    "schema": "retrosolver.spot_list.v1",
    "list_id": "synthetic-unit-test-list",
    "solver": {"name": "TexasSolver", "version": "v0.2.0"},
    "spots": [{
        "spot_id": "synthetic-river-1",
        "positions": {"ip": "BTN", "oop": "BB"},
        "pot": 10, "effective_stack": 20,
        "board": "Qs,Jh,2h,8d,3c",
        "ranges": {"ip": "AA,KK", "oop": "JJ,66"},
        "bet_sizes": {"river": {"oop": {"bet": [50]}, "ip": {"bet": [50]}}},
        "accuracy_target": 0.5,
    }],
}

IP_COMBOS = ["AdAc", "AhAc", "KdKc", "KhKc"]
OOP_COMBOS = ["JdJc", "JsJc", "6d6c", "6h6c"]


def _node(player, actions, combos, children=None, evs=True):
    n = {"node_type": "action_node", "player": player, "actions": actions,
         "strategy": {"actions": actions,
                      "strategy": {c: [0.25, 0.75] if len(actions) == 2 else [1.0 / len(actions)] * len(actions)
                                   for c in combos}}}
    if evs:
        n["evs"] = {"actions": actions, "evs": {c: [float(i + 1) for i in range(len(actions))] for c in combos}}
    if children:
        n["childrens"] = children
    return n


def synthetic_output(evs=True):
    """SYNTHETIC tree shaped like TexasSolver dump_result (+ dump_evs blocks)."""
    root = _node(1, ["CHECK", "BET 5.000000"], OOP_COMBOS, {
        "BET 5.000000": _node(0, ["CALL", "FOLD"], IP_COMBOS, evs=evs),
        "CHECK": _node(0, ["CHECK", "BET 5.000000"], IP_COMBOS, {
            "BET 5.000000": _node(1, ["CALL", "FOLD"], OOP_COMBOS, evs=evs)}, evs=evs),
    }, evs=evs)
    root[SYNTHETIC] = True
    return root


def write_spot_outputs(batch_dir, spot_id, tree=None, log_values=(2.0, 0.4), stdout=True,
                       exit_code="0", finished_at="2026-01-01T00:00:00Z"):
    """Write SYNTHETIC solver output files into a generated batch folder."""
    d = os.path.join(batch_dir, "spots", spot_id)
    if tree is not None:
        with open(os.path.join(d, "output_result.json"), "x") as f:
            json.dump(tree, f)
    if log_values:
        with open(os.path.join(d, "tmp_log.txt"), "x") as f:
            for i, v in enumerate(log_values):
                f.write(json.dumps({"iteration": (i + 1) * 10, "exploitibility": v, "time_ms": 1}) + "\n")
    if stdout and log_values:
        with open(os.path.join(d, "solve_stdout.log"), "x") as f:
            f.write("SYNTHETIC\n" + "".join("Total exploitability %s precent\n" % v for v in log_values))
    if exit_code is not None:
        with open(os.path.join(d, "solver_exit_code.txt"), "x") as f:
            f.write(exit_code + "\n")
    if finished_at is not None:
        with open(os.path.join(d, "run_finished_at.txt"), "x") as f:
            f.write(finished_at + "\n")
