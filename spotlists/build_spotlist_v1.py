#!/usr/bin/env python3
"""Build the DRAFT production spot list v1 (config only - no solving, no strategy numbers).

Ranges are NOT written by hand: each preflop range is read verbatim from the range
files shipped inside the official TexasSolver v0.2.0 release (ranges/6max_range/...),
and the SHA-256 of every source file is recorded in the list so the input is auditable.

Usage:
  python3 build_spotlist_v1.py <TexasSolver ranges/6max_range dir> <out spotlist.json>
Then:
  python3 ../batch_generate.py <out spotlist.json> --out <batch dir>
"""
import hashlib
import json
import os
import sys

# Draft flop subset for curriculum v1 (texture coverage). Board choice is curation, for review.
FLOPS = [
    ("a72r", "Ah,7c,2d"), ("k83r", "Kd,8s,3h"), ("qt5r", "Qh,Tc,5d"), ("j98r", "Jd,9c,8h"),
    ("t62tt", "Ts,6s,2d"), ("987tt", "9h,8h,7c"), ("752r", "7s,5d,2c"), ("kq4m", "Ks,Qs,4s"),
    ("883r", "8d,8c,3h"), ("ak5r", "As,Kd,5c"), ("643r", "6h,4d,3c"), ("qj2tt", "Qd,Jd,2c"),
]

# Pot families. Source paths are relative to ranges/6max_range in the TexasSolver v0.2.0 release.
# pot / effective_stack in bb, from the action line (open size, 3-bet size, 0.5bb dead SB where SB folded).
FAMILIES = [
    {"key": "srp-btn-bb", "positions": {"ip": "BTN", "oop": "BB"}, "dir": "BTN/2.5bb/BB/Call",
     "files": {"ip": "BTN_range.txt", "oop": "BB_range.txt"}, "pot": 5.5, "effective_stack": 97.5,
     "line": "BTN opens 2.5bb, SB folds, BB calls"},
    {"key": "srp-co-bb", "positions": {"ip": "CO", "oop": "BB"}, "dir": "CO/2.5bb/BB/Call",
     "files": {"ip": "CO_range.txt", "oop": "BB_range.txt"}, "pot": 5.5, "effective_stack": 97.5,
     "line": "CO opens 2.5bb, BTN/SB fold, BB calls"},
    {"key": "srp-sb-bb", "positions": {"ip": "BB", "oop": "SB"}, "dir": "SB/3.0bb/BB/Call",
     "files": {"ip": "BB_range.txt", "oop": "SB_range.txt"}, "pot": 6, "effective_stack": 97,
     "line": "SB opens 3bb, BB calls"},
    {"key": "3bp-bb-btn", "positions": {"ip": "BTN", "oop": "BB"}, "dir": "BTN/2.5bb/BB/11.0bb/BTN/Call",
     "files": {"ip": "BTN_range.txt", "oop": "BB_range.txt"}, "pot": 22.5, "effective_stack": 89,
     "line": "BTN opens 2.5bb, SB folds, BB 3-bets to 11bb, BTN calls"},
    {"key": "3bp-bb-co", "positions": {"ip": "CO", "oop": "BB"}, "dir": "CO/2.5bb/BB/11.0bb/CO/Call",
     "files": {"ip": "CO_range.txt", "oop": "BB_range.txt"}, "pot": 22.5, "effective_stack": 89,
     "line": "CO opens 2.5bb, BTN/SB fold, BB 3-bets to 11bb, CO calls"},
    {"key": "3bp-sb-bb", "positions": {"ip": "BB", "oop": "SB"}, "dir": "SB/3.0bb/BB/9.0bb/SB/Call",
     "files": {"ip": "BB_range.txt", "oop": "SB_range.txt"}, "pot": 18, "effective_stack": 91,
     "line": "SB opens 3bb, BB 3-bets to 9bb, SB calls"},
]

TREE = {  # draft tree config (pot-percent sizes), same for every family; tune with Instinct.
    # A richer draft (flop 33/75 + raise 60 + all-in, turn/river 50/100 + raise 60 + all-in) was OOM-killed
    # on the 15 GB box at 7 threads with full ranges; this lighter tree ran at a 2.4 GB peak RSS.
    "flop": {"oop": {"bet": [33], "allin": True}, "ip": {"bet": [33], "allin": True}},
    "turn": {"oop": {"bet": [75], "allin": True}, "ip": {"bet": [75], "allin": True}},
    "river": {"oop": {"bet": [75], "allin": True}, "ip": {"bet": [75], "allin": True}},
}


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 1
    root, out = argv
    if os.path.exists(out):
        print("refusing to overwrite " + out, file=sys.stderr)
        return 1
    sources, spots = {}, []
    for fam in FAMILIES:
        rng = {}
        for side, fn in fam["files"].items():
            rel = fam["dir"] + "/" + fn
            with open(os.path.join(root, *rel.split("/")), "rb") as f:
                raw = f.read()
            sources[rel] = hashlib.sha256(raw).hexdigest()
            rng[side] = raw.decode("ascii").strip()
        for fkey, board in FLOPS:
            spots.append({
                "spot_id": "v1-%s-100bb-%s" % (fam["key"], fkey),
                "positions": fam["positions"], "pot": fam["pot"], "effective_stack": fam["effective_stack"],
                "board": board, "ranges": rng, "bet_sizes": TREE, "accuracy_target": 0.5,
                "notes": "%s. Ranges verbatim from TexasSolver v0.2.0 ranges/6max_range/%s (sha256 in list header)." % (fam["line"], fam["dir"]),
            })
    doc = {
        "schema": "retrosolver.spot_list.v1",
        "list_id": "retrosolver-spotlist-v1-draft",
        "notes": "DRAFT production spot list v1 (config only, not solved). 6 pot families x 12 flops at 100bb. "
                 "Ranges are copied verbatim from the official TexasSolver v0.2.0 release range files listed in range_sources. "
                 "OPEN: (1) the bundled ranges do not state their stack depth; 100bb is assumed and must be confirmed; "
                 "(2) only one stack depth has sourced ranges, so the 2-3 depths the card asks for need a range source; "
                 "(3) TexasSolver's CLI has no rake setting, so these solves are rake-free; standard rake needs wasm-postflop (rake_rate/rake_cap) or a patched CLI.",
        "range_sources": {"release": "TexasSolver-v0.2.0-Windows.zip (github.com/bupticybee/TexasSolver/releases/tag/v0.2.0)",
                          "root": "ranges/6max_range", "files_sha256": sources},
        "solver": {"name": "TexasSolver", "version": "v0.2.0"},
        "defaults": {"thread_num": 8, "max_iteration": 300, "print_interval": 10, "use_isomorphism": 1,
                     "dump_rounds": 1, "allin_threshold": 0.67},
        "spots": spots,
    }
    with open(out, "x", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print("wrote %s: %d spots, %d range source files" % (out, len(spots), len(sources)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
