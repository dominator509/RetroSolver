#!/usr/bin/env python3
"""Mechanical checks for the onboarding curriculum (stdlib only).

Run from the repository root:

    python3 retrosolver/content/onboarding/check_onboarding.py

Exit 0 if all A-checks pass, 1 otherwise. Prints one line per check and a
list of every prose line containing a digit (A1 is a review aid, not a fail).
This script reads the content files; it does not modify anything.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VALID_GATES = {"none", "recognize", "solve"}
NUMERIC_ALLOWED = {"cost_to_call", "pot_size"}  # only in tc.l2
SLOT_RE = re.compile(r"\{([a-z_]+)\}")


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def main():
    failures = []
    notes = []
    marks = []

    def check(name, ok, detail=""):
        marks.append((name, ok, detail))
        if not ok:
            failures.append(f"{name}: {detail}")

    cur = load("curriculum.json")
    tpl = load("teach-card-template.json")

    # A2 / A3 schema
    check("A2", cur.get("schema") == "retrosolver.onboarding_curriculum.v1",
          f"schema={cur.get('schema')!r}")
    check("A3", tpl.get("schema") == "retrosolver.teach_card_template.v1",
          f"schema={tpl.get('schema')!r}")

    units = {u["id"]: u for u in cur.get("units", [])}

    # A6 gate enum, A7 visual is bare slot, A10 graded/ungraded discipline
    bad_gate, bad_visual, solve_in_ungraded = [], [], []
    for uid, u in units.items():
        graded = u.get("graded", False)
        for s in u.get("screens", []):
            g = s.get("gate")
            if g not in VALID_GATES:
                bad_gate.append(f"{s.get('id')}={g!r}")
            v = s.get("visual", "")
            if "/" in v or "." in v or not v:
                bad_visual.append(f"{s.get('id')}={v!r}")
            if g == "solve" and not graded:
                solve_in_ungraded.append(s.get("id"))
        for r in ([u["recall"]] if u.get("recall") else []):
            if r.get("gate") not in VALID_GATES:
                bad_gate.append(f"{r.get('id')}={r.get('gate')!r}")
    check("A6", not bad_gate, ", ".join(bad_gate))
    check("A7", not bad_visual, ", ".join(bad_visual))
    check("A10", not solve_in_ungraded, ", ".join(solve_in_ungraded))

    # A8 order references exist
    missing = [x for x in cur.get("order", []) if x not in units]
    extra = [x for x in units if x not in cur.get("order", [])]
    check("A8", not missing and not extra,
          f"missing={missing} unordered={extra}")

    # A9 lesson -> template exists
    bad_ref = []
    for uid, u in units.items():
        tid = u.get("teach_card_template_id")
        if u.get("graded") and not tid:
            bad_ref.append(f"{uid}: no template id")
        if tid and tid not in tpl.get("templates", {}):
            bad_ref.append(f"{uid}: {tid} not defined")
    check("A9", not bad_ref, ", ".join(bad_ref))

    # A4 all slots defined, A5 numeric allow-list
    common = set(tpl.get("common_slots", {}))
    bad_slots, bad_numeric = [], []
    for tid, t in tpl.get("templates", {}).items():
        defined = common | set(t.get("extra_phrase_sets", {}))
        # numeric slots declared by this template are defined slots too
        defined |= set(t.get("numeric_slots_used", []))
        used = set(SLOT_RE.findall(t.get("text", "")))
        undef = sorted(used - defined)
        if undef:
            bad_slots.append(f"{tid}: undefined {undef}")
        numeric = set(t.get("numeric_slots_used", []))
        allowed = set(t.get("numeric_slots_allowed_from_spot_record", []))
        if numeric != allowed:
            bad_numeric.append(f"{tid}: numeric={sorted(numeric)} allowed={sorted(allowed)}")
        for slot in numeric:
            if slot not in NUMERIC_ALLOWED:
                bad_numeric.append(f"{tid}: {slot} not in global numeric allow-list")
            if tid != "tc.l2":
                bad_numeric.append(f"{tid}: numeric slot {slot} outside tc.l2")
        # declared slots_used must cover the slots actually in the text
        if set(t.get("slots_used", [])) != used:
            bad_slots.append(
                f"{tid}: slots_used {sorted(set(t.get('slots_used', [])))} != text {sorted(used)}")
    check("A4", not bad_slots, "; ".join(bad_slots))
    check("A5", not bad_numeric, "; ".join(bad_numeric))

    # A1 review aid: every prose line containing a digit
    digit_lines = []
    for name in ("README.md", "01-basics.md", "02-lessons.md", "editorial-checks.md"):
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                if re.search(r"\d", line):
                    digit_lines.append(f"{name}:{ln}: {line.strip()[:80]}")
    notes.append(f"A1 review aid: {len(digit_lines)} prose line(s) contain a digit")
    notes.extend("  " + d for d in digit_lines)

    # re-derive a per-screen count so the RESULT can cite it
    screen_count = sum(len(u.get("screens", [])) for u in units.values())
    notes.append(f"screens={screen_count} units={len(units)} templates={len(tpl.get('templates', {}))}")

    for name, ok, detail in marks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    for n in notes:
        print(n)

    if failures:
        print(f"\n{len(failures)} check(s) FAILED")
        return 1
    print("\nall A-checks PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
