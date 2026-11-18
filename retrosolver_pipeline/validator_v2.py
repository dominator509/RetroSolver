"""Independent acceptance validator for spot_pack.v2 packs.

This module is the acceptance bar for v2 spot packs: it decides whether
a pack's strategy numbers are good enough to use, by recomputing the
pack's own claims from the pack JSON instead of trusting them. Structure
is checked by retrosolver_pipeline.pack_v2; this module adds the
acceptance judgement on top.

Acceptance bar
--------------
Every pack states how well its solver run converged. There are two
kinds of convergence claim:

* Monte Carlo runs state a worst-seat standard error (SE) as a
  percentage of the root pot. The documented accuracy target for the
  program is 0.5% of pot. The bar is: accept when the worst-seat SE is
  at most 0.25% of pot, warn between 0.25% and 0.5%, and reject above
  0.5%. The reasoning is budget arithmetic: at 0.25% the one-sigma
  sampling error is half the accuracy budget, so a plus-or-minus
  two-sigma interval just fits inside it; above 0.5% the sampling
  noise alone exceeds the whole budget, so the frequencies cannot be
  trusted to the program's own standard.
* Exact runs state an exploitability figure against a stated accuracy
  target. Accept when the figure is at or under the target, warn when
  it exceeds the target by no more than 10%, and reject when it
  exceeds the target by more. The target claim itself must be
  consistent: the pack must state that the target was met, and the
  figure must agree with that statement.

What is recomputed, what is trusted
-----------------------------------
The validator recomputes, from the pack JSON itself: the worst seat
(the largest per-seat SE), the SE as a percentage of the root pot, the
pack hash, every frequency vector's sum, and the 169-class coverage of
class-keyed nodes. A recomputation mismatch is a rejection: the pack
is claiming something its own numbers contradict. The validator trusts
only the SE values and the iteration counts themselves, which are
internal to the solver and cannot be recomputed from the pack.

What this validator cannot verify
----------------------------------
The acceptance bar is honest about its limits. It cannot verify:
abstraction quality (how the solver simplified the game); Nash
distance without an exploitability figure; per-action EVs in
frequencies-only packs (they are absent by design); the SE values
themselves; the iteration counts; whether the raw solver output is
truly converged; combo expansion (which combos a range contains);
or the solver version recorded in the pack. A pack that passes here
is accepted on its convergence evidence, not certified on those
points.

Dual-run cross-check
--------------------
Two independent runs of the same spots are compared node by node.
The root node is compared entry by entry (warn at 0.02, reject at
0.05), with a near-tie exception for top-action flips: when the top
two actions are within 0.02 in both runs, a flip of the top action is
noise, not disagreement. Deeper nodes are compared by a
reach-weighted mean absolute difference (warn at 0.02, reject at
0.05): each entry is weighted by how often the game reaches that node
for that hand, so a large difference in a rarely reached corner
cannot veto two runs that agree where the game is actually played.
The worst deep entries are still listed, so nothing is hidden.
Root EVs are compared per seat within twice the combined standard
error. Spots that do not match, or whose identity differs, are
quarantined.

Verification
------------
A pack arrives marked single_source. Only this validator's verdict
may promote it: the validator never trusts a pipeline claim, and a
pack counts as verified only when it passes here or agrees with an
independent run in the cross-check.
"""

import argparse
import copy
import json
import math
import sys
from dataclasses import dataclass, field

from .canonical import canonical_json, canonical_sha256
from .pack_v2 import CLASSES, PackError, validate_pack

SCHEMA_V2 = "retrosolver.spot_pack.v2"

# Acceptance bands: worst-seat SE as a percentage of the root pot.
SE_PASS_PCT = 0.25
SE_WARN_PCT = 0.5
# Exploitability: a run may exceed its stated accuracy target by up to
# this fraction before it is rejected outright; inside the margin it is
# accepted with a warning.
EXPLOIT_OVER_WARN = 0.10
# Frequency comparison bands (absolute frequency difference).
FREQ_WARN = 0.02
FREQ_REJECT = 0.05
# Recomputation tolerances (the structural check uses the same values).
SE_PCT_TOL = 1e-9
FREQ_SUM_TOL = 1e-3
EPS = 1e-9
# How many of the worst deep entries to list for visibility.
DEEP_WORST_SHOWN = 5


@dataclass
class PackVerdict:
    """The validator's verdict on one pack.

    verdict is "accept", "warning", or "reject". failures are the
    reasons a pack is rejected; warnings are findings that flag a
    pack for review without rejecting it.
    """

    verdict: str
    failures: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _num(x):
    return not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x)


# ---------------------------------------------------------------------------
# Single-pack validation
# ---------------------------------------------------------------------------

def _structure_copy(pack):
    """Deep copy of the pack with the exploitability-vs-target bound
    neutralised, so the structural check can still catch every other
    problem. The bound itself is graded by the acceptance bar (warning
    within 10% over the target, reject beyond), not by the structural
    check, so it is clamped to the target here and evaluated on the
    original pack below."""
    if not isinstance(pack, dict):
        return pack
    cp = copy.deepcopy(pack)
    for spot in cp.get("spots") or []:
        if not isinstance(spot, dict):
            continue
        conv = spot.get("convergence")
        if not isinstance(conv, dict) or conv.get("method") != "exploitability":
            continue
        exp = conv.get("exploitability_pct_of_pot")
        target = conv.get("accuracy_target_pct_of_pot")
        if _num(exp) and _num(target) and exp > target:
            conv["exploitability_pct_of_pot"] = target
    return cp


def _recompute_hash(pack, failures):
    h = pack.get("pack_hash")
    if not isinstance(h, str) or not h:
        failures.append("pack_hash missing or malformed")
        return
    try:
        recomputed = canonical_sha256(
            {k: v for k, v in pack.items() if k != "pack_hash"})
    except (TypeError, ValueError) as e:
        failures.append("pack_hash cannot be recomputed: %s" % e)
        return
    if recomputed != h:
        failures.append(
            "pack_hash mismatch: stored %s != recomputed %s "
            "(pack content was changed)" % (h, recomputed))


def _recompute_spot(spot, failures):
    """Recompute one spot's claimed figures from its own numbers.
    Fields that are absent or unreadable are left to the structural
    check; only present, computable claims are rechecked here."""
    sid = spot.get("spot_id", "<missing spot_id>")
    conv = spot.get("convergence")
    if isinstance(conv, dict) and conv.get("method") == "root_ev_standard_error":
        per_seat = conv.get("per_seat")
        rows = []
        if isinstance(per_seat, list) and per_seat:
            for r in per_seat:
                if (isinstance(r, dict) and isinstance(r.get("seat"), str)
                        and _num(r.get("se_chips")) and r["se_chips"] >= 0):
                    rows.append((r["seat"], r["se_chips"]))
        if len(rows) == len(per_seat) and rows:
            worst_seat, worst_se = max(rows, key=lambda t: t[1])
            if conv.get("worst_seat") != worst_seat:
                failures.append(
                    "spot %s: worst_seat %r != recomputed worst seat %r "
                    "(largest per-seat SE)" % (sid, conv.get("worst_seat"), worst_seat))
            if conv.get("worst_seat_se_chips") != worst_se:
                failures.append(
                    "spot %s: worst_seat_se_chips %r != recomputed worst SE %r "
                    "(false claim)" % (sid, conv.get("worst_seat_se_chips"), worst_se))
            root_pot = conv.get("root_pot_chips")
            stated_pct = conv.get("worst_seat_se_pct_of_pot")
            if _num(root_pot) and root_pot > 0 and _num(stated_pct):
                recomputed_pct = 100.0 * worst_se / root_pot
                if abs(stated_pct - recomputed_pct) > SE_PCT_TOL:
                    failures.append(
                        "spot %s: worst_seat_se_pct_of_pot %r != recomputed %.10f "
                        "(100 * worst SE / root pot; false claim)"
                        % (sid, stated_pct, recomputed_pct))
    nodes = spot.get("decision_nodes")
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if not isinstance(node, dict):
            continue
        path = "/".join(node.get("path") or []) or "<root>"
        freqs = node.get("frequencies")
        if not isinstance(freqs, dict):
            continue
        if spot.get("hand_keying") == "class169":
            missing = sorted(CLASSES - set(freqs))
            extra = sorted(set(freqs) - CLASSES)
            if missing or extra:
                failures.append(
                    "spot %s: node %s class169 coverage: missing %d keys %s, "
                    "extra %d keys %s"
                    % (sid, path, len(missing), missing[:5],
                       len(extra), extra[:5]))
        worst_dev, worst_key = 0.0, None
        for key, vec in freqs.items():
            if isinstance(vec, list) and all(_num(x) for x in vec):
                dev = abs(sum(vec) - 1.0)
                if dev > worst_dev:
                    worst_dev, worst_key = dev, key
        if worst_dev > FREQ_SUM_TOL:
            failures.append(
                "spot %s: node %s frequencies sum off by %.4f at key %r "
                "(tolerance %.4f)" % (sid, path, worst_dev, worst_key, FREQ_SUM_TOL))


def _band_spot(spot, failures, warnings):
    """Apply the acceptance bands to one spot's convergence claim."""
    sid = spot.get("spot_id", "<missing spot_id>")
    conv = spot.get("convergence")
    if not isinstance(conv, dict):
        failures.append("spot %s: convergence block missing or unreadable" % sid)
        return
    method = conv.get("method")
    if method == "root_ev_standard_error":
        per_seat = conv.get("per_seat")
        root_pot = conv.get("root_pot_chips")
        ses = []
        if isinstance(per_seat, list) and per_seat:
            ses = [r.get("se_chips") for r in per_seat if isinstance(r, dict)]
        if not ses or not all(_num(v) and v >= 0 for v in ses):
            failures.append("spot %s: SE convergence block is incomplete" % sid)
            return
        if not _num(root_pot) or root_pot <= 0:
            failures.append("spot %s: SE convergence block is incomplete" % sid)
            return
        se_pct = 100.0 * max(ses) / root_pot
        if se_pct > SE_WARN_PCT + EPS:
            failures.append(
                "spot %s: worst-seat SE %.4f%% of pot exceeds the %.4f%% "
                "reject band (worst SE %r chips, root pot %r chips)"
                % (sid, se_pct, SE_WARN_PCT, max(ses), root_pot))
        elif se_pct > SE_PASS_PCT + EPS:
            warnings.append(
                "spot %s: worst-seat SE %.4f%% of pot is in the warning band "
                "(%.4f%%-%.4f%% of pot)"
                % (sid, se_pct, SE_PASS_PCT, SE_WARN_PCT))
    elif method == "exploitability":
        exp = conv.get("exploitability_pct_of_pot")
        target = conv.get("accuracy_target_pct_of_pot")
        if conv.get("met_target") is not True:
            failures.append(
                "spot %s: met_target must be true (the pack claims its "
                "accuracy target was met)" % sid)
        if not _num(exp) or not _num(target):
            failures.append(
                "spot %s: exploitability figure or accuracy target is missing"
                % sid)
            return
        if exp <= target:
            return
        if target > 0 and exp <= target * (1.0 + EXPLOIT_OVER_WARN):
            warnings.append(
                "spot %s: exploitability %.4f%% of pot exceeds its %.4f%% "
                "target by %.1f%% (within the 10%% warning margin)"
                % (sid, exp, target, 100.0 * (exp - target) / target))
        elif target > 0:
            failures.append(
                "spot %s: exploitability %.4f%% of pot exceeds its %.4f%% "
                "target by %.1f%% (beyond the 10%% warning margin)"
                % (sid, exp, target, 100.0 * (exp - target) / target))
        else:
            failures.append(
                "spot %s: exploitability %.4f%% of pot exceeds its %.4f%% target"
                % (sid, exp, target))
    else:
        failures.append("spot %s: unknown convergence method %r" % (sid, method))


def validate_v2_pack(pack, allow_synthetic=False):
    """Validate one v2 pack and return a PackVerdict.

    Structure is delegated to pack_v2.validate_pack (hash excluded:
    the hash is recomputed here). The acceptance bands are applied to
    the pack's own convergence figures, and every recomputable claim
    is rechecked from the pack JSON. A pack is rejected when any
    failure is found, warned when it only carries warnings, and
    accepted otherwise. Synthetic test data is refused unless
    allow_synthetic is set.
    """
    failures, warnings = [], []
    if not isinstance(pack, dict):
        return PackVerdict("reject", ["pack is not a JSON object"], [])
    try:
        validate_pack(_structure_copy(pack), check_hash=False,
                      allow_synthetic=allow_synthetic)
    except PackError as e:
        failures.append("structure: %s" % e)
    except (TypeError, KeyError, AttributeError) as e:
        failures.append("structure: pack is malformed (%s: %s)"
                        % (type(e).__name__, e))
    _recompute_hash(pack, failures)
    spots = pack.get("spots")
    if isinstance(spots, list):
        for spot in spots:
            if isinstance(spot, dict):
                _recompute_spot(spot, failures)
        for spot in spots:
            if isinstance(spot, dict):
                _band_spot(spot, failures, warnings)
    verdict = "reject" if failures else ("warning" if warnings else "accept")
    return PackVerdict(verdict, failures, warnings)


# ---------------------------------------------------------------------------
# Dual-run cross-check
# ---------------------------------------------------------------------------

def _spot_identity(spot):
    """Identity of a spot for matching two runs: spot_id, positions,
    pot, stacks, and the solver-settings hash. Two spots are the same
    spot only when all of these agree. Returns None when the identity
    cannot be computed."""
    try:
        return (
            spot.get("spot_id"),
            canonical_json(spot.get("positions")),
            canonical_json(spot.get("pot")),
            canonical_json(spot.get("stacks")),
            canonical_sha256(spot.get("solver_settings")),
        )
    except (TypeError, ValueError):
        return None


def _fmt_path(path):
    return "/".join(path) if path else "<root>"


def _node_map(spot):
    """{path tuple: node} for a spot. Also returns a list of path
    problems (malformed or duplicate paths)."""
    nodes, problems = {}, []
    for node in spot.get("decision_nodes") or []:
        if not isinstance(node, dict):
            problems.append("<non-object node>")
            continue
        path = node.get("path")
        if not isinstance(path, list) or not all(isinstance(e, str) for e in path):
            problems.append("malformed path %r" % (path,))
            continue
        key = tuple(path)
        if key in nodes:
            problems.append("duplicate path %s" % _fmt_path(path))
        else:
            nodes[key] = node
    return nodes, problems


def _same_actions(na, nb):
    return isinstance(na.get("actions"), list) and na.get("actions") == nb.get("actions")


def _resolve_action(entry, actions):
    """Resolve one path entry to an action index in the ancestor node's
    actions list. Preflop entries are 'SEAT:ACTION'; postflop entries
    are bare action names. Returns None when the entry cannot be
    resolved."""
    if not isinstance(entry, str) or not isinstance(actions, list):
        return None
    if entry in actions:
        return actions.index(entry)
    if ":" in entry:
        action = entry.rsplit(":", 1)[1]
        if action in actions:
            return actions.index(action)
    return None


def _reach(nodes, path, key):
    """Reach of (node at path, key) in one run: the product of the
    action frequencies along the path, for that key. Returns None when
    any step cannot be resolved."""
    reach = 1.0
    for i, entry in enumerate(path):
        ancestor = nodes.get(tuple(path[:i]))
        if ancestor is None:
            return None
        idx = _resolve_action(entry, ancestor.get("actions"))
        if idx is None:
            return None
        vec = (ancestor.get("frequencies") or {}).get(key)
        if not isinstance(vec, list) or idx >= len(vec) or not _num(vec[idx]):
            return None
        reach *= vec[idx]
    return reach


def _top_two(vec):
    """(top action index, top frequency, second frequency) of a vector."""
    best, second, best_i = -1.0, -1.0, 0
    for i, v in enumerate(vec):
        if v > best:
            second, best, best_i = best, v, i
        elif v > second:
            second = v
    return best_i, best, (second if second >= 0 else 0.0)


def _compare_root(sid, na, nb, note_quarantine, note_warning):
    """Root node: per-entry max absolute difference, plus top-action
    agreement with the near-tie exception."""
    fa, fb = na.get("frequencies") or {}, nb.get("frequencies") or {}
    actions = na.get("actions") or []
    max_d, flips = 0.0, 0
    for key in sorted(set(fa) | set(fb)):
        va = list(fa.get(key) or [0.0] * len(actions))
        vb = list(fb.get(key) or [0.0] * len(actions))
        n = max(len(va), len(vb))
        va += [0.0] * (n - len(va))
        vb += [0.0] * (n - len(vb))
        for i in range(n):
            if _num(va[i]) and _num(vb[i]):
                max_d = max(max_d, abs(va[i] - vb[i]))
        if va and vb:
            clean_a = [v if _num(v) else 0.0 for v in va]
            clean_b = [v if _num(v) else 0.0 for v in vb]
            ia, fa_top, fa_second = _top_two(clean_a)
            ib, fb_top, fb_second = _top_two(clean_b)
            if ia != ib:
                near_tie = (fa_top - fa_second <= FREQ_WARN + EPS
                            and fb_top - fb_second <= FREQ_WARN + EPS)
                if near_tie:
                    flips += 1
                else:
                    note_quarantine(
                        "spot %s: root top action disagrees for %s "
                        "(pack A %s %.3f vs second %.3f; pack B %s %.3f vs second %.3f)"
                        % (sid, key, actions[ia] if ia < len(actions) else ia,
                           fa_top, fa_second,
                           actions[ib] if ib < len(actions) else ib,
                           fb_top, fb_second))
    if max_d > FREQ_REJECT + EPS:
        note_quarantine(
            "spot %s: root frequencies disagree by up to %.4f (> %.2f)"
            % (sid, max_d, FREQ_REJECT))
    elif max_d > FREQ_WARN + EPS:
        note_warning(
            "spot %s: root frequencies differ by up to %.4f "
            "(warning band %.2f-%.2f)" % (sid, max_d, FREQ_WARN, FREQ_REJECT))
    if flips:
        note_warning(
            "spot %s: %d root top-action flip(s) on near ties "
            "(top two within %.2f in both runs)" % (sid, flips, FREQ_WARN))


def _compare_deep_node(path, na, nb, nodes_a, nodes_b, acc):
    """Accumulate one deep node's entries into acc (reach-weighted
    sums plus the worst entries)."""
    fa, fb = na.get("frequencies") or {}, nb.get("frequencies") or {}
    actions = na.get("actions") or []
    for key in sorted(set(fa) | set(fb)):
        reach_a = _reach(nodes_a, path, key)
        reach_b = _reach(nodes_b, path, key)
        # Unresolvable reach gets full weight: an entry whose reach
        # cannot be determined must not hide behind a small weight.
        reach = 1.0 if reach_a is None or reach_b is None else (reach_a + reach_b) / 2.0
        va = list(fa.get(key) or [0.0] * len(actions))
        vb = list(fb.get(key) or [0.0] * len(actions))
        n = max(len(va), len(vb))
        va += [0.0] * (n - len(va))
        vb += [0.0] * (n - len(vb))
        for i in range(n):
            if not _num(va[i]) or not _num(vb[i]):
                continue
            d = abs(va[i] - vb[i])
            acc["weighted_sum"] += reach * d
            acc["weight_total"] += reach
            if d > FREQ_WARN + EPS:
                acc["worst"].append(
                    (d, path, key, actions[i] if i < len(actions) else i))


def _compare_root_ev(sid, sa, sb, note_quarantine, note_warning):
    """Root-EV comparison per seat, within twice the combined SE.
    Only runs when both spots use the SE convergence method."""
    ca, cb = sa.get("convergence"), sb.get("convergence")
    if not isinstance(ca, dict) or not isinstance(cb, dict):
        return
    ma, mb = ca.get("method"), cb.get("method")
    if ma != "root_ev_standard_error" or mb != "root_ev_standard_error":
        if ma != mb:
            note_warning(
                "spot %s: convergence methods differ (%s vs %s); "
                "root-EV comparison skipped" % (sid, ma, mb))
        return

    def per_seat(conv):
        out = {}
        for row in conv.get("per_seat") or []:
            if isinstance(row, dict) and isinstance(row.get("seat"), str):
                out[row["seat"]] = (row.get("root_ev_chips"), row.get("se_chips"))
        return out

    ea, eb = per_seat(ca), per_seat(cb)
    for seat in sorted(set(ea) | set(eb)):
        if seat not in ea or seat not in eb:
            note_warning(
                "spot %s: seat %s root EV present in only one run; "
                "EV comparison skipped for it" % (sid, seat))
            continue
        eva, sea = ea[seat]
        evb, seb = eb[seat]
        if not (_num(eva) and _num(sea) and _num(evb) and _num(seb)):
            continue
        tol = 2.0 * math.sqrt(sea * sea + seb * seb)
        if abs(eva - evb) > tol + EPS:
            note_quarantine(
                "spot %s: root EV seat %s differs by %.4f chips "
                "(> 2x combined SE %.4f)" % (sid, seat, abs(eva - evb), tol))


def _compare_spot(sid, sa, sb, note_quarantine, note_warning):
    id_a, id_b = _spot_identity(sa), _spot_identity(sb)
    if id_a is None or id_b is None or id_a != id_b:
        note_quarantine(
            "spot %s: divergent (spot_id, positions, pot, stacks, or "
            "solver settings differ)" % sid)
        return
    nodes_a, problems_a = _node_map(sa)
    nodes_b, problems_b = _node_map(sb)
    if problems_a or problems_b:
        note_quarantine(
            "spot %s: decision nodes have malformed or duplicate paths (%s)"
            % (sid, "; ".join(problems_a + problems_b)))
        return
    for path in sorted(set(nodes_a) - set(nodes_b)):
        note_quarantine("spot %s: node %s present in pack A only"
                        % (sid, _fmt_path(path)))
    for path in sorted(set(nodes_b) - set(nodes_a)):
        note_quarantine("spot %s: node %s present in pack B only"
                        % (sid, _fmt_path(path)))
    deep = {"weighted_sum": 0.0, "weight_total": 0.0, "worst": []}
    for path in sorted(set(nodes_a) & set(nodes_b)):
        na, nb = nodes_a[path], nodes_b[path]
        if not _same_actions(na, nb):
            note_quarantine("spot %s: node %s action sets differ"
                            % (sid, _fmt_path(path)))
            continue
        if not path:
            _compare_root(sid, na, nb, note_quarantine, note_warning)
        else:
            _compare_deep_node(path, na, nb, nodes_a, nodes_b, deep)
    if deep["weight_total"] > 0:
        mean = deep["weighted_sum"] / deep["weight_total"]
    else:
        mean = 0.0
    if mean > FREQ_REJECT + EPS:
        note_quarantine(
            "spot %s: deep frequencies disagree (reach-weighted mean %.4f > %.2f)"
            % (sid, mean, FREQ_REJECT))
    elif mean > FREQ_WARN + EPS:
        note_warning(
            "spot %s: deep frequencies differ (reach-weighted mean %.4f, "
            "warning band %.2f-%.2f)" % (sid, mean, FREQ_WARN, FREQ_REJECT))
    worst = sorted(deep["worst"], key=lambda t: -t[0])[:DEEP_WORST_SHOWN]
    if worst:
        detail = "; ".join(
            "node %s key %s action %s diff %.4f" % (_fmt_path(p), k, a, d)
            for d, p, k, a in worst)
        note_warning("spot %s: worst deep entries: %s" % (sid, detail))
    _compare_root_ev(sid, sa, sb, note_quarantine, note_warning)


def cross_check_v2(pack_a, pack_b):
    """Compare two independent runs of the same spots.

    Returns (quarantine, warnings): quarantine is True when any spot
    is quarantined; warnings lists every finding, with quarantine
    reasons marked QUARANTINE and the rest marked WARNING. A
    quarantined spot never passes. Packs are compared, not validated
    here; validate each pack first when a verdict on it is needed.
    """
    findings = []
    quarantined = False

    def note_quarantine(msg):
        nonlocal quarantined
        quarantined = True
        findings.append("QUARANTINE " + msg)

    def note_warning(msg):
        findings.append("WARNING " + msg)

    if not isinstance(pack_a, dict) or not isinstance(pack_b, dict):
        return True, ["QUARANTINE one or both packs are not JSON objects"]
    spots_a, spots_b = pack_a.get("spots"), pack_b.get("spots")
    if not isinstance(spots_a, list) or not isinstance(spots_b, list):
        return True, ["QUARANTINE one or both packs have no spots list"]
    a_by_id, b_by_id = {}, {}
    for s in spots_a:
        if isinstance(s, dict) and isinstance(s.get("spot_id"), str):
            a_by_id.setdefault(s["spot_id"], s)
    for s in spots_b:
        if isinstance(s, dict) and isinstance(s.get("spot_id"), str):
            b_by_id.setdefault(s["spot_id"], s)
    for sid in sorted(set(a_by_id) | set(b_by_id)):
        if sid not in a_by_id:
            note_quarantine("spot %s: missing in pack A" % sid)
            continue
        if sid not in b_by_id:
            note_quarantine("spot %s: missing in pack B" % sid)
            continue
        _compare_spot(sid, a_by_id[sid], b_by_id[sid],
                      note_quarantine, note_warning)
    return quarantined, findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_pack(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            pack = json.load(f)
    except OSError as e:
        return None, "cannot read %s: %s" % (path, e)
    except json.JSONDecodeError as e:
        return None, "%s is not valid JSON: %s" % (path, e)
    if not isinstance(pack, dict):
        return None, "%s: pack is not a JSON object" % path
    return pack, None


def main(argv=None):
    """Minimal CLI. One pack: validate it. Two packs: cross-check them.
    Exit codes: 0 accept / agree, 1 warning, 2 reject / quarantine,
    3 usage or I/O error."""
    parser = argparse.ArgumentParser(
        description="Independent acceptance validator for spot_pack.v2 packs.")
    parser.add_argument("pack", help="pack JSON file to validate")
    parser.add_argument("other", nargs="?",
                        help="second pack JSON file: cross-check the two "
                             "packs instead of validating one")
    parser.add_argument("--allow-synthetic", action="store_true",
                        help="accept packs carrying synthetic test data")
    args = parser.parse_args(argv)
    pack, err = _load_pack(args.pack)
    if err:
        print("ERROR: %s" % err, file=sys.stderr)
        return 3
    if args.other is None:
        result = validate_v2_pack(pack, allow_synthetic=args.allow_synthetic)
        for f in result.failures:
            print("FAIL: %s" % f)
        for w in result.warnings:
            print("WARN: %s" % w)
        print("verdict: %s (%d failure(s), %d warning(s))"
              % (result.verdict, len(result.failures), len(result.warnings)))
        return {"accept": 0, "warning": 1, "reject": 2}[result.verdict]
    other, err = _load_pack(args.other)
    if err:
        print("ERROR: %s" % err, file=sys.stderr)
        return 3
    quarantined, findings = cross_check_v2(pack, other)
    for f in findings:
        print(f)
    if quarantined:
        print("quarantined: the two runs disagree")
        return 2
    print("agree: no quarantine (%d finding(s))" % len(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
