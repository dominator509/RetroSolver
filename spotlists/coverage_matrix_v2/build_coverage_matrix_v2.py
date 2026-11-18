#!/usr/bin/env python3
"""Build coverage-matrix v2 spot lists (config only).

Ranges are copied verbatim from the official TexasSolver v0.2.0 release
files under ranges/6max_range/. Every source file's SHA-256 is recorded.
No range, frequency, or EV is written by hand. Cells without a sourced
range are marked NO_RANGE. This script does not run a solver.

Usage:
  python3 build_coverage_matrix_v2.py <ranges/6max_range dir> <out dir>
The output directory must not already exist.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from itertools import combinations

RANKS = "23456789TJQKA"
SUITS = "cdhs"
RANK_VAL = {r: i for i, r in enumerate(RANKS, start=2)}
CARDS = [r + s for r in RANKS for s in SUITS]  # 2c,2d,...,As

# Texture classes, in the order given by the coverage-matrix brief (T1/T2 = first 8).
CLASS_ORDER = [
    "A-high dry",
    "K-high dry",
    "Q/J-high dry",
    "mid dry",
    "low dry",
    "paired high",
    "paired low",
    "monotone high",
    "monotone low",
    "two-tone A/K high",
    "two-tone broadway",
    "two-tone connected mid",
    "rainbow connected mid",
    "rainbow connected low",
    "A-low wet",
    "trips-board",
]
T12_CLASSES = CLASS_ORDER[:8]
T3_CLASSES = CLASS_ORDER[8:]

# v1 draft flops (already queued as T0). Reused as a canonical board only when
# the board also satisfies the class definition below.
V1_FLOPS = [
    ("a72r", "Ah,7c,2d"),
    ("k83r", "Kd,8s,3h"),
    ("qt5r", "Qh,Tc,5d"),
    ("j98r", "Jd,9c,8h"),
    ("t62tt", "Ts,6s,2d"),
    ("987tt", "9h,8h,7c"),
    ("752r", "7s,5d,2c"),
    ("kq4m", "Ks,Qs,4s"),
    ("883r", "8d,8c,3h"),
    ("ak5r", "As,Kd,5c"),
    ("643r", "6h,4d,3c"),
    ("qj2tt", "Qd,Jd,2c"),
]

# Same light tree as the v1 draft. A richer tree (flop 33/75 plus raise 60,
# turn/river 50/100 plus raise 60, all-in) was memory-killed on a 15 GiB host.
TREE = {
    "flop": {"oop": {"bet": [33], "allin": True}, "ip": {"bet": [33], "allin": True}},
    "turn": {"oop": {"bet": [75], "allin": True}, "ip": {"bet": [75], "allin": True}},
    "river": {"oop": {"bet": [75], "allin": True}, "ip": {"bet": [75], "allin": True}},
}

# Starting stack assumed 100bb when a cell is marked configured. The bundled
# range files do not state a depth; 40bb and 200bb are therefore NO_RANGE.
START_BB = 100.0
DEAD_SB = 0.5
DEAD_BB = 1.0

# 16 matchups from the coverage-matrix brief. The bundled tree labels the
# 6-max seat between UTG and CO as MP; that seat is HJ in the brief, so HJ
# cells use the MP files and record the mapping. Paths are relative to
# ranges/6max_range/.
MATCHUPS = [
    {
        "matchup_id": "srp-utg-bb",
        "pot_type": "SRP",
        "brief_name": "UTG-BB",
        "positions": {"ip": "UTG", "oop": "BB"},
        "dir": "UTG/2.5bb/BB/Call",
        "files": {"ip": "UTG_range.txt", "oop": "BB_range.txt"},
        "line": "UTG opens 2.5bb, HJ/CO/BTN/SB fold, BB calls",
        "dead_blinds": ["SB"],
        "ip_committed": 2.5,
        "oop_committed": 2.5,
    },
    {
        "matchup_id": "srp-hj-bb",
        "pot_type": "SRP",
        "brief_name": "HJ-BB",
        "positions": {"ip": "HJ", "oop": "BB"},
        "bundled_seat_map": {"HJ": "MP"},
        "dir": "MP/2.5bb/BB/Call",
        "files": {"ip": "MP_range.txt", "oop": "BB_range.txt"},
        "line": "HJ (bundled seat name MP) opens 2.5bb, CO/BTN/SB fold, BB calls",
        "dead_blinds": ["SB"],
        "ip_committed": 2.5,
        "oop_committed": 2.5,
    },
    {
        "matchup_id": "srp-co-bb",
        "pot_type": "SRP",
        "brief_name": "CO-BB",
        "positions": {"ip": "CO", "oop": "BB"},
        "dir": "CO/2.5bb/BB/Call",
        "files": {"ip": "CO_range.txt", "oop": "BB_range.txt"},
        "line": "CO opens 2.5bb, BTN/SB fold, BB calls",
        "dead_blinds": ["SB"],
        "ip_committed": 2.5,
        "oop_committed": 2.5,
    },
    {
        "matchup_id": "srp-btn-bb",
        "pot_type": "SRP",
        "brief_name": "BTN-BB",
        "positions": {"ip": "BTN", "oop": "BB"},
        "dir": "BTN/2.5bb/BB/Call",
        "files": {"ip": "BTN_range.txt", "oop": "BB_range.txt"},
        "line": "BTN opens 2.5bb, SB folds, BB calls",
        "dead_blinds": ["SB"],
        "ip_committed": 2.5,
        "oop_committed": 2.5,
    },
    {
        "matchup_id": "srp-sb-bb",
        "pot_type": "SRP",
        "brief_name": "SB-BB",
        "positions": {"ip": "BB", "oop": "SB"},
        "dir": "SB/3.0bb/BB/Call",
        "files": {"ip": "BB_range.txt", "oop": "SB_range.txt"},
        "line": "SB opens 3bb, BB calls",
        "dead_blinds": [],
        "ip_committed": 3.0,
        "oop_committed": 3.0,
    },
    {
        "matchup_id": "srp-co-btn",
        "pot_type": "SRP",
        "brief_name": "CO-BTN",
        "positions": {"ip": "BTN", "oop": "CO"},
        "dir": "CO/2.5bb/BTN/Call",
        "files": {"ip": "BTN_range.txt", "oop": "CO_range.txt"},
        "line": "CO opens 2.5bb, BTN calls, SB/BB fold",
        "dead_blinds": ["SB", "BB"],
        "ip_committed": 2.5,
        "oop_committed": 2.5,
    },
    {
        "matchup_id": "srp-hj-btn",
        "pot_type": "SRP",
        "brief_name": "HJ-BTN",
        "positions": {"ip": "BTN", "oop": "HJ"},
        "bundled_seat_map": {"HJ": "MP"},
        "dir": "MP/2.5bb/BTN/Call",
        "files": {"ip": "BTN_range.txt", "oop": "MP_range.txt"},
        "line": "HJ (bundled seat name MP) opens 2.5bb, BTN calls, CO/SB/BB fold",
        "dead_blinds": ["SB", "BB"],
        "ip_committed": 2.5,
        "oop_committed": 2.5,
    },
    {
        "matchup_id": "3bp-bb-btn",
        "pot_type": "3BP",
        "brief_name": "BB v BTN",
        "positions": {"ip": "BTN", "oop": "BB"},
        "dir": "BTN/2.5bb/BB/11.0bb/BTN/Call",
        "files": {"ip": "BTN_range.txt", "oop": "BB_range.txt"},
        "line": "BTN opens 2.5bb, SB folds, BB 3-bets to 11bb, BTN calls",
        "dead_blinds": ["SB"],
        "ip_committed": 11.0,
        "oop_committed": 11.0,
    },
    {
        "matchup_id": "3bp-bb-co",
        "pot_type": "3BP",
        "brief_name": "BB v CO",
        "positions": {"ip": "CO", "oop": "BB"},
        "dir": "CO/2.5bb/BB/11.0bb/CO/Call",
        "files": {"ip": "CO_range.txt", "oop": "BB_range.txt"},
        "line": "CO opens 2.5bb, BTN/SB fold, BB 3-bets to 11bb, CO calls",
        "dead_blinds": ["SB"],
        "ip_committed": 11.0,
        "oop_committed": 11.0,
    },
    {
        "matchup_id": "3bp-bb-utg",
        "pot_type": "3BP",
        "brief_name": "BB v UTG",
        "positions": {"ip": "UTG", "oop": "BB"},
        "dir": "UTG/2.5bb/BB/11.0bb/UTG/Call",
        "files": {"ip": "UTG_range.txt", "oop": "BB_range.txt"},
        "line": "UTG opens 2.5bb, HJ/CO/BTN/SB fold, BB 3-bets to 11bb, UTG calls",
        "dead_blinds": ["SB"],
        "ip_committed": 11.0,
        "oop_committed": 11.0,
    },
    {
        "matchup_id": "3bp-sb-btn",
        "pot_type": "3BP",
        "brief_name": "SB v BTN",
        "positions": {"ip": "BTN", "oop": "SB"},
        "dir": "BTN/2.5bb/SB/11.0bb/BTN/Call",
        "files": {"ip": "BTN_range.txt", "oop": "SB_range.txt"},
        "line": "BTN opens 2.5bb, SB 3-bets to 11bb, BB folds, BTN calls",
        "dead_blinds": ["BB"],
        "ip_committed": 11.0,
        "oop_committed": 11.0,
    },
    {
        "matchup_id": "3bp-btn-co",
        "pot_type": "3BP",
        "brief_name": "BTN(3b) v CO",
        "positions": {"ip": "BTN", "oop": "CO"},
        "dir": "CO/2.5bb/BTN/8.5bb/CO/Call",
        "files": {"ip": "BTN_range.txt", "oop": "CO_range.txt"},
        "line": "CO opens 2.5bb, BTN 3-bets to 8.5bb, SB/BB fold, CO calls",
        "dead_blinds": ["SB", "BB"],
        "ip_committed": 8.5,
        "oop_committed": 8.5,
    },
    {
        "matchup_id": "3bp-co-hj",
        "pot_type": "3BP",
        "brief_name": "CO(3b) v HJ",
        "positions": {"ip": "CO", "oop": "HJ"},
        "bundled_seat_map": {"HJ": "MP"},
        "dir": "MP/2.5bb/CO/8.5bb/MP/Call",
        "files": {"ip": "CO_range.txt", "oop": "MP_range.txt"},
        "line": "HJ (bundled seat name MP) opens 2.5bb, CO 3-bets to 8.5bb, BTN/SB/BB fold, HJ calls",
        "dead_blinds": ["SB", "BB"],
        "ip_committed": 8.5,
        "oop_committed": 8.5,
    },
    {
        "matchup_id": "4bp-btn-bb",
        "pot_type": "4BP",
        "brief_name": "BTN v BB",
        "positions": {"ip": "BTN", "oop": "BB"},
        "dir": "BTN/2.5bb/BB/11.0bb/BTN/24.0bb/BB/Call",
        "files": {"ip": "BTN_range.txt", "oop": "BB_range.txt"},
        "line": "BTN opens 2.5bb, SB folds, BB 3-bets to 11bb, BTN 4-bets to 24bb, BB calls",
        "dead_blinds": ["SB"],
        "ip_committed": 24.0,
        "oop_committed": 24.0,
    },
    {
        "matchup_id": "4bp-co-btn",
        "pot_type": "4BP",
        "brief_name": "CO v BTN",
        "positions": {"ip": "BTN", "oop": "CO"},
        "dir": "CO/2.5bb/BTN/8.5bb/CO/22.0bb/BTN/Call",
        "files": {"ip": "BTN_range.txt", "oop": "CO_range.txt"},
        "line": "CO opens 2.5bb, BTN 3-bets to 8.5bb, CO 4-bets to 22bb, SB/BB fold, BTN calls",
        "dead_blinds": ["SB", "BB"],
        "ip_committed": 22.0,
        "oop_committed": 22.0,
    },
    {
        "matchup_id": "4bp-utg-bb",
        "pot_type": "4BP",
        "brief_name": "UTG v BB",
        "positions": {"ip": "UTG", "oop": "BB"},
        "dir": "UTG/2.5bb/BB/11.0bb/UTG/24.0bb/BB/Call",
        "files": {"ip": "UTG_range.txt", "oop": "BB_range.txt"},
        "line": "UTG opens 2.5bb, HJ/CO/BTN/SB fold, BB 3-bets to 11bb, UTG 4-bets to 24bb, BB calls",
        "dead_blinds": ["SB"],
        "ip_committed": 24.0,
        "oop_committed": 24.0,
    },
]

DEPTHS = [40, 100, 200]


def parse_board(board: str):
    cards = board.split(",")
    parsed = []
    for c in cards:
        if len(c) != 2 or c[0] not in RANK_VAL or c[1] not in SUITS:
            raise ValueError("bad card %r in board %r" % (c, board))
        parsed.append((c[0], c[1], RANK_VAL[c[0]]))
    return parsed


def board_features(board: str):
    cards = parse_board(board)
    ranks = [v for _, _, v in cards]
    suits = [s for _, s, _ in cards]
    rc = Counter(ranks)
    sc = Counter(suits)
    high = max(ranks)
    is_trips = any(n == 3 for n in rc.values())
    is_paired = any(n == 2 for n in rc.values()) and not is_trips
    pair_rank = max((r for r, n in rc.items() if n >= 2), default=None)
    max_suit = max(sc.values())
    pattern = "monotone" if max_suit == 3 else "two-tone" if max_suit == 2 else "rainbow"
    unique = sorted(set(ranks))
    span = unique[-1] - unique[0] if unique else 0
    # Strongly connected: 3 distinct ranks that fit in a 5-card straight window
    # (span <= 4). Ace-low (wheel) uses A as 1 with ranks in {A,2,3,4,5}.
    strongly_connected = False
    if not is_trips and not is_paired and len(unique) == 3:
        if span <= 4:
            strongly_connected = True
        wheel = sorted({1 if r == 14 else r for r in unique if r == 14 or r <= 5})
        if len(wheel) == 3 and wheel[-1] - wheel[0] <= 4:
            strongly_connected = True
    side = sorted(r for r in ranks if r != 14)
    return {
        "ranks": ranks,
        "high": high,
        "is_trips": is_trips,
        "is_paired": is_paired,
        "pair_rank": pair_rank,
        "pattern": pattern,
        "strongly_connected": strongly_connected,
        "broadway_count": sum(1 for r in ranks if r >= 10),
        "side_low": len(side) == 2 and all(r <= 7 for r in side),
        "second_high": sorted(ranks, reverse=True)[1],
    }


def matches_class(board: str, cls: str) -> bool:
    f = board_features(board)
    if cls == "trips-board":
        return f["is_trips"]
    if cls == "paired high":
        return f["is_paired"] and f["pair_rank"] >= 10
    if cls == "paired low":
        return f["is_paired"] and f["pair_rank"] is not None and f["pair_rank"] <= 9
    if cls == "monotone high":
        return f["pattern"] == "monotone" and not f["is_trips"] and not f["is_paired"] and f["high"] >= 10
    if cls == "monotone low":
        return f["pattern"] == "monotone" and not f["is_trips"] and not f["is_paired"] and f["high"] <= 9
    if cls == "A-low wet":
        if f["is_trips"] or f["is_paired"] or f["pattern"] == "monotone" or f["high"] != 14 or not f["side_low"]:
            return False
        # wet: flush draw and/or the two side cards (or the wheel) are connected
        return f["pattern"] == "two-tone" or f["strongly_connected"]
    if cls == "A-high dry":
        return (
            not f["is_trips"]
            and not f["is_paired"]
            and f["pattern"] == "rainbow"
            and f["high"] == 14
            and f["second_high"] <= 9
            and not f["strongly_connected"]
            and not (f["side_low"] and f["strongly_connected"])
        )
    if cls == "K-high dry":
        return (
            not f["is_trips"]
            and not f["is_paired"]
            and f["pattern"] == "rainbow"
            and f["high"] == 13
            and not f["strongly_connected"]
        )
    if cls == "Q/J-high dry":
        return (
            not f["is_trips"]
            and not f["is_paired"]
            and f["pattern"] == "rainbow"
            and f["high"] in (12, 11)
            and not f["strongly_connected"]
        )
    if cls == "mid dry":
        return (
            not f["is_trips"]
            and not f["is_paired"]
            and f["pattern"] == "rainbow"
            and f["high"] in (10, 9, 8)
            and not f["strongly_connected"]
        )
    if cls == "low dry":
        return (
            not f["is_trips"]
            and not f["is_paired"]
            and f["pattern"] == "rainbow"
            and f["high"] <= 7
            and not f["strongly_connected"]
        )
    if cls == "two-tone A/K high":
        return (
            not f["is_trips"]
            and not f["is_paired"]
            and f["pattern"] == "two-tone"
            and f["high"] in (14, 13)
            and not (f["high"] == 14 and f["side_low"] and (f["pattern"] == "two-tone" or f["strongly_connected"]))
        )
    if cls == "two-tone broadway":
        return (
            not f["is_trips"]
            and not f["is_paired"]
            and f["pattern"] == "two-tone"
            and f["broadway_count"] >= 2
            and f["high"] <= 12
        )
    if cls == "two-tone connected mid":
        return (
            not f["is_trips"]
            and not f["is_paired"]
            and f["pattern"] == "two-tone"
            and f["strongly_connected"]
            and f["high"] in (8, 9, 10, 11)
        )
    if cls == "rainbow connected mid":
        return (
            not f["is_trips"]
            and not f["is_paired"]
            and f["pattern"] == "rainbow"
            and f["strongly_connected"]
            and f["high"] in (8, 9, 10, 11)
        )
    if cls == "rainbow connected low":
        return (
            not f["is_trips"]
            and not f["is_paired"]
            and f["pattern"] == "rainbow"
            and f["strongly_connected"]
            and f["high"] <= 7
        )
    raise ValueError(cls)


def pattern_suffix(board: str) -> str:
    f = board_features(board)
    if f["is_trips"]:
        return "t"
    return {"rainbow": "r", "two-tone": "tt", "monotone": "m"}[f["pattern"]]


def board_key(board: str) -> str:
    cards = parse_board(board)
    # unique ranks high-to-low, then pair/trips still listed once; for pairs
    # include the kicker. Use rank letters in descending rank order as they
    # appear when cards are sorted by rank desc, suit asc.
    cards_sorted = sorted(cards, key=lambda x: (-x[2], SUITS.index(x[1])))
    letters = "".join(c[0].lower() if c[0] != "T" else "t" for c in cards_sorted)
    return letters + pattern_suffix(board)


def format_board(cards):
    # cards are rank+suit strings; present high-to-low, suit asc within rank
    parsed = [(c[0], c[1], RANK_VAL[c[0]]) for c in cards]
    parsed.sort(key=lambda x: (-x[2], SUITS.index(x[1])))
    return ",".join(r + s for r, s, _ in parsed)


def all_flops_lex():
    for trip in combinations(CARDS, 3):
        yield format_board(trip)


def choose_canonical_boards():
    """Reuse a v1 board when it satisfies the class; otherwise the first flop
    in lexicographic combinations of cards ordered 2c..As that satisfies it
    and is not already chosen."""
    ledger = []
    chosen = {}
    used = set()
    v1_by_board = {b: k for k, b in V1_FLOPS}

    # Classify every v1 board for the ledger (including those not reused).
    v1_class_hits = []
    for key, board in V1_FLOPS:
        hits = [c for c in CLASS_ORDER if matches_class(board, c)]
        v1_class_hits.append({"v1_key": key, "board": board, "matching_classes": hits})

    for cls in CLASS_ORDER:
        reused = None
        for key, board in V1_FLOPS:
            if board in used:
                continue
            if matches_class(board, cls):
                reused = (key, board)
                break
        if reused:
            key, board = reused
            used.add(board)
            chosen[cls] = {"key": key, "board": board}
            ledger.append({
                "class": cls,
                "board": board,
                "key": key,
                "source": "v1_reuse",
                "why": "This board is in the v1 12-flop draft and satisfies the class definition, so it is reused as the canonical board for continuity with T0.",
            })
            continue
        found = None
        for board in all_flops_lex():
            if board in used:
                continue
            if matches_class(board, cls):
                found = board
                break
        if not found:
            raise SystemExit("no flop found for class %s" % cls)
        key = board_key(found)
        used.add(found)
        chosen[cls] = {"key": key, "board": found}
        ledger.append({
            "class": cls,
            "board": found,
            "key": key,
            "source": "lex_first",
            "why": "No unused v1 board satisfies the class definition. This is the first flop, in combinations of cards ordered 2c,2d,2h,2s,...,As, that satisfies the class and is not already a canonical board.",
        })
    return chosen, ledger, v1_class_hits


def pot_and_stack(m, start=START_BB):
    dead = 0.0
    if "SB" in m["dead_blinds"]:
        dead += DEAD_SB
    if "BB" in m["dead_blinds"]:
        dead += DEAD_BB
    pot = m["ip_committed"] + m["oop_committed"] + dead
    # effective stack is the lesser remaining; both commit the same in these HU lines
    eff = start - max(m["ip_committed"], m["oop_committed"])
    return pot, eff


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, obj):
    with open(path, "x", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
        f.write("\n")


def load_range(root, rel):
    path = os.path.join(root, *rel.split("/"))
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("ascii").strip()
    return text, hashlib.sha256(raw).hexdigest()


def cell_id(matchup_id, depth, board_key_):
    return "%s-%dbb-%s" % (matchup_id, depth, board_key_)


def balance_block(cells, label):
    """Count configured vs NO_RANGE by matchup and depth. Flag under-representation
    among configured cells in this set."""
    by_matchup = defaultdict(lambda: Counter())
    by_depth = defaultdict(lambda: Counter())
    by_class = defaultdict(lambda: Counter())
    by_pot = defaultdict(lambda: Counter())
    for c in cells:
        st = c["status"]
        by_matchup[c["matchup_id"]][st] += 1
        by_depth[c["depth_bb"]][st] += 1
        by_class[c["texture_class"]][st] += 1
        by_pot[c["pot_type"]][st] += 1
    configured_by_matchup = {k: v.get("configured", 0) for k, v in by_matchup.items()}
    configured_by_depth = {k: v.get("configured", 0) for k, v in by_depth.items()}
    # Under-represented: a matchup or depth with fewer configured cells than the
    # max in this tier, when the shortfall is not solely because the cell is
    # NO_RANGE for a documented reason that applies equally. We still report
    # raw counts and mark any matchup/depth with zero configured cells when
    # some other matchup/depth in the same tier has configured cells.
    flags = []
    if configured_by_matchup:
        mx = max(configured_by_matchup.values())
        mn = min(configured_by_matchup.values())
        if mx > 0 and mn < mx:
            short = [k for k, n in configured_by_matchup.items() if n < mx]
            flags.append({
                "scope": "matchup",
                "detail": "configured counts are not equal across matchups",
                "max_configured": mx,
                "min_configured": mn,
                "short_matchups": short,
            })
    if configured_by_depth:
        mx = max(configured_by_depth.values())
        mn = min(configured_by_depth.values())
        if mx > 0 and mn < mx:
            short = [k for k, n in configured_by_depth.items() if n < mx]
            flags.append({
                "scope": "depth",
                "detail": "configured counts are not equal across depths",
                "max_configured": mx,
                "min_configured": mn,
                "short_depths": short,
            })
    return {
        "tier": label,
        "n_cells": len(cells),
        "status_totals": dict(Counter(c["status"] for c in cells)),
        "by_matchup": {k: dict(v) for k, v in by_matchup.items()},
        "by_depth": {str(k): dict(v) for k, v in by_depth.items()},
        "by_texture_class": {k: dict(v) for k, v in by_class.items()},
        "by_pot_type": {k: dict(v) for k, v in by_pot.items()},
        "flags": flags,
    }


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 1
    root, out = argv
    if os.path.exists(out):
        print("refusing to overwrite " + out, file=sys.stderr)
        return 1
    os.makedirs(out)

    chosen, board_ledger, v1_class_hits = choose_canonical_boards()

    # Load and hash every range file used by the 16 matchups.
    range_files = {}
    range_text = {}
    for m in MATCHUPS:
        for side, fn in m["files"].items():
            rel = m["dir"] + "/" + fn
            if rel in range_text:
                continue
            text, digest = load_range(root, rel)
            range_text[rel] = text
            range_files[rel] = digest

    # Build 768 cells (16 x 3 x 16).
    cells = []
    for m in MATCHUPS:
        for depth in DEPTHS:
            for cls in CLASS_ORDER:
                b = chosen[cls]
                cid = cell_id(m["matchup_id"], depth, b["key"])
                if depth != 100:
                    status = "NO_RANGE"
                    reason = (
                        "The bundled TexasSolver v0.2.0 range files do not state a stack depth. "
                        "Configured cells use a 100bb assumption already used by the v1 draft. "
                        "No verified range source was found for %dbb, so this cell is NO_RANGE. "
                        "Ranges were not copied across depths."
                    ) % depth
                    pot = None
                    eff = None
                else:
                    status = "configured"
                    reason = (
                        "Heads-up Call ranges exist in the TexasSolver v0.2.0 bundle at %s. "
                        "Copied verbatim. 100bb stack is assumed (the files do not state a depth)."
                    ) % m["dir"]
                    pot, eff = pot_and_stack(m, START_BB)
                cells.append({
                    "cell_id": cid,
                    "matchup_id": m["matchup_id"],
                    "brief_name": m["brief_name"],
                    "pot_type": m["pot_type"],
                    "positions": m["positions"],
                    "depth_bb": depth,
                    "texture_class": cls,
                    "board": b["board"],
                    "board_key": b["key"],
                    "status": status,
                    "reason": reason,
                    "pot": pot,
                    "effective_stack": eff,
                    "range_dir": m["dir"],
                    "range_files": {side: m["dir"] + "/" + fn for side, fn in m["files"].items()},
                    "bundled_seat_map": m.get("bundled_seat_map"),
                })

    # T0 is the already-queued v1 list: 6 families x 12 flops at 100bb, not the
    # 16-class canonical grid. It is recorded as a pointer to that list.
    t0_families = {
        "srp-btn-bb", "srp-co-bb", "srp-sb-bb",
        "3bp-bb-btn", "3bp-bb-co", "3bp-sb-bb",
    }
    t0_spots = []
    # Load v1 ids from a sibling file if present is done by the caller; we
    # reconstruct the 72 ids in the same order as the v1 builder.
    v1_family_order = [
        "srp-btn-bb", "srp-co-bb", "srp-sb-bb",
        "3bp-bb-btn", "3bp-bb-co", "3bp-sb-bb",
    ]
    for fam in v1_family_order:
        for fkey, _board in V1_FLOPS:
            t0_spots.append({
                "spot_id": "v1-%s-100bb-%s" % (fam, fkey),
                "matchup_id": fam,
                "depth_bb": 100,
                "board_key": fkey,
                "status": "configured",
                "source_list": "spotlists/spotlist_v1_draft.json",
            })

    def cells_for_tier(classes, depths):
        want = {(c["matchup_id"], c["depth_bb"], c["texture_class"]) for c in cells
                if c["texture_class"] in classes and c["depth_bb"] in depths}
        return [c for c in cells if (c["matchup_id"], c["depth_bb"], c["texture_class"]) in want]

    t1_cells = cells_for_tier(T12_CLASSES, [100])
    t2_cells = cells_for_tier(T12_CLASSES, [40, 200])
    t3_cells = cells_for_tier(T3_CLASSES, [40, 100, 200])

    # Build runnable spot objects for every configured 100bb cell (T1 and T3).
    def spot_from_cell(c):
        m = next(x for x in MATCHUPS if x["matchup_id"] == c["matchup_id"])
        rng = {
            "ip": range_text[m["dir"] + "/" + m["files"]["ip"]],
            "oop": range_text[m["dir"] + "/" + m["files"]["oop"]],
        }
        notes = (
            "%s. Ranges verbatim from TexasSolver v0.2.0 ranges/6max_range/%s "
            "(sha256 in range_sources). 100bb assumed."
        ) % (m["line"], m["dir"])
        if m.get("bundled_seat_map"):
            notes += " Bundled seat-name map: %s." % m["bundled_seat_map"]
        return {
            "spot_id": c["cell_id"],
            "matchup_id": c["matchup_id"],
            "positions": c["positions"],
            "pot": c["pot"],
            "effective_stack": c["effective_stack"],
            "board": c["board"],
            "texture_class": c["texture_class"],
            "depth_bb": c["depth_bb"],
            "ranges": rng,
            "bet_sizes": TREE,
            "accuracy_target": 0.5,
            "notes": notes,
        }

    t1_spots = [spot_from_cell(c) for c in t1_cells if c["status"] == "configured"]
    t3_spots_100 = [spot_from_cell(c) for c in t3_cells if c["status"] == "configured"]

    report = {
        "schema": "retrosolver.coverage_matrix_v2.report",
        "grid": {
            "matchups": 16,
            "depths": 3,
            "texture_classes": 16,
            "cells": 16 * 3 * 16,
        },
        "assumptions": [
            "Stack depth 100bb is assumed for configured cells; the bundled range files do not state a depth.",
            "40bb and 200bb cells are NO_RANGE. Ranges were not reused across depths.",
            "The bundled 6-max tree labels the seat between UTG and CO as MP. Brief matchups that say HJ use those MP files and record bundled_seat_map.",
            "Pot and effective stack are computed from the action-line bet sizes in the bundled path, plus folded-blind dead money (SB 0.5bb, BB 1.0bb when that blind folded).",
            "TexasSolver v0.2.0 console_solver has no rake setting. Configured spots are rake-free. A standard-rake variant is not expressible in that CLI; this report does not mark those cells UNCOMPARABLE, because the v1 draft already queued them as rake-free. The limitation is recorded here.",
            "T0 is the existing 72-spot v1 draft (6 pot families x 12 flops at 100bb), not a slice of the 16-class grid.",
            "T1 is all 16 matchups at 100bb x the first 8 texture classes. T2 is 40bb and 200bb x those same 8 classes. T3 is the remaining 8 classes across all 16 matchups and 3 depths.",
        ],
        "texture_class_definitions": {
            "trips-board": "Three cards of the same rank.",
            "paired high": "Exactly one pair, pair rank ten or higher.",
            "paired low": "Exactly one pair, pair rank nine or lower.",
            "monotone high": "Unpaired, not trips, all three suits equal, high card ten or higher.",
            "monotone low": "Unpaired, not trips, all three suits equal, high card nine or lower.",
            "A-low wet": "Unpaired, not monotone, ace-high, both side cards seven or lower, and either a flush draw (two-tone) or strongly connected (including the ace-to-five wheel).",
            "A-high dry": "Unpaired rainbow ace-high, second card nine or lower, not strongly connected.",
            "K-high dry": "Unpaired rainbow king-high, not strongly connected.",
            "Q/J-high dry": "Unpaired rainbow queen- or jack-high, not strongly connected.",
            "mid dry": "Unpaired rainbow, high card ten, nine, or eight, not strongly connected.",
            "low dry": "Unpaired rainbow, high card seven or lower, not strongly connected.",
            "two-tone A/K high": "Unpaired two-tone, ace- or king-high, and not an A-low wet board.",
            "two-tone broadway": "Unpaired two-tone, at least two broadway cards (ten or higher), high card queen or lower (so ace/king-high two-tone boards stay in two-tone A/K high).",
            "two-tone connected mid": "Unpaired two-tone, strongly connected, high card eight through jack.",
            "rainbow connected mid": "Unpaired rainbow, strongly connected, high card eight through jack.",
            "rainbow connected low": "Unpaired rainbow, strongly connected, high card seven or lower.",
            "strongly_connected": "Three distinct ranks whose span is at most 4 (they fit in a five-card straight window), or the ace-low wheel equivalent.",
        },
        "cells": cells,
        "balance": [
            balance_block(
                [{"matchup_id": s["matchup_id"], "depth_bb": 100, "texture_class": s["board_key"],
                  "pot_type": "T0", "status": "configured"} for s in t0_spots],
                "T0",
            ),
            balance_block(t1_cells, "T1"),
            balance_block(t2_cells, "T2"),
            balance_block(t3_cells, "T3"),
        ],
        "v1_flop_class_hits": v1_class_hits,
        "status_totals_all_cells": dict(Counter(c["status"] for c in cells)),
    }

    # T0 balance uses board keys as a stand-in texture; rewrite a clearer T0 block.
    report["balance"][0] = {
        "tier": "T0",
        "n_cells": 72,
        "status_totals": {"configured": 72},
        "by_matchup": {fam: {"configured": 12} for fam in v1_family_order},
        "by_depth": {"100": {"configured": 72}},
        "by_texture_class": {k: {"configured": 6} for k, _ in V1_FLOPS},
        "by_pot_type": {"SRP": {"configured": 36}, "3BP": {"configured": 36}},
        "flags": [],
        "note": "T0 is the v1 draft grid (6 families x 12 flops), not the 16x3x16 matrix. Each family and each v1 flop appears equally (12 and 6 configured spots). 10 of the 16 brief matchups and both non-100bb depths are absent from T0 by construction; they are not flags against T0, because T0 was defined as this 72-spot list.",
    }

    header_sources = {
        "release": "TexasSolver-v0.2.0-Windows.zip (github.com/bupticybee/TexasSolver/releases/tag/v0.2.0)",
        "root": "ranges/6max_range",
        "files_sha256": range_files,
    }

    def list_doc(list_id, notes, spots):
        return {
            "schema": "retrosolver.spot_list.v1",
            "list_id": list_id,
            "notes": notes,
            "range_sources": header_sources,
            "solver": {"name": "TexasSolver", "version": "v0.2.0"},
            "defaults": {
                "thread_num": 8,
                "max_iteration": 300,
                "print_interval": 10,
                "use_isomorphism": 1,
                "dump_rounds": 1,
                "allin_threshold": 0.67,
            },
            "spots": spots,
        }

    os.makedirs(os.path.join(out, "manifests"))
    write_json(os.path.join(out, "board_ledger.json"), {
        "card_order": "ranks 2-A, suits cdhs, then itertools.combinations of the 52 cards in that order; boards are written high-rank-first, suit ascending within a rank",
        "v1_reuse_rule": "If a v1 draft board satisfies the class definition and is not already used, it is the canonical board for that class.",
        "lex_first_rule": "Otherwise the first flop in the card order that satisfies the class and is not already used.",
        "canonical_boards": [{"class": cls, **chosen[cls], "tier_group": "T1_T2" if cls in T12_CLASSES else "T3"} for cls in CLASS_ORDER],
        "entries": board_ledger,
        "v1_flop_class_hits": v1_class_hits,
    })
    write_json(os.path.join(out, "range_sources.json"), header_sources)
    write_json(os.path.join(out, "matchups.json"), {
        "hj_seat_mapping": "The bundled 6-max tree uses MP for the seat between UTG and CO. Brief matchups named HJ use those MP range files and record bundled_seat_map.",
        "pot_and_stack": "pot = ip_committed + oop_committed + dead blinds (0.5 for a folded SB, 1.0 for a folded BB). effective_stack = 100 - the line's committed amount. 100bb start assumed.",
        "matchups": [
            dict(m, pot_100bb=pot_and_stack(m)[0], effective_stack_100bb=pot_and_stack(m)[1])
            for m in MATCHUPS
        ],
    })
    write_json(os.path.join(out, "report.json"), report)
    write_json(os.path.join(out, "manifests", "t0_manifest.json"), {
        "tier": "T0",
        "definition": "The 72-spot v1 draft (6 pot families x 12 flops at 100bb), already queued. Source list: spotlists/spotlist_v1_draft.json.",
        "n_spots": 72,
        "status_totals": {"configured": 72},
        "spots": t0_spots,
    })
    write_json(os.path.join(out, "manifests", "t1_manifest.json"), {
        "tier": "T1",
        "definition": "All 16 matchups at 100bb x the first 8 texture classes (128 cells).",
        "texture_classes": T12_CLASSES,
        "depths": [100],
        "n_cells": len(t1_cells),
        "status_totals": dict(Counter(c["status"] for c in t1_cells)),
        "cells": [{k: c[k] for k in ("cell_id", "matchup_id", "brief_name", "pot_type", "depth_bb", "texture_class", "board", "board_key", "status", "pot", "effective_stack", "range_dir")} for c in t1_cells],
    })
    write_json(os.path.join(out, "manifests", "t2_manifest.json"), {
        "tier": "T2",
        "definition": "All 16 matchups at 40bb and 200bb x the first 8 texture classes (256 cells).",
        "texture_classes": T12_CLASSES,
        "depths": [40, 200],
        "n_cells": len(t2_cells),
        "status_totals": dict(Counter(c["status"] for c in t2_cells)),
        "cells": [{k: c[k] for k in ("cell_id", "matchup_id", "brief_name", "pot_type", "depth_bb", "texture_class", "board", "board_key", "status", "reason")} for c in t2_cells],
    })
    write_json(os.path.join(out, "manifests", "t3_manifest.json"), {
        "tier": "T3",
        "definition": "The remaining 8 texture classes across all 16 matchups and all 3 depths (384 cells).",
        "texture_classes": T3_CLASSES,
        "depths": [40, 100, 200],
        "n_cells": len(t3_cells),
        "status_totals": dict(Counter(c["status"] for c in t3_cells)),
        "cells": [{k: c[k] for k in ("cell_id", "matchup_id", "brief_name", "pot_type", "depth_bb", "texture_class", "board", "board_key", "status", "pot", "effective_stack", "range_dir") if k in c} for c in t3_cells],
    })
    write_json(
        os.path.join(out, "t1_spotlist.json"),
        list_doc(
            "retrosolver-coverage-matrix-v2-t1",
            "Coverage matrix v2 T1: 16 matchups at 100bb x 8 texture classes. "
            "Ranges copied verbatim from TexasSolver v0.2.0 bundled files listed in range_sources. "
            "100bb is assumed. Rake-free (the TexasSolver CLI has no rake setting).",
            t1_spots,
        ),
    )
    write_json(
        os.path.join(out, "t3_100bb_spotlist.json"),
        list_doc(
            "retrosolver-coverage-matrix-v2-t3-100bb",
            "Coverage matrix v2 T3, 100bb cells only (the 40bb and 200bb T3 cells are NO_RANGE). "
            "16 matchups x 8 remaining texture classes. Ranges copied verbatim from TexasSolver v0.2.0 "
            "bundled files listed in range_sources. 100bb is assumed. Rake-free.",
            t3_spots_100,
        ),
    )

    # Human-readable report (no private-repo or issue references).
    lines = []
    lines.append("# Coverage matrix v2")
    lines.append("")
    lines.append("Config only. No solver was run to produce this directory. Ranges are copied verbatim from the official TexasSolver v0.2.0 release (`ranges/6max_range/`); SHA-256 of each source file is in `range_sources.json`.")
    lines.append("")
    lines.append("## Grid and tiers")
    lines.append("")
    lines.append("- 16 matchups x 3 depths (40, 100, 200bb) x 16 flop texture classes = 768 flop-root cells.")
    lines.append("- T0: the existing 72-spot v1 draft (6 pot families x 12 flops at 100bb) in `spotlists/spotlist_v1_draft.json`. Production batches start here.")
    lines.append("- T1: 16 matchups at 100bb x the first 8 texture classes (128 cells).")
    lines.append("- T2: 40bb and 200bb x those same 8 classes (256 cells).")
    lines.append("- T3: the remaining 8 classes across all matchups and depths (384 cells).")
    lines.append("")
    lines.append("## Cell status")
    lines.append("")
    lines.append("- 256 configured (all 16 matchups x 16 classes at 100bb).")
    lines.append("- 512 NO_RANGE (every 40bb and 200bb cell). The bundled files do not state a stack depth; 100bb is the assumption already used by the v1 draft, and ranges were not copied across depths. No other verified range source was used.")
    lines.append("- 0 UNCOMPARABLE. Configured spots are rake-free because TexasSolver v0.2.0 `console_solver` has no rake setting. That limitation is recorded rather than used to blank out the 100bb cells, which follow the same rake-free convention as the v1 draft.")
    lines.append("")
    lines.append("## Canonical boards")
    lines.append("")
    lines.append("One board per texture class, used in every matchup/depth cell of that class. v1 boards are reused when they satisfy the class definition; otherwise the first matching flop in a fixed card order (ranks 2-A, suits c-d-h-s, `itertools.combinations`). See `board_ledger.json`.")
    lines.append("")
    lines.append("| Class | Tier group | Board | Key | Source |")
    lines.append("|---|---|---|---|---|")
    for cls in CLASS_ORDER:
        e = next(x for x in board_ledger if x["class"] == cls)
        grp = "T1/T2" if cls in T12_CLASSES else "T3"
        lines.append("| %s | %s | `%s` | `%s` | %s |" % (cls, grp, e["board"], e["key"], e["source"]))
    lines.append("")
    lines.append("## Matchups and pot math (100bb)")
    lines.append("")
    lines.append("The bundled tree uses MP for the 6-max seat between UTG and CO. Brief names that say HJ use those MP files (`bundled_seat_map`).")
    lines.append("")
    lines.append("| Matchup | Type | Path | Pot (bb) | Effective stack (bb) |")
    lines.append("|---|---|---|---|---|")
    for m in MATCHUPS:
        pot, eff = pot_and_stack(m)
        lines.append("| %s | %s | `%s` | %s | %s |" % (m["brief_name"], m["pot_type"], m["dir"], pot, eff))
    lines.append("")
    lines.append("## Balance check")
    lines.append("")
    lines.append("- T0: 6 families x 12 flops, 12 spots per family, 6 per flop, 36 SRP and 36 3-bet. Equal inside that list. The other 10 brief matchups and the 40/200bb depths are outside T0 by definition.")
    lines.append("- T1: 128/128 configured. 8 spots per matchup, 16 per class, all at 100bb. No under-representation.")
    lines.append("- T2: 256/256 NO_RANGE. Every matchup and both depths are equally empty of ranges.")
    lines.append("- T3: 128 configured (100bb) and 256 NO_RANGE (40bb and 200bb). Every matchup has 8 configured spots (the 100bb half of its 24 cells). The 40bb and 200bb depths have zero configured spots; that is the missing range source, not a curation imbalance.")
    lines.append("")
    lines.append("## Tree")
    lines.append("")
    lines.append("Same light tree as the v1 draft: flop 33% plus all-in, turn 75% plus all-in, river 75% plus all-in, accuracy 0.5% of pot, max 300 iterations. The richer tree was memory-killed on a 15 GiB host with full ranges.")
    lines.append("")
    with open(os.path.join(out, "README.md"), "x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("wrote %s" % out)
    print("canonical boards:")
    for cls in CLASS_ORDER:
        e = next(x for x in board_ledger if x["class"] == cls)
        print("  %s: %s (%s, %s)" % (cls, e["board"], e["key"], e["source"]))
    print("configured 100bb cells:", sum(1 for c in cells if c["status"] == "configured"))
    print("NO_RANGE cells:", sum(1 for c in cells if c["status"] == "NO_RANGE"))
    print("T1 configured spots:", len(t1_spots))
    print("T3 100bb configured spots:", len(t3_spots_100))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
