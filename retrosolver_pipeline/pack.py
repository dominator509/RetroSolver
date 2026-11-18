"""Spot-pack schema checks and the pack-level hash.

pack_hash = sha256( canonical_json(pack minus the "pack_hash" key) ), where
canonical_json is RFC 8785 (JCS): sorted keys, no whitespace, ECMAScript
number formatting. Any JS/TS or Python JCS implementation reproduces it.
"""
import math
import re

from . import SPOT_PACK_SCHEMA
from .canonical import canonical_sha256

SPOT_REQUIRED = ["spot_id", "board", "ranges", "pot", "stacks", "bet_sizes", "decision_nodes",
                 "solver", "accuracy_target", "run_date", "convergence"]
NODE_REQUIRED = ["path", "player", "actions", "frequencies", "evs"]
HASH_INFO = {"algorithm": "sha256", "canonicalization": "RFC8785-JCS",
             "scope": "entire pack object with the pack_hash key removed"}
EV_MODES = ("full", "frequencies_only")
VERIFICATION = ("single_source", "verified")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class PackError(ValueError):
    pass


def compute_pack_hash(pack):
    body = {k: v for k, v in pack.items() if k != "pack_hash"}
    return canonical_sha256(body)


def build_pack(pack_id, created_at, generator, solver, spots, source_manifest_sha256, extra=None,
               ev_mode="full"):
    pack = {"schema": SPOT_PACK_SCHEMA, "pack_id": pack_id, "created_at": created_at, "ev_mode": ev_mode,
            "generator": generator, "solver": solver, "source_batch_manifest_sha256": source_manifest_sha256,
            "spot_count": len(spots), "spots": spots, "hash": dict(HASH_INFO)}
    if any(s.get("synthetic_test_data") for s in spots):
        pack["contains_synthetic_test_data"] = True
    if extra:
        pack.update(extra)
    validate_pack(pack, check_hash=False, allow_synthetic=True)
    pack["pack_hash"] = compute_pack_hash(pack)
    return pack


def _num_ok(x):
    return not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x)


def validate_spot(s, ev_mode="full"):
    where = "spot %r" % s.get("spot_id")
    for k in SPOT_REQUIRED:
        if k not in s or s[k] in (None, "", [], {}):
            raise PackError("%s: missing required field %r" % (where, k))
    if not (isinstance(s["ranges"], dict) and s["ranges"].get("ip") and s["ranges"].get("oop")):
        raise PackError("%s: ranges must have ip and oop" % where)
    if not _num_ok(s["pot"]) or not _num_ok(s["stacks"].get("effective_stack")):
        raise PackError("%s: pot/stacks must be numbers" % where)
    if not (isinstance(s["solver"], dict) and s["solver"].get("name") and s["solver"].get("version")):
        raise PackError("%s: solver name + version required" % where)
    c = s["convergence"]
    if not _num_ok(c.get("exploitability_pct_of_pot")) or c.get("met_target") is not True:
        raise PackError("%s: convergence figure missing or target not met" % where)
    if c["exploitability_pct_of_pot"] > s["accuracy_target"]:
        raise PackError("%s: exploitability above accuracy target" % where)
    if "verification" in s and s["verification"] not in VERIFICATION:
        raise PackError("%s: verification must be one of %s" % (where, VERIFICATION))
    if ev_mode == "frequencies_only" and "verification" not in s:
        raise PackError("%s: frequencies_only spots must carry a verification tag" % where)
    for n in s["decision_nodes"]:
        for k in NODE_REQUIRED:
            if k not in n:
                raise PackError("%s node %s: missing %r" % (where, n.get("path"), k))
        na = len(n["actions"])
        if ev_mode == "frequencies_only":
            if n["evs"] is not None:
                raise PackError("%s node %s: frequencies_only pack must have evs=null" % (where, n["path"]))
            if not n["frequencies"]:
                raise PackError("%s node %s: frequencies missing" % (where, n["path"]))
        elif not n["frequencies"] or not isinstance(n["evs"], dict) or set(n["frequencies"]) != set(n["evs"]):
            raise PackError("%s node %s: frequencies/EVs missing or combo sets differ" % (where, n["path"]))
        for combo, vec in n["frequencies"].items():
            if len(vec) != na or not all(_num_ok(x) for x in vec):
                raise PackError("%s node %s: bad frequency vector for %s" % (where, n["path"], combo))
            if abs(sum(vec) - 1) > 1e-3:
                raise PackError("%s node %s: %s frequencies do not sum to 1" % (where, n["path"], combo))
        for combo, vec in (n["evs"] or {}).items():
            if len(vec) != na or not all(_num_ok(x) for x in vec):
                raise PackError("%s node %s: bad EV vector for %s" % (where, n["path"], combo))


def validate_pack(pack, check_hash=True, allow_synthetic=False):
    if pack.get("schema") != SPOT_PACK_SCHEMA:
        raise PackError("schema must be %r" % SPOT_PACK_SCHEMA)
    synthetic = pack.get("contains_synthetic_test_data") is True or any(
        s.get("synthetic_test_data") for s in pack.get("spots", []))
    if synthetic and not allow_synthetic:
        raise PackError("pack contains SYNTHETIC test data and must never ship")
    for k in ("pack_id", "created_at", "solver", "spots", "hash"):
        if k not in pack:
            raise PackError("pack missing %r" % k)
    if not pack["spots"]:
        raise PackError("pack has no spots")
    if pack.get("spot_count") != len(pack["spots"]):
        raise PackError("spot_count does not match spots")
    ids = [s.get("spot_id") for s in pack["spots"]]
    if len(set(ids)) != len(ids):
        raise PackError("duplicate spot_id in pack")
    ev_mode = pack.get("ev_mode", "full")   # packs written before the frequencies-only mode have no ev_mode: full
    if ev_mode not in EV_MODES:
        raise PackError("ev_mode must be one of %s" % (EV_MODES,))
    for s in pack["spots"]:
        validate_spot(s, ev_mode)
        if s["solver"] != pack["solver"]:
            raise PackError("spot %r solver differs from pack solver (mixed versions)" % s["spot_id"])
    if check_hash:
        h = pack.get("pack_hash")
        if not isinstance(h, str) or not HEX64.match(h):
            raise PackError("pack_hash missing or malformed")
        if compute_pack_hash(pack) != h:
            raise PackError("pack_hash mismatch: pack content was changed")
    return True
