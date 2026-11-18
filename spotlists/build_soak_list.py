#!/usr/bin/env python3
"""Build the throughput-soak spot list (pipeline follow-on item 2) from spotlist v1.

The soak reuses spot list v1's 6 pot families: the same verbatim TexasSolver-release ranges, pots,
stacks and tree. The flop of each family is kept, and turn and river cards are added so a 30-spot
soak finishes in about an hour on the box. Full-range flop solves take roughly 20+ minutes each
there and are measured separately. Config only; no strategy numbers.
Usage: python3 build_soak_list.py spotlist_v1_draft.json soak_30.json
"""
import copy
import json
import os
import sys

RUNOUTS = {  # flop key in v1 -> turn cards (3) and river runouts (2); cards are inputs only
    "a72r": ["Ks", "7h", "Td"], "k83r": ["Qc", "2s", "8h"], "t62tt": ["Js", "4h", "Tc"],
}
RIVERS = {"a72r": ["Ks,4h", "7h,Jc"], "k83r": ["Qc,5d", "2s,Ah"], "t62tt": ["Js,3c", "4h,9s"]}
FAMILY_FLOP = {"srp-btn-bb": "a72r", "srp-co-bb": "k83r", "srp-sb-bb": "t62tt",
               "3bp-bb-btn": "a72r", "3bp-bb-co": "k83r", "3bp-sb-bb": "t62tt"}


def main(argv):
    src, out = argv
    if os.path.exists(out):
        print("refusing to overwrite " + out)
        return 1
    with open(src) as f:
        v1 = json.load(f)
    by_id = {s["spot_id"]: s for s in v1["spots"]}
    spots = []
    for fam, fk in FAMILY_FLOP.items():
        base = by_id["v1-%s-100bb-%s" % (fam, fk)]
        for card in RUNOUTS[fk]:
            s = copy.deepcopy(base)
            s["spot_id"] = "soak-%s-%s-t%s" % (fam, fk, card.lower())
            s["board"] = base["board"] + "," + card
            s["bet_sizes"] = {k: v for k, v in base["bet_sizes"].items() if k in ("turn", "river")}
            spots.append(s)
        for rv in RIVERS[fk]:
            s = copy.deepcopy(base)
            s["spot_id"] = "soak-%s-%s-r%s" % (fam, fk, rv.replace(",", "").lower())
            s["board"] = base["board"] + "," + rv
            s["bet_sizes"] = {"river": base["bet_sizes"]["river"]}
            spots.append(s)
    doc = copy.deepcopy(v1)
    doc["list_id"] = "retrosolver-soak-30"
    doc["notes"] = "Throughput soak list built from spotlist v1 (see build_soak_list.py). Not curriculum data."
    doc["spots"] = spots
    with open(out, "x") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print("wrote %s: %d spots" % (out, len(spots)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
