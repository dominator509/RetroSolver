"""Extractor/validator: TexasSolver output files -> spot-pack spots.

Every number placed in a spot comes from a solver output file:
  * action frequencies: output_result.json, node["strategy"]["strategy"][combo]
  * per-action EVs:     node["evs"]["evs"][combo] (the TexasSolver dump_evs() shape)
  * exploitability:     tmp_log.txt (JSON lines, key "exploitibility" sic) and/or
                        the "Total exploitability X precent" lines in solve_stdout.log
Anything missing or inconsistent rejects the whole spot; nothing is filled in.

NOTE (verified in TexasSolver v0.2.0 source and a real box run): the stock CLI
`dump_result` writes strategy only. EVs are computed internally (get_evs /
dump_evs) but only the GUI reads them. Stock CLI output is therefore rejected
with reason MISSING_EVS until an EV-bearing export is available.
"""
import datetime
import json
import math
import os
import re

from .canonical import file_sha256

FREQ_SUM_TOL = 1e-3
STDOUT_EXPL_RE = re.compile(r"Total exploitability\s+(-?[0-9.]+(?:[eE][-+]?[0-9]+)?)\s+precent")
COMBO_RE = re.compile(r"^[2-9TJQKA][cdhs][2-9TJQKA][cdhs]$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# TexasSolver numbering verified on a real v0.2.0 run: the root (first to act) is player 1 = OOP.
PLAYER_NAME = {1: "oop", 0: "ip"}


class Reject(Exception):
    def __init__(self, code, detail):
        super().__init__("%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


def _finite_list(v, n, what):
    if not isinstance(v, list) or len(v) != n:
        raise Reject("BAD_VECTOR", "%s: expected list of %d numbers" % (what, n))
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            raise Reject("BAD_VECTOR", "%s: non-finite or non-numeric value %r" % (what, x))
    return v


def _board_cards(spot):
    return set(spot["board"])


def parse_action_node(node, path, board, frequencies_only=False):
    """Return a decision-node record built only from solver data.
    frequencies_only: stock TexasSolver CLI output has no EVs; the
    node is kept with evs=None. Every other gate is unchanged. EVs are never filled in."""
    where = "node %s" % ("/".join(path) or "<root>")
    actions = node.get("actions")
    if not isinstance(actions, list) or not actions or not all(isinstance(a, str) for a in actions):
        raise Reject("MISSING_FIELD", "%s: no actions list" % where)
    player = node.get("player")
    if player not in PLAYER_NAME:
        raise Reject("MISSING_FIELD", "%s: player missing or not 0/1" % where)
    strat = node.get("strategy")
    if not isinstance(strat, dict) or not isinstance(strat.get("strategy"), dict) or not strat["strategy"]:
        raise Reject("MISSING_FREQUENCIES", "%s: no strategy block" % where)
    if strat.get("actions") != actions:
        raise Reject("ACTION_MISMATCH", "%s: strategy actions != node actions" % where)
    freqs = {}
    for combo, vec in strat["strategy"].items():
        if not COMBO_RE.match(combo):
            raise Reject("BAD_COMBO", "%s: combo key %r" % (where, combo))
        if combo[:2] in board or combo[2:] in board:
            raise Reject("BAD_COMBO", "%s: combo %s overlaps the board" % (where, combo))
        _finite_list(vec, len(actions), "%s freq %s" % (where, combo))
        if any(x < 0 or x > 1 for x in vec):
            raise Reject("BAD_FREQUENCY", "%s: %s frequency outside [0,1]" % (where, combo))
        if abs(sum(vec) - 1.0) > FREQ_SUM_TOL:
            raise Reject("BAD_FREQUENCY", "%s: %s frequencies sum to %r" % (where, combo, sum(vec)))
        freqs[combo] = vec
    evs_block = node.get("evs")
    if frequencies_only:
        if evs_block is not None:
            raise Reject("EVS_PRESENT_IN_FREQ_ONLY", "%s: output has an EV block; use the normal (full) mode" % where)
        return {"path": list(path), "player": PLAYER_NAME[player], "actions": list(actions),
                "frequencies": {c: freqs[c] for c in sorted(freqs)}, "evs": None}
    if not isinstance(evs_block, dict) or not isinstance(evs_block.get("evs"), dict):
        raise Reject("MISSING_EVS", "%s: no per-action EVs in solver output "
                     "(stock TexasSolver CLI dump_result does not export EVs)" % where)
    if evs_block.get("actions") != actions:
        raise Reject("ACTION_MISMATCH", "%s: evs actions != node actions" % where)
    evs = evs_block["evs"]
    if set(evs) != set(freqs):
        raise Reject("EV_COMBO_MISMATCH", "%s: EV combos differ from strategy combos" % where)
    for combo, vec in evs.items():
        _finite_list(vec, len(actions), "%s ev %s" % (where, combo))
    return {"path": list(path), "player": PLAYER_NAME[player], "actions": list(actions),
            "frequencies": {c: freqs[c] for c in sorted(freqs)},
            "evs": {c: evs[c] for c in sorted(evs)}}


def walk_street(root, board, frequencies_only=False):
    """All action nodes on the spot's own street (stops at chance nodes)."""
    if not isinstance(root, dict) or root.get("node_type") != "action_node":
        raise Reject("MISSING_FIELD", "root is not an action_node")
    out, stack = [], [(root, [])]
    while stack:
        node, path = stack.pop()
        out.append(parse_action_node(node, path, board, frequencies_only))
        kids = node.get("childrens", {}) or {}
        if not isinstance(kids, dict):
            raise Reject("MISSING_FIELD", "node %s: childrens is not an object" % "/".join(path))
        for act in sorted(kids, reverse=True):
            child = kids[act]
            if act not in node["actions"]:
                raise Reject("ACTION_MISMATCH", "child %r is not one of the node's actions" % act)
            if isinstance(child, dict) and child.get("node_type") == "action_node":
                stack.append((child, path + [act]))
    out.sort(key=lambda n: (len(n["path"]), n["path"]))
    return out


def read_convergence(spot_dir, accuracy_target):
    log_path = os.path.join(spot_dir, "tmp_log.txt")
    out_path = os.path.join(spot_dir, "solve_stdout.log")
    from_log = from_stdout = None
    iteration = None
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            rows = [ln.strip() for ln in f if ln.strip()]
        if rows:
            try:
                last = json.loads(rows[-1])
                from_log = float(last["exploitibility"])
                iteration = int(last["iteration"])
            except (ValueError, KeyError, TypeError):
                raise Reject("BAD_CONVERGENCE_LOG", "tmp_log.txt last line unparsable")
    if os.path.isfile(out_path):
        with open(out_path, "r", encoding="utf-8", errors="replace") as f:
            hits = STDOUT_EXPL_RE.findall(f.read())
        if hits:
            from_stdout = float(hits[-1])
    if from_log is None and from_stdout is None:
        raise Reject("MISSING_CONVERGENCE", "no exploitability figure in tmp_log.txt or solve_stdout.log")
    if from_log is not None and from_stdout is not None and abs(from_log - from_stdout) > 1e-4 * max(1.0, abs(from_log)):
        raise Reject("CONVERGENCE_MISMATCH", "tmp_log.txt says %r, stdout says %r" % (from_log, from_stdout))
    value = from_log if from_log is not None else from_stdout
    if not math.isfinite(value):
        raise Reject("MISSING_CONVERGENCE", "exploitability is not finite")
    if value > accuracy_target:
        raise Reject("NOT_CONVERGED", "final exploitability %r%% of pot > accuracy target %r%%" % (value, accuracy_target))
    conv = {"exploitability_pct_of_pot": value, "accuracy_target_pct_of_pot": accuracy_target,
            "met_target": True,
            "source": "tmp_log.txt" if from_log is not None else "solve_stdout.log"}
    if iteration is not None:
        conv["last_logged_iteration"] = iteration
    return conv


def read_run_date(spot_dir, output_path):
    for name in ("run_finished_at.txt",):
        p = os.path.join(spot_dir, name)
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
                v = f.read().strip()
            if not ISO_RE.match(v):
                raise Reject("BAD_RUN_DATE", "%s is not a UTC ISO-8601 time: %r" % (name, v))
            return v, name
    ts = datetime.datetime.fromtimestamp(os.path.getmtime(output_path), datetime.timezone.utc)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "output_file_mtime"


SYNTHETIC_MARKER = "_SYNTHETIC_TEST_FIXTURE"


def extract_spot(batch_dir, mspot, solver, allow_synthetic=False, frequencies_only=False):
    spot = mspot["spot"]
    spot_dir = os.path.join(batch_dir, "spots", spot["spot_id"])
    in_path = os.path.join(batch_dir, *mspot["input_file"].split("/"))
    if not os.path.isfile(in_path):
        raise Reject("MISSING_INPUT", "input.txt not found")
    if file_sha256(in_path) != mspot["input_sha256"]:
        raise Reject("INPUT_TAMPERED", "input.txt hash differs from manifest")
    code_path = os.path.join(spot_dir, "solver_exit_code.txt")
    if os.path.isfile(code_path):
        with open(code_path, "r", encoding="utf-8", errors="replace") as f:
            code = f.read().strip()
        if code != "0":
            raise Reject("SOLVER_FAILED", "console_solver exit code %s" % code)
    out_path = os.path.join(batch_dir, *mspot["expected_output_file"].split("/"))
    if not os.path.isfile(out_path):
        raise Reject("MISSING_OUTPUT", "%s not found" % mspot["expected_output_file"])
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            tree = json.load(f)
    except (ValueError, UnicodeDecodeError) as e:
        raise Reject("BAD_OUTPUT_JSON", str(e))
    if not isinstance(tree, dict):
        raise Reject("BAD_OUTPUT_JSON", "top level is not an object")
    if tree.get(SYNTHETIC_MARKER) and not allow_synthetic:
        raise Reject("SYNTHETIC_DATA", "output is a synthetic test fixture, not solver output")
    convergence = read_convergence(spot_dir, spot["accuracy_target"])
    nodes = walk_street(tree, _board_cards(spot), frequencies_only)
    if nodes[0]["player"] != "oop":
        raise Reject("UNEXPECTED_ROOT", "root decision is not OOP")
    run_date, run_date_source = read_run_date(spot_dir, out_path)
    rec = {
        "spot_id": spot["spot_id"],
        "positions": spot["positions"],
        "board": spot["board"],
        "street": spot["street"],
        "ranges": spot["ranges"],
        "pot": spot["pot"],
        "stacks": {"effective_stack": spot["effective_stack"]},
        "bet_sizes": spot["bet_sizes"],
        "accuracy_target": spot["accuracy_target"],
        "solver": dict(solver),
        "solver_settings": spot["solver_settings"],
        "run_date": run_date,
        "run_date_source": run_date_source,
        "convergence": convergence,
        "decision_nodes": nodes,
        # Tagging rule: only the independent validator may change this to "verified".
        "verification": "single_source",
        "provenance": {"input_sha256": mspot["input_sha256"],
                       "output_sha256": file_sha256(out_path),
                       "output_file": mspot["expected_output_file"]},
    }
    if tree.get(SYNTHETIC_MARKER):
        rec["synthetic_test_data"] = True
    return rec
