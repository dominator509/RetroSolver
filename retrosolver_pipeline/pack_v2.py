"""retrosolver.spot_pack.v2: checks, builder and pack hash.

v2 lives ALONGSIDE v1 (v1 code and schema are untouched). What v2 adds:
  * street "preflop" with an empty board; 6-max seats (SB, BB, UTG, HJ, CO, BTN) instead of ip/oop only
  * hand_keying "class169" (AA, AKs, AKo, ... exactly 169 keys per node) besides "combo" (AhKd)
  * convergence is a tagged block:
      method "root_ev_standard_error" (Monte Carlo engines, e.g. donksolver): worst-seat SE in chips and
        as % of the root pot, iterations, per-seat root EV +- SE, all copied from the solver's own log
      method "exploitability" (exact CFR engines, e.g. TexasSolver): the v1 certificate, unchanged
  * ev_mode: "full" (per-action EVs on every node) | "frequencies_only" (evs null on every node)
  * verification: single_source until the independent validator sets verified
Every strategy number must come from a solver output file; this module only checks and hashes.
pack_hash = sha256 of RFC 8785 JCS canonical JSON of the pack without the pack_hash key (same as v1).
"""
import math
import re

from .canonical import canonical_sha256

SCHEMA_V2 = "retrosolver.spot_pack.v2"
STREETS = ("preflop", "flop", "turn", "river")
BOARD_LEN = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
SEATS_6MAX = ("SB", "BB", "UTG", "HJ", "CO", "BTN")
ACTORS = SEATS_6MAX + ("ip", "oop")
EV_MODES = ("full", "frequencies_only")
VERIFICATION = ("single_source", "verified")
KEYINGS = ("class169", "combo")
CONV_METHODS = ("root_ev_standard_error", "exploitability")
HASH_INFO = {"algorithm": "sha256", "canonicalization": "RFC8785-JCS",
             "scope": "entire pack object with the pack_hash key removed"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CARD = re.compile(r"^[2-9TJQKA][cdhs]$")
COMBO = re.compile(r"^[2-9TJQKA][cdhs][2-9TJQKA][cdhs]$")
RANKS_DESC = "AKQJT98765432"


def class169_names():
    out = []
    for i, a in enumerate(RANKS_DESC):
        for j, b in enumerate(RANKS_DESC):
            if i == j:
                out.append(a + a)
            elif i < j:
                out += [a + b + "s", a + b + "o"]
    return frozenset(out)


CLASSES = class169_names()
assert len(CLASSES) == 169


class PackError(ValueError):
    pass


def _num(x):
    return not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x)


def compute_pack_hash(pack):
    return canonical_sha256({k: v for k, v in pack.items() if k != "pack_hash"})


def _check_convergence(s, where):
    c = s.get("convergence")
    if not isinstance(c, dict) or c.get("method") not in CONV_METHODS:
        raise PackError("%s: convergence.method must be one of %s" % (where, CONV_METHODS))
    if not isinstance(c.get("source"), str) or not c["source"]:
        raise PackError("%s: convergence.source (solver output file) required" % where)
    if not isinstance(c.get("iterations"), int) or c["iterations"] < 1:
        raise PackError("%s: convergence.iterations required" % where)
    if c["method"] == "root_ev_standard_error":
        seats = c.get("per_seat")
        if not isinstance(seats, list) or not seats:
            raise PackError("%s: per_seat root EV/SE required" % where)
        for r in seats:
            if r.get("seat") not in SEATS_6MAX or not _num(r.get("root_ev_chips")) or not _num(r.get("se_chips")) or r["se_chips"] < 0:
                raise PackError("%s: bad per_seat row %r" % (where, r))
        worst = max(seats, key=lambda r: r["se_chips"])
        if c.get("worst_seat") != worst["seat"] or c.get("worst_seat_se_chips") != worst["se_chips"]:
            raise PackError("%s: worst_seat/worst_seat_se_chips must equal the largest per_seat se_chips" % where)
        pot = c.get("root_pot_chips")
        if not _num(pot) or pot <= 0:
            raise PackError("%s: root_pot_chips required" % where)
        if not _num(c.get("worst_seat_se_pct_of_pot")) or abs(c["worst_seat_se_pct_of_pot"] - 100.0 * worst["se_chips"] / pot) > 1e-9:
            raise PackError("%s: worst_seat_se_pct_of_pot must be 100*worst_seat_se_chips/root_pot_chips" % where)
        if "met_target" in c or "exploitability_pct_of_pot" in c:
            raise PackError("%s: SE convergence carries no exploitability/met_target claim" % where)
    else:
        if not _num(c.get("exploitability_pct_of_pot")) or c.get("met_target") is not True:
            raise PackError("%s: exploitability figure missing or target not met" % where)
        if not _num(c.get("accuracy_target_pct_of_pot")) or c["exploitability_pct_of_pot"] > c["accuracy_target_pct_of_pot"]:
            raise PackError("%s: exploitability above accuracy target" % where)


def validate_spot(s, ev_mode):
    where = "spot %r" % s.get("spot_id")
    for k in ("spot_id", "street", "board", "table", "positions", "hand_keying", "pot", "stacks", "solver",
              "solver_settings", "run_date", "run_date_source", "convergence", "decision_nodes", "provenance",
              "verification"):
        if k not in s:
            raise PackError("%s: missing %r" % (where, k))
    st = s["street"]
    if st not in STREETS:
        raise PackError("%s: street must be one of %s" % (where, STREETS))
    if not isinstance(s["board"], list) or len(s["board"]) != BOARD_LEN[st] or not all(CARD.match(c or "") for c in s["board"]):
        raise PackError("%s: board must have %d cards for %s" % (where, BOARD_LEN[st], st))
    if len(set(s["board"])) != len(s["board"]):
        raise PackError("%s: duplicate board card" % where)
    if s["verification"] not in VERIFICATION:
        raise PackError("%s: verification must be one of %s" % (where, VERIFICATION))
    tbl = s["table"]
    if not isinstance(tbl, dict) or tbl.get("format") not in ("6max", "heads_up"):
        raise PackError("%s: table.format must be 6max or heads_up" % where)
    pos = s["positions"]
    if st == "preflop":
        if tbl["format"] != "6max" or tuple(pos.get("seats", ())) != SEATS_6MAX or pos.get("first_to_act") not in SEATS_6MAX:
            raise PackError("%s: preflop 6-max needs positions.seats = %s and first_to_act" % (where, SEATS_6MAX))
        if s["hand_keying"] != "class169":
            raise PackError("%s: preflop frequencies must be keyed by the 169 hand classes" % where)
    else:
        if pos.get("ip") not in SEATS_6MAX or pos.get("oop") not in SEATS_6MAX or pos["ip"] == pos["oop"]:
            raise PackError("%s: postflop positions need distinct ip and oop seats" % where)
        if s["hand_keying"] != "combo":
            raise PackError("%s: postflop frequencies are combo-keyed" % where)
        if not isinstance(s.get("ranges"), dict) or not s["ranges"].get("ip") or not s["ranges"].get("oop"):
            raise PackError("%s: postflop ranges ip/oop required" % where)
    if not _num(s["pot"]) or s["pot"] <= 0 or not _num(s["stacks"].get("effective_stack")):
        raise PackError("%s: pot/stacks must be numbers" % where)
    if not (isinstance(s["solver"], dict) and s["solver"].get("name") and s["solver"].get("version")):
        raise PackError("%s: solver name + version required" % where)
    for k in ("output_sha256", "output_file"):
        if not s["provenance"].get(k):
            raise PackError("%s: provenance.%s required" % (where, k))
    if not HEX64.match(s["provenance"]["output_sha256"]):
        raise PackError("%s: provenance.output_sha256 must be sha256 hex" % where)
    _check_convergence(s, where)
    if st == "preflop" and s["convergence"]["method"] != "root_ev_standard_error":
        raise PackError("%s: preflop (Monte Carlo) spots use root_ev_standard_error convergence" % where)
    nodes = s["decision_nodes"]
    if not isinstance(nodes, list) or not nodes:
        raise PackError("%s: no decision nodes" % where)
    board = set(s["board"])
    for n in nodes:
        nw = "%s node %s" % (where, "/".join(n.get("path", [])) or "<root>")
        for k in ("path", "actor", "actions", "frequencies", "evs"):
            if k not in n:
                raise PackError("%s: missing %r" % (nw, k))
        if n["actor"] not in ACTORS:
            raise PackError("%s: actor must be one of %s" % (nw, ACTORS))
        na = len(n["actions"])
        if na < 1 or not all(isinstance(a, str) and a for a in n["actions"]):
            raise PackError("%s: actions" % nw)
        fr = n["frequencies"]
        if not isinstance(fr, dict) or not fr:
            raise PackError("%s: frequencies missing" % nw)
        if s["hand_keying"] == "class169":
            if set(fr) != CLASSES:
                raise PackError("%s: class169 nodes need exactly the 169 hand classes" % nw)
        else:
            for c in fr:
                if not COMBO.match(c) or c[:2] in board or c[2:] in board or c[:2] == c[2:]:
                    raise PackError("%s: bad combo key %r" % (nw, c))
        for c, v in fr.items():
            if not isinstance(v, list) or len(v) != na or not all(_num(x) and -1e-12 <= x <= 1 + 1e-12 for x in v):
                raise PackError("%s: bad frequency vector for %s" % (nw, c))
            if abs(sum(v) - 1.0) > 1e-3:
                raise PackError("%s: %s frequencies sum to %r" % (nw, c, sum(v)))
        if ev_mode == "frequencies_only":
            if n["evs"] is not None:
                raise PackError("%s: frequencies_only pack must have evs=null" % nw)
        else:
            ev = n["evs"]
            if not isinstance(ev, dict) or set(ev) != set(fr):
                raise PackError("%s: full mode needs evs with the same keys as frequencies" % nw)
            for c, v in ev.items():
                if not isinstance(v, list) or len(v) != na or not all(_num(x) for x in v):
                    raise PackError("%s: bad EV vector for %s" % (nw, c))


def validate_pack(pack, check_hash=True, allow_synthetic=False):
    if pack.get("schema") != SCHEMA_V2:
        raise PackError("schema must be %r" % SCHEMA_V2)
    synthetic = pack.get("contains_synthetic_test_data") is True or any(
        s.get("synthetic_test_data") for s in pack.get("spots", []))
    if synthetic and not allow_synthetic:
        raise PackError("pack contains SYNTHETIC test data and must never ship")
    for k in ("pack_id", "created_at", "generator", "solver", "ev_mode", "source_sha256", "spot_count", "spots", "hash"):
        if k not in pack:
            raise PackError("pack missing %r" % k)
    if pack["ev_mode"] not in EV_MODES:
        raise PackError("ev_mode must be one of %s" % (EV_MODES,))
    if not HEX64.match(pack["source_sha256"] or ""):
        raise PackError("source_sha256 must be sha256 hex")
    if not pack["spots"] or pack["spot_count"] != len(pack["spots"]):
        raise PackError("spot_count does not match spots")
    ids = [s.get("spot_id") for s in pack["spots"]]
    if len(set(ids)) != len(ids):
        raise PackError("duplicate spot_id in pack")
    for s in pack["spots"]:
        validate_spot(s, pack["ev_mode"])
        if s["solver"] != pack["solver"]:
            raise PackError("spot %r solver differs from pack solver" % s["spot_id"])
    if check_hash:
        h = pack.get("pack_hash")
        if not isinstance(h, str) or not HEX64.match(h):
            raise PackError("pack_hash missing or malformed")
        if compute_pack_hash(pack) != h:
            raise PackError("pack_hash mismatch: pack content was changed")
    return True


def build_pack(pack_id, created_at, generator, solver, spots, source_sha256, ev_mode):
    pack = {"schema": SCHEMA_V2, "pack_id": pack_id, "created_at": created_at, "generator": generator,
            "solver": solver, "ev_mode": ev_mode, "source_sha256": source_sha256,
            "spot_count": len(spots), "spots": spots, "hash": dict(HASH_INFO)}
    if any(s.get("synthetic_test_data") for s in spots):
        pack["contains_synthetic_test_data"] = True
    validate_pack(pack, check_hash=False, allow_synthetic=True)
    pack["pack_hash"] = compute_pack_hash(pack)
    return pack
