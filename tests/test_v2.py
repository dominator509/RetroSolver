"""spot_pack.v2 tests. All numbers are SYNTHETIC placeholders, never solver output;
every pack built here carries synthetic_test_data and production verification refuses it."""
import copy
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import batch_generate  # noqa: E402
import extract_pack_v2  # noqa: E402
import synthetic  # noqa: E402
from test_pipeline import quiet  # noqa: E402
from retrosolver_pipeline import pack_v2  # noqa: E402
from retrosolver_pipeline.pack_v2 import CLASSES, PackError, build_pack, compute_pack_hash, validate_pack  # noqa: E402


def synthetic_preflop_spot():
    per_seat = [{"seat": s, "root_ev_chips": 1.0, "se_chips": 0.5 + i * 0.1} for i, s in enumerate(pack_v2.SEATS_6MAX)]
    return {
        "spot_id": "synthetic-preflop", "street": "preflop", "board": [],
        "table": {"format": "6max"}, "positions": {"seats": list(pack_v2.SEATS_6MAX), "first_to_act": "UTG"},
        "hand_keying": "class169", "pot": 300, "stacks": {"effective_stack": 8000},
        "solver": {"name": "synthetic", "version": "0"}, "solver_settings": {}, "run_date": "2026-01-01T00:00:00Z",
        "run_date_source": "synthetic",
        "convergence": {"method": "root_ev_standard_error", "iterations": 10, "per_seat": per_seat, "worst_seat": "BTN",
                        "worst_seat_se_chips": per_seat[-1]["se_chips"], "root_pot_chips": 300,
                        "worst_seat_se_pct_of_pot": 100.0 * per_seat[-1]["se_chips"] / 300, "se_scope": "synthetic", "source": "synthetic"},
        "decision_nodes": [{"path": [], "actor": "UTG", "actions": ["FOLD", "RAISE 500"],
                            "frequencies": {c: [0.25, 0.75] for c in sorted(CLASSES)}, "evs": None}],
        "provenance": {"output_file": "synthetic", "output_sha256": "0" * 64}, "verification": "single_source",
        "synthetic_test_data": True,
    }


def mk(spot, ev_mode="frequencies_only"):
    return build_pack("synthetic-v2", "2026-01-01T00:00:00Z", {"name": "t", "version": "0"}, spot["solver"], [spot], "0" * 64, ev_mode)


class V2PackTests(unittest.TestCase):
    def test_preflop_pack_valid_and_hashed(self):
        p = mk(synthetic_preflop_spot())
        self.assertTrue(validate_pack(p, allow_synthetic=True))
        with self.assertRaises(PackError):
            validate_pack(p)  # synthetic never passes production
        p["spots"][0]["pot"] = 301
        with self.assertRaises(PackError):
            validate_pack(p, allow_synthetic=True)

    def bad(self, mutate, ev_mode="frequencies_only"):
        s = synthetic_preflop_spot(); mutate(s)
        with self.assertRaises(PackError):
            mk(s, ev_mode)

    def test_rejections(self):
        self.bad(lambda s: s.update(board=["Ah", "Kd", "2c"]))                      # preflop has no board
        self.bad(lambda s: s["decision_nodes"][0]["frequencies"].pop("AA"))        # 169 classes required
        self.bad(lambda s: s["decision_nodes"][0]["frequencies"].update(AKx=[0.5, 0.5]))
        self.bad(lambda s: s["decision_nodes"][0]["frequencies"].update(AA=[0.5, 0.6]))  # sum != 1
        self.bad(lambda s: s["decision_nodes"][0].update(evs={c: [0, 0] for c in CLASSES}))  # evs in freq-only
        self.bad(lambda s: s["convergence"].update(worst_seat="SB"))               # must be the max-SE seat
        self.bad(lambda s: s["convergence"].update(worst_seat_se_pct_of_pot=0.1))  # must equal 100*se/pot
        self.bad(lambda s: s["convergence"].update(met_target=True))               # SE makes no target claim
        self.bad(lambda s: s.update(positions={"ip": "BTN", "oop": "BB"}))         # preflop needs 6 seats
        self.bad(lambda s: s.update(hand_keying="combo"))
        self.bad(lambda s: s.update(verification="trusted"))
        self.bad(lambda s: s["decision_nodes"][0].update(actor="P7"))
        self.bad(lambda s: None, ev_mode="full")                                   # full mode needs EVs


class V2TexasSolverExtractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = self.tmp.name
        self.batch = os.path.join(t, "batch"); sl = os.path.join(t, "list.json")
        with open(sl, "w") as f:
            json.dump(synthetic.SPOT_LIST, f)
        assert quiet(batch_generate.main, [sl, "--out", self.batch])[0] == 0
        self.out = os.path.join(t, "v2.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_freq_only_and_full(self):
        synthetic.write_spot_outputs(self.batch, "synthetic-river-1", synthetic.synthetic_output(evs=False))
        rc, log = quiet(extract_pack_v2.main, ["texassolver", self.batch, "--out", self.out, "--frequencies-only", "--allow-synthetic"])
        self.assertEqual(rc, 0, log)
        with open(self.out) as f:
            p = json.load(f)
        self.assertEqual(p["schema"], "retrosolver.spot_pack.v2")
        s = p["spots"][0]
        self.assertEqual((s["hand_keying"], s["convergence"]["method"], s["verification"]), ("combo", "exploitability", "single_source"))
        self.assertTrue(all(n["evs"] is None for n in s["decision_nodes"]))
        self.assertEqual(compute_pack_hash(p), p["pack_hash"])
        self.assertTrue(validate_pack(p, allow_synthetic=True))
        rc, log = quiet(extract_pack_v2.main, ["texassolver", self.batch, "--out", self.out, "--frequencies-only", "--allow-synthetic"])
        self.assertEqual(rc, 1)  # never overwrites

    def test_full_mode_needs_evs(self):
        synthetic.write_spot_outputs(self.batch, "synthetic-river-1", synthetic.synthetic_output(evs=False))
        rc, log = quiet(extract_pack_v2.main, ["texassolver", self.batch, "--out", self.out, "--allow-synthetic"])
        self.assertEqual(rc, 1, log)
        self.assertFalse(os.path.exists(self.out))


if __name__ == "__main__":
    unittest.main()
