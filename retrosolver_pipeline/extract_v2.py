"""spot_pack.v2 extractors. Nothing here creates strategy numbers.

* from_texassolver: reuses the v1 extractor gates (extract.extract_spot: input hash, exit code, frequency
  checks, exploitability log vs stdout, target met) and re-shapes the accepted record into v2.
* from_donksolver: reads a dump written by spikes/donksolver_v2/dump_preflop.py (raw donksolver API output)
  plus the solve's own run dir, re-hashes every solver file the dump names, and takes the convergence
  numbers (iterations, per-seat root EV and SE) straight from the solver's log.jsonl.
"""
import datetime
import json
import os

from .canonical import file_sha256
from .extract import Reject, extract_spot
from .pack_v2 import CLASSES, SEATS_6MAX


def from_texassolver(batch_dir, mspot, solver, frequencies_only=False, allow_synthetic=False):
    r = extract_spot(batch_dir, mspot, solver, allow_synthetic, frequencies_only)
    c = r["convergence"]
    conv = {"method": "exploitability", "exploitability_pct_of_pot": c["exploitability_pct_of_pot"],
            "accuracy_target_pct_of_pot": c["accuracy_target_pct_of_pot"], "met_target": c["met_target"],
            "source": c["source"]}
    if "last_logged_iteration" not in c:
        raise Reject("MISSING_CONVERGENCE", "no iteration count in tmp_log.txt")
    conv["iterations"] = c["last_logged_iteration"]
    spot = {
        "spot_id": r["spot_id"], "street": r["street"], "board": r["board"],
        "table": {"format": "6max", "note": "postflop heads-up spot reached from a 6-max preflop line"},
        "positions": r["positions"], "hand_keying": "combo", "ranges": r["ranges"], "pot": r["pot"],
        "stacks": r["stacks"], "bet_sizes": r["bet_sizes"], "accuracy_target": r["accuracy_target"],
        "solver": r["solver"], "solver_settings": r["solver_settings"], "run_date": r["run_date"],
        "run_date_source": r["run_date_source"], "convergence": conv,
        "decision_nodes": [{"path": n["path"], "actor": n["player"], "actions": n["actions"],
                            "frequencies": n["frequencies"], "evs": n["evs"]} for n in r["decision_nodes"]],
        "provenance": r["provenance"], "verification": "single_source",
    }
    if r.get("synthetic_test_data"):
        spot["synthetic_test_data"] = True
    return spot


def _config(text):
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def from_donksolver(dump_path, run_dir, spot_id, abstraction_path=None):
    with open(dump_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    if d.get("solver", {}).get("name") != "donksolver":
        raise Reject("BAD_OUTPUT_JSON", "dump is not a donksolver dump")
    names = {"config.txt": "config.txt", "log.jsonl": "log.jsonl", "state.bin": "state.bin", "policy.dpol": "policy.dpol"}
    for key, fn in names.items():
        p = os.path.join(run_dir, fn)
        if not os.path.isfile(p):
            raise Reject("MISSING_OUTPUT", "%s not in run dir" % fn)
        if file_sha256(p) != d["files"][key]:
            raise Reject("OUTPUT_TAMPERED", "%s hash differs from the dump's record" % fn)
    if abstraction_path and file_sha256(abstraction_path) != d["files"]["abstraction"]:
        raise Reject("INPUT_TAMPERED", "abstraction hash differs from the dump's record")
    with open(os.path.join(run_dir, "config.txt"), "r", encoding="utf-8") as f:
        cfg_text = f.read()
    if cfg_text != d["config_text"]:
        raise Reject("INPUT_TAMPERED", "config.txt differs from the dump's config_text")
    cfg = _config(cfg_text)
    if cfg.get("game") != "nlhe" or cfg.get("players") != "6":
        raise Reject("UNSUPPORTED", "only 6-player NLHE preflop dumps are handled")
    with open(os.path.join(run_dir, "log.jsonl"), "r", encoding="utf-8") as f:
        rows = [json.loads(ln) for ln in f if ln.strip()]
    if not rows:
        raise Reject("MISSING_CONVERGENCE", "log.jsonl is empty")
    last = rows[-1]
    if last["iterations"] != d["iterations"]:
        raise Reject("CONVERGENCE_MISMATCH", "log.jsonl last iterations %r != dump %r" % (last["iterations"], d["iterations"]))
    ev, se = last["root_ev"], last["root_ev_se"]
    if len(ev) != 6 or len(se) != 6:
        raise Reject("MISSING_CONVERGENCE", "log.jsonl root EV/SE is not per 6 seats")
    sb, bb, stack = int(cfg["sb"]), int(cfg["bb"]), int(cfg["stack"])
    pot = sb + bb
    per_seat = [{"seat": SEATS_6MAX[i], "root_ev_chips": ev[i], "se_chips": se[i]} for i in range(6)]
    worst = max(per_seat, key=lambda r: r["se_chips"])
    conv = {"method": "root_ev_standard_error", "iterations": last["iterations"], "per_seat": per_seat,
            "worst_seat": worst["seat"], "worst_seat_se_chips": worst["se_chips"], "root_pot_chips": pot,
            "worst_seat_se_pct_of_pot": 100.0 * worst["se_chips"] / pot,
            "se_scope": "donksolver log.jsonl last chunk: root EV and SE estimated on that chunk's deals only "
                        "(Solver.solve resets the EV accumulator each chunk); Monte Carlo estimate, not an exploitability bound",
            "source": "log.jsonl"}
    nodes = []
    for n in d["decision_nodes"]:
        fr = n["average_strategy_by_class"]
        if set(fr) != CLASSES:
            raise Reject("MISSING_FREQUENCIES", "node %s does not cover the 169 classes" % n["node_id"])
        nodes.append({"path": n["path"], "actor": n["actor"], "actions": n["actions"], "frequencies": fr,
                      "evs": None, "solver_node_id": n["node_id"],
                      "action_detail": {"kinds": n["kinds"], "additional_chips": n["chips"], "pot_fracs": n["fracs"]}})
    root = d["decision_nodes"][0]
    run_date = datetime.datetime.fromtimestamp(last["t"], datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "spot_id": spot_id, "street": "preflop", "board": [],
        "table": {"format": "6max", "seat_order": list(SEATS_6MAX), "blinds_chips": {"sb": sb, "bb": bb}},
        "positions": {"seats": list(SEATS_6MAX), "first_to_act": root["actor"]},
        "hand_keying": "class169",
        "ranges": {"kind": "engine_dealt", "detail": "donksolver deals hole cards to every seat from the deck; no range input"},
        "pot": pot, "stacks": {"effective_stack": stack, "stack_bb": stack / bb, "per_seat_chips": [stack] * 6},
        "rake": {"pct": float(cfg["rake_pct"]), "cap_chips": int(cfg["rake_cap"]), "no_flop_no_drop": cfg.get("no_flop_no_drop") == "1"},
        "bet_sizes": {k: cfg[k] for k in sorted(cfg) if k.startswith(("menu.", "mw_menu.")) or k in ("max_raises", "mw_max_raises", "allin", "kappa_bet", "kappa_ai")},
        "solver": dict(d["solver"]), "solver_settings": {k: cfg[k] for k in sorted(cfg) if k != "abstraction"},
        "run_date": run_date, "run_date_source": "log.jsonl last row t",
        "convergence": conv, "decision_nodes": nodes,
        "provenance": {"output_file": os.path.basename(dump_path), "output_sha256": file_sha256(dump_path),
                       "solver_files_sha256": d["files"], "dump_max_depth": d["max_depth"],
                       "class_to_preflop_bucket": d["class_to_preflop_bucket"],
                       "action_label_note": d.get("action_label_note")},
        "verification": "single_source",
    }
