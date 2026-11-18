"""validator_v2 tests. All fixtures are SYNTHETIC placeholders built with
build_pack and marked synthetic_test_data; every number here is made up
for unit tests and is never solver output. The two sample-verdict tests
load the committed sample packs and assert their verdicts."""
import copy
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, HERE)
from test_pipeline import quiet  # noqa: E402
from retrosolver_pipeline import pack_v2  # noqa: E402
from retrosolver_pipeline.pack_v2 import (  # noqa: E402
    CLASSES, build_pack, compute_pack_hash)
from retrosolver_pipeline.validator_v2 import (  # noqa: E402
    cross_check_v2, main, validate_v2_pack)

SAMPLES = os.path.join(REPO_ROOT, "samples", "v2")


def mk(spot, ev_mode="frequencies_only"):
    return build_pack("synthetic-v2", "2026-01-01T00:00:00Z",
                      {"name": "t", "version": "0"}, spot["solver"],
                      [spot], "0" * 64, ev_mode)


def mutated(pack, fn):
    """Deep copy of a pack with fn applied, hash recomputed."""
    p = copy.deepcopy(pack)
    fn(p)
    p["pack_hash"] = compute_pack_hash(p)
    return p


def se_spot(worst_se_chips=0.3, spot_id="synthetic-preflop",
            ev_by_seat=None, solver_settings=None):
    """SE-method preflop spot. worst_se_chips is the largest per-seat SE;
    root pot is 300 chips, so SE% = worst_se_chips / 3."""
    fracs = (0.2, 0.4, 0.6, 0.7, 0.85, 1.0)
    evs = ev_by_seat or {}
    per_seat = [{"seat": s, "root_ev_chips": evs.get(s, 1.0),
                 "se_chips": worst_se_chips * f}
                for s, f in zip(pack_v2.SEATS_6MAX, fracs)]
    return {
        "spot_id": spot_id, "street": "preflop", "board": [],
        "table": {"format": "6max"},
        "positions": {"seats": list(pack_v2.SEATS_6MAX), "first_to_act": "UTG"},
        "hand_keying": "class169", "pot": 300, "stacks": {"effective_stack": 8000},
        "solver": {"name": "synthetic", "version": "0"},
        "solver_settings": solver_settings if solver_settings is not None else {},
        "run_date": "2026-01-01T00:00:00Z", "run_date_source": "synthetic",
        "convergence": {"method": "root_ev_standard_error", "iterations": 10,
                        "per_seat": per_seat, "worst_seat": "BTN",
                        "worst_seat_se_chips": worst_se_chips,
                        "root_pot_chips": 300,
                        "worst_seat_se_pct_of_pot": 100.0 * worst_se_chips / 300,
                        "se_scope": "synthetic", "source": "synthetic"},
        "decision_nodes": [{"path": [], "actor": "UTG",
                            "actions": ["FOLD", "RAISE 500"],
                            "frequencies": {c: [0.25, 0.75] for c in sorted(CLASSES)},
                            "evs": None}],
        "provenance": {"output_file": "synthetic", "output_sha256": "0" * 64},
        "verification": "single_source", "synthetic_test_data": True,
    }


def expl_spot(exploitability=0.4, target=0.5, met_target=True,
              spot_id="synthetic-turn"):
    """Exploitability-method turn spot (combo-keyed)."""
    combos = ["AhAc", "KhKc", "JdJc", "TdTc"]
    return {
        "spot_id": spot_id, "street": "turn",
        "board": ["As", "Kd", "Qh", "2c"],
        "table": {"format": "6max"}, "positions": {"ip": "BTN", "oop": "BB"},
        "hand_keying": "combo", "pot": 5.5, "stacks": {"effective_stack": 20},
        "ranges": {"ip": "AA,KK", "oop": "JJ,66"},
        "solver": {"name": "synthetic", "version": "0"}, "solver_settings": {},
        "run_date": "2026-01-01T00:00:00Z", "run_date_source": "synthetic",
        "convergence": {"method": "exploitability", "iterations": 180,
                        "exploitability_pct_of_pot": exploitability,
                        "accuracy_target_pct_of_pot": target,
                        "met_target": met_target, "source": "tmp_log.txt"},
        "decision_nodes": [{"path": [], "actor": "oop",
                            "actions": ["CHECK", "BET 4"],
                            "frequencies": {c: [0.5, 0.5] for c in combos},
                            "evs": None}],
        "provenance": {"output_file": "synthetic", "output_sha256": "0" * 64},
        "verification": "single_source", "synthetic_test_data": True,
    }


def combo_keys(n, board):
    """n valid combo keys (pairs of distinct cards, none on the board)."""
    ranks = "AKQJT98765432"
    suits = "cdhs"
    deck = [r + s for r in ranks for s in suits if r + s not in board]
    out = []
    for i in range(len(deck)):
        for j in range(i + 1, len(deck)):
            out.append(deck[i] + deck[j])
            if len(out) == n:
                return out
    return out


def node(path, actor, actions, frequencies):
    return {"path": path, "actor": actor, "actions": actions,
            "frequencies": frequencies, "evs": None}


def flop_spot(spot_id, nodes, solver_settings=None):
    return {
        "spot_id": spot_id, "street": "flop", "board": ["Qs", "Jh", "2h"],
        "table": {"format": "6max"}, "positions": {"ip": "BTN", "oop": "BB"},
        "hand_keying": "combo", "pot": 10, "stacks": {"effective_stack": 20},
        "ranges": {"ip": "AA,KK", "oop": "JJ,66"},
        "solver": {"name": "synthetic", "version": "0"},
        "solver_settings": solver_settings if solver_settings is not None else {},
        "run_date": "2026-01-01T00:00:00Z", "run_date_source": "synthetic",
        "convergence": {"method": "exploitability", "iterations": 180,
                        "exploitability_pct_of_pot": 0.4,
                        "accuracy_target_pct_of_pot": 0.5,
                        "met_target": True, "source": "tmp_log.txt"},
        "decision_nodes": nodes,
        "provenance": {"output_file": "synthetic", "output_sha256": "0" * 64},
        "verification": "single_source", "synthetic_test_data": True,
    }


def deep_pair(root_shift=0.004, shifted_keys=55, shift=0.06):
    """Two flop packs for the deep-node scenario: 4 deep nodes x 110
    keys x 2 actions = 880 deep entries. Roots agree within root_shift.
    In pack B, shifted_keys keys in the deepest node move by shift
    (one action gains, the other loses, so vectors still sum to 1)."""
    keys = combo_keys(110, ["Qs", "Jh", "2h"])

    def freqs(vec):
        return {k: list(vec) for k in keys}

    nodes_a = [
        node([], "oop", ["CHECK", "BET 4"], freqs([0.7, 0.3])),
        node(["CHECK"], "ip", ["CHECK", "BET 4"], freqs([0.8, 0.2])),
        node(["CHECK", "BET 4"], "oop", ["CALL", "FOLD"], freqs([0.5, 0.5])),
        node(["BET 4"], "ip", ["CALL", "FOLD"], freqs([0.6, 0.4])),
        node(["BET 4", "CALL"], "oop", ["CHECK", "BET 4"], freqs([0.5, 0.5])),
    ]
    deep_b = {}
    for i, k in enumerate(keys):
        deep_b[k] = [0.5 + shift, 0.5 - shift] if i < shifted_keys else [0.5, 0.5]
    nodes_b = [
        node([], "oop", ["CHECK", "BET 4"], freqs([0.7 + root_shift, 0.3 - root_shift])),
        node(["CHECK"], "ip", ["CHECK", "BET 4"], freqs([0.8, 0.2])),
        node(["CHECK", "BET 4"], "oop", ["CALL", "FOLD"], freqs([0.5, 0.5])),
        node(["BET 4"], "ip", ["CALL", "FOLD"], freqs([0.6, 0.4])),
        node(["BET 4", "CALL"], "oop", ["CHECK", "BET 4"], deep_b),
    ]
    return (mk(flop_spot("synthetic-flop-deep", nodes_a)),
            mk(flop_spot("synthetic-flop-deep", nodes_b)))


def count_deep_entries(pack_a, pack_b):
    """(total deep entries, entries over 0.05) across matched deep nodes."""
    total, over = 0, 0
    a_nodes = {tuple(n["path"]): n for n in pack_a["spots"][0]["decision_nodes"]}
    b_nodes = {tuple(n["path"]): n for n in pack_b["spots"][0]["decision_nodes"]}
    for path in sorted(set(a_nodes) & set(b_nodes)):
        if not path:
            continue
        fa, fb = a_nodes[path]["frequencies"], b_nodes[path]["frequencies"]
        for key in set(fa) | set(fb):
            va = fa.get(key) or [0.0] * len(a_nodes[path]["actions"])
            vb = fb.get(key) or [0.0] * len(b_nodes[path]["actions"])
            for x, y in zip(va, vb):
                total += 1
                if abs(x - y) > 0.05:
                    over += 1
    return total, over


class SEBandTests(unittest.TestCase):
    def test_se_pass(self):
        # Worst SE 0.3 chips on a 300-chip pot = 0.10% of pot.
        r = validate_v2_pack(mk(se_spot(0.3)), allow_synthetic=True)
        self.assertEqual(r.verdict, "accept")
        self.assertEqual(r.failures, [])

    def test_se_warning(self):
        # Worst SE 0.9 chips = 0.30% of pot (warning band 0.25-0.5%).
        r = validate_v2_pack(mk(se_spot(0.9)), allow_synthetic=True)
        self.assertEqual(r.verdict, "warning")
        self.assertTrue(any("warning band" in w for w in r.warnings))

    def test_se_reject(self):
        # Worst SE 1.8 chips = 0.60% of pot (above the 0.5% reject band).
        r = validate_v2_pack(mk(se_spot(1.8)), allow_synthetic=True)
        self.assertEqual(r.verdict, "reject")
        self.assertTrue(any("0.6000%" in f for f in r.failures))

    def test_se_pct_mismatch_rejects(self):
        p = mutated(mk(se_spot(0.3)), lambda p: p["spots"][0]["convergence"]
                    .update(worst_seat_se_pct_of_pot=0.2))
        r = validate_v2_pack(p, allow_synthetic=True)
        self.assertEqual(r.verdict, "reject")
        self.assertTrue(any("worst_seat_se_pct_of_pot" in f for f in r.failures))

    def test_worst_seat_mismatch_rejects(self):
        p = mutated(mk(se_spot(0.3)), lambda p: p["spots"][0]["convergence"]
                    .update(worst_seat="SB"))
        r = validate_v2_pack(p, allow_synthetic=True)
        self.assertEqual(r.verdict, "reject")
        self.assertTrue(any("worst_seat" in f for f in r.failures))

    def test_synthetic_refused_without_flag(self):
        r = validate_v2_pack(mk(se_spot(0.3)))
        self.assertEqual(r.verdict, "reject")

    def test_non_v2_pack_rejects(self):
        r = validate_v2_pack({"schema": "retrosolver.spot_pack.v1", "spots": []})
        self.assertEqual(r.verdict, "reject")


class ExploitabilityTests(unittest.TestCase):
    def test_exploitability_accept(self):
        r = validate_v2_pack(mk(expl_spot(0.4, 0.5)), allow_synthetic=True)
        self.assertEqual(r.verdict, "accept")

    def test_exploitability_warning_within_10pct_over(self):
        # 0.52 vs a 0.5 target: 4% over, inside the 10% warning margin.
        p = mutated(mk(expl_spot(0.4, 0.5)), lambda p: p["spots"][0]["convergence"]
                    .update(exploitability_pct_of_pot=0.52))
        r = validate_v2_pack(p, allow_synthetic=True)
        self.assertEqual(r.verdict, "warning")
        self.assertTrue(any("warning margin" in w for w in r.warnings))

    def test_exploitability_reject_beyond_10pct_over(self):
        # 0.60 vs a 0.5 target: 20% over, beyond the warning margin.
        p = mutated(mk(expl_spot(0.4, 0.5)), lambda p: p["spots"][0]["convergence"]
                    .update(exploitability_pct_of_pot=0.60))
        r = validate_v2_pack(p, allow_synthetic=True)
        self.assertEqual(r.verdict, "reject")

    def test_met_target_inconsistency_rejects(self):
        p = mutated(mk(expl_spot(0.4, 0.5)), lambda p: p["spots"][0]["convergence"]
                    .update(met_target=False))
        r = validate_v2_pack(p, allow_synthetic=True)
        self.assertEqual(r.verdict, "reject")
        self.assertTrue(any("met_target" in f for f in r.failures))


class HashTests(unittest.TestCase):
    def test_pack_hash_mismatch_rejects(self):
        p = mk(se_spot(0.3))
        p["spots"][0]["pot"] = 301  # content changed, hash not recomputed
        r = validate_v2_pack(p, allow_synthetic=True)
        self.assertEqual(r.verdict, "reject")
        self.assertTrue(any("pack_hash" in f for f in r.failures))


class SampleVerdictTests(unittest.TestCase):
    def test_preflop_sample_rejects(self):
        path = os.path.join(SAMPLES, "v2-sample-donksolver-preflop.pack.json")
        with open(path) as f:
            pack = json.load(f)
        r = validate_v2_pack(pack)
        self.assertEqual(r.verdict, "reject")
        # Worst SE 2.2066 chips on a 300-chip pot = 0.7355% of pot.
        self.assertTrue(any("0.7355" in f for f in r.failures))

    def test_turn_sample_accepts(self):
        path = os.path.join(SAMPLES, "v2-sample-texassolver-turn.pack.json")
        with open(path) as f:
            pack = json.load(f)
        r = validate_v2_pack(pack)
        self.assertEqual(r.verdict, "accept")
        self.assertEqual(r.failures, [])


class CrossCheckTests(unittest.TestCase):
    def test_root_disagreement_quarantines(self):
        keys = combo_keys(8, ["Qs", "Jh", "2h"])
        root_a = {k: [0.7, 0.3] for k in keys}
        root_b = {k: [0.7, 0.3] for k in keys}
        root_b[keys[0]] = [0.76, 0.24]  # one root entry off by 0.06
        deep = {k: [0.5, 0.5] for k in keys}
        nodes_a = [node([], "oop", ["CHECK", "BET 4"], root_a),
                   node(["CHECK"], "ip", ["CHECK", "BET 4"], deep)]
        nodes_b = [node([], "oop", ["CHECK", "BET 4"], root_b),
                   node(["CHECK"], "ip", ["CHECK", "BET 4"], deep)]
        q, findings = cross_check_v2(
            mk(flop_spot("synthetic-flop-root", nodes_a)),
            mk(flop_spot("synthetic-flop-root", nodes_b)))
        self.assertTrue(q)
        self.assertTrue(any("root frequencies disagree" in f for f in findings))

    def test_root_top_action_flip_without_near_tie_quarantines(self):
        # Pack A [0.52, 0.48] tops CHECK; pack B [0.49, 0.51] tops BET 4.
        # Max diff is 0.03 (warning band only), but the top action flips
        # and pack A's top two are 0.04 apart, so no near-tie exception.
        keys = combo_keys(8, ["Qs", "Jh", "2h"])
        root_a = {k: [0.52, 0.48] for k in keys}
        root_b = {k: [0.49, 0.51] for k in keys}
        nodes_a = [node([], "oop", ["CHECK", "BET 4"], root_a)]
        nodes_b = [node([], "oop", ["CHECK", "BET 4"], root_b)]
        q, findings = cross_check_v2(
            mk(flop_spot("synthetic-flop-top", nodes_a)),
            mk(flop_spot("synthetic-flop-top", nodes_b)))
        self.assertTrue(q)
        self.assertTrue(any("top action disagrees" in f for f in findings))

    def test_root_top_action_flip_on_near_tie_passes(self):
        # Both runs have their top two within 0.02: the flip is noise.
        keys = combo_keys(8, ["Qs", "Jh", "2h"])
        root_a = {k: [0.51, 0.49] for k in keys}
        root_b = {k: [0.49, 0.51] for k in keys}
        nodes_a = [node([], "oop", ["CHECK", "BET 4"], root_a)]
        nodes_b = [node([], "oop", ["CHECK", "BET 4"], root_b)]
        q, findings = cross_check_v2(
            mk(flop_spot("synthetic-flop-tie", nodes_a)),
            mk(flop_spot("synthetic-flop-tie", nodes_b)))
        self.assertFalse(q)
        self.assertTrue(any("near tie" in f for f in findings))

    def test_deep_disagreement_passes_when_reach_weighted(self):
        # 110 of 880 deep entries differ by 0.06, but they sit in the
        # deepest node (reach ~0.18), so the reach-weighted mean is
        # ~0.004: two runs that agree where the game is actually played.
        pack_a, pack_b = deep_pair()
        total, over = count_deep_entries(pack_a, pack_b)
        self.assertEqual((total, over), (880, 110))
        q, findings = cross_check_v2(pack_a, pack_b)
        self.assertFalse(q)
        self.assertTrue(any("worst deep entries" in f for f in findings))

    def test_all_deep_disagreement_quarantines(self):
        # Every deep entry differs by 0.06: the reach-weighted mean is
        # 0.06, above the 0.05 reject band.
        keys = combo_keys(110, ["Qs", "Jh", "2h"])

        def freqs(vec):
            return {k: list(vec) for k in keys}

        nodes_a = [
            node([], "oop", ["CHECK", "BET 4"], freqs([0.7, 0.3])),
            node(["CHECK"], "ip", ["CHECK", "BET 4"], freqs([0.8, 0.2])),
            node(["CHECK", "BET 4"], "oop", ["CALL", "FOLD"], freqs([0.5, 0.5])),
            node(["BET 4"], "ip", ["CALL", "FOLD"], freqs([0.6, 0.4])),
            node(["BET 4", "CALL"], "oop", ["CHECK", "BET 4"], freqs([0.5, 0.5])),
        ]
        nodes_b = [
            node([], "oop", ["CHECK", "BET 4"], freqs([0.7, 0.3])),
            node(["CHECK"], "ip", ["CHECK", "BET 4"], freqs([0.86, 0.14])),
            node(["CHECK", "BET 4"], "oop", ["CALL", "FOLD"], freqs([0.56, 0.44])),
            node(["BET 4"], "ip", ["CALL", "FOLD"], freqs([0.66, 0.34])),
            node(["BET 4", "CALL"], "oop", ["CHECK", "BET 4"], freqs([0.56, 0.44])),
        ]
        q, findings = cross_check_v2(
            mk(flop_spot("synthetic-flop-alldeep", nodes_a)),
            mk(flop_spot("synthetic-flop-alldeep", nodes_b)))
        self.assertTrue(q)
        self.assertTrue(any("reach-weighted mean" in f for f in findings))

    def test_root_ev_beyond_combined_se_quarantines(self):
        # BB root EV 10.0 vs 12.0 chips; each run's BB SE is 0.12 chips,
        # so 2x combined SE is 0.34 chips and the 2.0-chip gap quarantines.
        pack_a = mk(se_spot(0.3, ev_by_seat={"BB": 10.0}))
        pack_b = mk(se_spot(0.3, ev_by_seat={"BB": 12.0}))
        q, findings = cross_check_v2(pack_a, pack_b)
        self.assertTrue(q)
        self.assertTrue(any("root EV" in f and "BB" in f for f in findings))

    def test_root_ev_within_combined_se_passes(self):
        pack_a = mk(se_spot(0.3, ev_by_seat={"BB": 10.0}))
        pack_b = mk(se_spot(0.3, ev_by_seat={"BB": 10.2}))
        q, _findings = cross_check_v2(pack_a, pack_b)
        self.assertFalse(q)

    def test_unmatched_and_divergent_spots_quarantine(self):
        q, findings = cross_check_v2(
            mk(se_spot(0.3, spot_id="synthetic-preflop")),
            mk(se_spot(0.3, spot_id="synthetic-other")))
        self.assertTrue(q)
        self.assertTrue(any("missing in pack" in f for f in findings))
        q, findings = cross_check_v2(
            mk(se_spot(0.3, solver_settings={})),
            mk(se_spot(0.3, solver_settings={"preset": "synthetic"})))
        self.assertTrue(q)
        self.assertTrue(any("divergent" in f for f in findings))


class CliTests(unittest.TestCase):
    def test_cli_validate_and_cross_check(self):
        with tempfile.TemporaryDirectory() as d:
            a_path = os.path.join(d, "a.json")
            b_path = os.path.join(d, "b.json")
            with open(a_path, "w") as f:
                json.dump(mk(se_spot(0.3)), f)
            with open(b_path, "w") as f:
                json.dump(mk(se_spot(0.3)), f)
            rc, _log = quiet(main, [a_path, "--allow-synthetic"])
            self.assertEqual(rc, 0)
            rc, _log = quiet(main, [a_path, b_path, "--allow-synthetic"])
            self.assertEqual(rc, 0)
            rc, _log = quiet(main, [os.path.join(d, "missing.json")])
            self.assertEqual(rc, 3)


if __name__ == "__main__":
    unittest.main()
