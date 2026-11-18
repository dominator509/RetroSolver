#!/usr/bin/env python3
"""Summarize a solved batch folder for throughput: per-spot wall time (run_started/finished_at),
solver time_ms / iterations / final exploitability (tmp_log.txt), exit code and bytes on disk.
Every figure is read from files the runner and solver wrote. Usage: python3 soak_report.py BATCH_DIR"""
import datetime
import json
import os
import sys


def ts(p):
    with open(p) as f:
        return datetime.datetime.strptime(f.read().strip(), "%Y-%m-%dT%H:%M:%SZ")


def main(batch):
    with open(os.path.join(batch, "manifest.json")) as f:
        man = json.load(f)
    rows = []
    for ms in man["spots"]:
        sp = ms["spot"]
        d = os.path.join(batch, "spots", sp["spot_id"])
        r = {"spot_id": sp["spot_id"], "street": sp["street"], "target": sp["accuracy_target"]}
        try:
            r["wall_s"] = (ts(os.path.join(d, "run_finished_at.txt")) - ts(os.path.join(d, "run_started_at.txt"))).total_seconds()
        except OSError:
            r["wall_s"] = None
        try:
            with open(os.path.join(d, "solver_exit_code.txt")) as f:
                r["exit"] = f.read().strip()
        except OSError:
            r["exit"] = None
        try:
            with open(os.path.join(d, "tmp_log.txt")) as f:
                last = json.loads([ln for ln in f if ln.strip()][-1])
            r.update(iterations_logged=last["iteration"], final_expl=last["exploitibility"], solve_ms=last["time_ms"])
        except (OSError, IndexError, ValueError):
            r.update(iterations_logged=None, final_expl=None, solve_ms=None)
        r["bytes"] = sum(os.path.getsize(os.path.join(d, x)) for x in os.listdir(d))
        r["output_bytes"] = os.path.getsize(os.path.join(d, "output_result.json")) if os.path.exists(os.path.join(d, "output_result.json")) else 0
        r["converged"] = r["final_expl"] is not None and r["final_expl"] <= r["target"]
        rows.append(r)
    for r in rows:
        print(json.dumps(r, sort_keys=True))
    by = {}
    for r in rows:
        by.setdefault(r["street"], []).append(r)
    for st, rs in sorted(by.items()):
        walls = [r["wall_s"] for r in rs if r["wall_s"] is not None]
        print("# %s: spots=%d exit0=%d converged=%d wall_sum_s=%d wall_mean_s=%.1f wall_max_s=%d spots_per_hour=%.1f bytes_mean=%d" % (
            st, len(rs), sum(r["exit"] == "0" for r in rs), sum(r["converged"] for r in rs), sum(walls),
            sum(walls) / len(walls), max(walls), 3600 * len(walls) / sum(walls), sum(r["bytes"] for r in rs) / len(rs)))
    walls = [r["wall_s"] for r in rows if r["wall_s"] is not None]
    tb = sum(r["bytes"] for r in rows)
    print("# all: spots=%d wall_sum_s=%d spots_per_hour=%.1f total_bytes=%d bytes_per_1k_spots=%d" % (
        len(rows), sum(walls), 3600 * len(walls) / sum(walls), tb, tb * 1000 // len(rows)))


if __name__ == "__main__":
    main(sys.argv[1])
