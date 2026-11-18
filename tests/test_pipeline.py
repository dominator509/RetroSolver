"""Unit tests. All solver-like numbers come from tests/synthetic.py and are SYNTHETIC."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import batch_generate  # noqa: E402
import extract_pack  # noqa: E402
import verify_pack  # noqa: E402
import synthetic  # noqa: E402
from retrosolver_pipeline.canonical import canonical_json  # noqa: E402
from retrosolver_pipeline.pack import PackError, compute_pack_hash, validate_pack  # noqa: E402
from retrosolver_pipeline.spotlist import (SpotListError, load_spot_list, normalize_spot_list,  # noqa: E402
                                           render_cli_script, spot_list_from_csv)

SAMPLE = os.path.join(ROOT, "samples", "sample_spots_3.json")


def quiet(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = fn(*a, **k)
    return rc, buf.getvalue()


class CanonicalTests(unittest.TestCase):
    def test_rfc8785_number_vectors(self):
        # Number-formatting vectors from RFC 8785 / ECMAScript (formatting, not strategy).
        cases = {0.0: "0", -0.0: "0", 1.0: "1", 1e-7: "1e-7", 0.000001: "0.000001",
                 1e21: "1e+21", 1e20: "100000000000000000000", 333333333.3333333: "333333333.3333333",
                 5e-324: "5e-324", 1.7976931348623157e308: "1.7976931348623157e+308",
                 9007199254740992.0: "9007199254740992", 295147905179352830000.0: "295147905179352830000",
                 4.5: "4.5", 2e-3: "0.002", 0.000001234: "0.000001234", 1.234e-7: "1.234e-7", -12.5: "-12.5"}
        for v, want in cases.items():
            self.assertEqual(canonical_json(v), want, repr(v))

    def test_sorted_keys_no_whitespace(self):
        self.assertEqual(canonical_json({"b": [1, 2.5], "a": {"y": None, "x": True}}),
                         '{"a":{"x":true,"y":null},"b":[1,2.5]}')

    def test_rejects_nonfinite(self):
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                canonical_json([bad])


class SpotListTests(unittest.TestCase):
    def setUp(self):
        self.base = copy.deepcopy(synthetic.SPOT_LIST)

    def bad(self, mutate, msg):
        doc = copy.deepcopy(self.base)
        mutate(doc["spots"][0], doc)
        with self.assertRaises(SpotListError) as cm:
            normalize_spot_list(doc)
        self.assertIn(msg, str(cm.exception))

    def test_sample_list_is_valid(self):
        sl = load_spot_list(SAMPLE)
        self.assertEqual([s["street"] for s in sl["spots"]], ["flop", "turn", "river"])

    def test_rejections(self):
        self.bad(lambda s, d: s["ranges"].__setitem__("ip", "AA, KK"), "whitespace")
        self.bad(lambda s, d: s.__setitem__("board", "Qs,Qs,2h"), "duplicate cards")
        self.bad(lambda s, d: s.__setitem__("board", "Qs,Jh"), "3, 4 or 5")
        self.bad(lambda s, d: s["ranges"].__setitem__("oop", "AAs"), "pair")
        self.bad(lambda s, d: s["ranges"].__setitem__("oop", "KA"), "higher rank")
        self.bad(lambda s, d: s["ranges"].__setitem__("oop", "AA:1.5"), "weight")
        self.bad(lambda s, d: s.pop("accuracy_target"), "accuracy_target")
        self.bad(lambda s, d: s.__setitem__("ev", 1), "unknown fields")
        self.bad(lambda s, d: s["bet_sizes"].__setitem__("flop", {}), "already dealt")
        self.bad(lambda s, d: d["solver"].__setitem__("version", ""), "solver")
        self.bad(lambda s, d: d["spots"].append(copy.deepcopy(s)), "duplicate spot_id")
        self.bad(lambda s, d: s.__setitem__("spot_id", "Bad Id"), "spot_id")

    def test_cli_script_rules(self):
        for spot in load_spot_list(SAMPLE)["spots"]:
            text = render_cli_script(spot)
            self.assertNotIn("\r", text)
            lines = text.split("\n")
            self.assertEqual(lines[-1], "")
            lines = lines[:-1]
            self.assertTrue(all(ln and len(ln.split(" ")) <= 2 for ln in lines))
            self.assertLess(lines.index("set_allin_threshold 0.67"), lines.index("build_tree"))
            self.assertTrue(any(ln.startswith("set_accuracy ") for ln in lines))
            self.assertLess(max(i for i, ln in enumerate(lines) if ln.startswith("set_accuracy")),
                            lines.index("start_solve"))
            self.assertEqual(lines[-1], "dump_result output_result.json")
            self.assertNotIn("set_raise_limit", text)  # not in the v0.2.0 release binary

    def test_csv_matches_json(self):
        csv_text = ("spot_id,ip_position,oop_position,pot,effective_stack,board,range_ip,range_oop,bet_sizes,accuracy_target\n"
                    "synthetic-river-1,BTN,BB,10,20,\"Qs,Jh,2h,8d,3c\",\"AA,KK\",\"JJ,66\","
                    "river:oop:bet:50|river:ip:bet:50,0.5\n")
        from_csv = normalize_spot_list(spot_list_from_csv(csv_text, "TexasSolver", "v0.2.0"))
        from_json = normalize_spot_list(copy.deepcopy(self.base))
        self.assertEqual(from_csv["spots"], from_json["spots"])


class GeneratorTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            out = os.path.join(t, "batch")
            rc, log = quiet(batch_generate.main, [SAMPLE, "--out", out, "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(out))
            self.assertEqual(log.count("dump_result output_result.json"), 3)

    def test_generate_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            out = os.path.join(t, "batch")
            self.assertEqual(quiet(batch_generate.main, [SAMPLE, "--out", out])[0], 0)
            with open(os.path.join(out, "manifest.json")) as f:
                man = json.load(f)
            self.assertEqual(len(man["spots"]), 3)
            with open(os.path.join(out, "run_all.bat"), "rb") as f:
                bat = f.read()
            self.assertIn(b"\r\n", bat)
            self.assertNotIn(b"\n", bat.replace(b"\r\n", b""))
            self.assertIn(b"OMP_STACKSIZE=64M", bat)
            with open(os.path.join(out, "run_all.sh"), "rb") as f:
                self.assertIn(b"OMP_STACKSIZE:-64M", f.read())
            self.assertEqual(quiet(batch_generate.main, [SAMPLE, "--out", out])[0], 1)


class ExtractorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = self.tmp.name
        self.batch = os.path.join(self.t, "batch")
        sl = os.path.join(self.t, "list.json")
        with open(sl, "w") as f:
            json.dump(synthetic.SPOT_LIST, f)
        assert quiet(batch_generate.main, [sl, "--out", self.batch])[0] == 0
        self.sid = "synthetic-river-1"
        self.out = os.path.join(self.t, "pack.json")

    def tearDown(self):
        self.tmp.cleanup()

    def extract(self, allow_synthetic=True):
        return quiet(extract_pack.run, self.batch, self.out, self.out + ".rej", allow_synthetic=allow_synthetic)

    def rejections(self):
        with open(self.out + ".rej") as f:
            return [json.loads(ln) for ln in f]

    def test_accept_and_hash_roundtrip(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output())
        rc, log = self.extract()
        self.assertEqual(rc, 0, log)
        with open(self.out) as f:
            pack = json.load(f)
        self.assertTrue(pack["contains_synthetic_test_data"])
        spot = pack["spots"][0]
        for k in ("spot_id", "board", "ranges", "pot", "stacks", "bet_sizes", "decision_nodes", "solver",
                  "accuracy_target", "run_date", "convergence"):
            self.assertIn(k, spot)
        self.assertEqual(spot["run_date"], "2026-01-01T00:00:00Z")
        self.assertEqual(spot["convergence"]["exploitability_pct_of_pot"], 0.4)
        self.assertEqual([n["path"] for n in spot["decision_nodes"]],
                         [[], ["BET 5.000000"], ["CHECK"], ["CHECK", "BET 5.000000"]])
        self.assertEqual(spot["decision_nodes"][0]["player"], "oop")
        self.assertTrue(validate_pack(pack, allow_synthetic=True))
        self.assertEqual(compute_pack_hash(pack), pack["pack_hash"])
        # synthetic packs can never pass the production check
        with self.assertRaises(PackError):
            validate_pack(pack)
        self.assertEqual(quiet(verify_pack.main, [self.out])[0], 1)
        self.assertEqual(quiet(verify_pack.main, [self.out, "--allow-synthetic"])[0], 0)
        # tamper with one number -> hash mismatch
        pack["spots"][0]["pot"] = 11
        with self.assertRaises(PackError) as cm:
            validate_pack(pack, allow_synthetic=True)
        self.assertIn("pack_hash mismatch", str(cm.exception))

    def test_synthetic_refused_without_flag(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output())
        rc, _ = self.extract(allow_synthetic=False)
        self.assertEqual(rc, 1)
        self.assertEqual(self.rejections()[0]["code"], "SYNTHETIC_DATA")
        self.assertFalse(os.path.exists(self.out))

    def assertRejected(self, code):
        rc, log = self.extract()
        self.assertEqual(rc, 1, log)
        self.assertFalse(os.path.exists(self.out), "no pack may be written without valid spots")
        self.assertEqual(self.rejections()[0]["code"], code, log)

    def test_missing_evs(self):  # this is what stock TexasSolver CLI output looks like
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output(evs=False))
        self.assertRejected("MISSING_EVS")

    def test_not_converged(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output(), log_values=(3.0, 0.9))
        self.assertRejected("NOT_CONVERGED")

    def test_missing_convergence(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output(), log_values=())
        self.assertRejected("MISSING_CONVERGENCE")

    def test_missing_output(self):
        synthetic.write_spot_outputs(self.batch, self.sid, None)
        self.assertRejected("MISSING_OUTPUT")

    def test_solver_failed(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output(), exit_code="3")
        self.assertRejected("SOLVER_FAILED")

    def test_bad_frequency_sum(self):
        tree = synthetic.synthetic_output()
        tree["strategy"]["strategy"]["JdJc"] = [0.25, 0.25]
        synthetic.write_spot_outputs(self.batch, self.sid, tree)
        self.assertRejected("BAD_FREQUENCY")

    def test_missing_frequencies(self):
        tree = synthetic.synthetic_output()
        del tree["childrens"]["CHECK"]["strategy"]
        synthetic.write_spot_outputs(self.batch, self.sid, tree)
        self.assertRejected("MISSING_FREQUENCIES")

    def test_ev_combo_mismatch(self):
        tree = synthetic.synthetic_output()
        del tree["evs"]["evs"]["JdJc"]
        synthetic.write_spot_outputs(self.batch, self.sid, tree)
        self.assertRejected("EV_COMBO_MISMATCH")

    def test_board_overlap(self):
        tree = synthetic.synthetic_output()
        tree["strategy"]["strategy"]["QsQc"] = [0.25, 0.75]
        synthetic.write_spot_outputs(self.batch, self.sid, tree)
        self.assertRejected("BAD_COMBO")

    def test_convergence_mismatch(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output())
        with open(os.path.join(self.batch, "spots", self.sid, "solve_stdout.log"), "a") as f:
            f.write("Total exploitability 0.1 precent\n")
        self.assertRejected("CONVERGENCE_MISMATCH")

    def test_input_tampered(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output())
        with open(os.path.join(self.batch, "spots", self.sid, "input.txt"), "a") as f:
            f.write("set_accuracy 50\n")
        self.assertRejected("INPUT_TAMPERED")

    # --- frequencies-only mode (synthetic fixtures only) ---
    def extract_fo(self):
        return quiet(extract_pack.run, self.batch, self.out, self.out + ".rej", allow_synthetic=True,
                     frequencies_only=True)

    def test_freq_only_accepts_no_ev_output(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output(evs=False))
        rc, log = self.extract_fo()
        self.assertEqual(rc, 0, log)
        with open(self.out) as f:
            pack = json.load(f)
        self.assertEqual(pack["ev_mode"], "frequencies_only")
        spot = pack["spots"][0]
        self.assertEqual(spot["verification"], "single_source")
        self.assertTrue(all(n["evs"] is None for n in spot["decision_nodes"]))
        self.assertTrue(all(n["frequencies"] for n in spot["decision_nodes"]))
        self.assertTrue(validate_pack(pack, allow_synthetic=True))
        # an EV block smuggled into a frequencies_only pack is invalid, as is flipping ev_mode
        bad = copy.deepcopy(pack); bad["spots"][0]["decision_nodes"][0]["evs"] = {"JdJc": [1.0, 2.0]}
        bad["pack_hash"] = compute_pack_hash(bad)
        with self.assertRaises(PackError):
            validate_pack(bad, allow_synthetic=True)
        bad = copy.deepcopy(pack); bad["ev_mode"] = "full"; bad["pack_hash"] = compute_pack_hash(bad)
        with self.assertRaises(PackError):
            validate_pack(bad, allow_synthetic=True)

    def test_freq_only_refuses_ev_output(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output())
        rc, log = self.extract_fo()
        self.assertEqual(rc, 1, log)
        self.assertEqual(self.rejections()[0]["code"], "EVS_PRESENT_IN_FREQ_ONLY")

    def test_freq_only_keeps_other_gates(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output(evs=False), log_values=(3.0, 0.9))
        rc, log = self.extract_fo()
        self.assertEqual(rc, 1, log)
        self.assertEqual(self.rejections()[0]["code"], "NOT_CONVERGED")

    def test_full_mode_still_rejects_missing_evs_and_tags_spots(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output())
        rc, log = self.extract()
        self.assertEqual(rc, 0, log)
        with open(self.out) as f:
            pack = json.load(f)
        self.assertEqual(pack["ev_mode"], "full")
        self.assertEqual(pack["spots"][0]["verification"], "single_source")

    def test_refuses_to_overwrite_pack(self):
        synthetic.write_spot_outputs(self.batch, self.sid, synthetic.synthetic_output())
        open(self.out, "x").close()
        rc, log = self.extract()
        self.assertEqual(rc, 1)
        self.assertIn("refusing to overwrite", log)


if __name__ == "__main__":
    unittest.main()
