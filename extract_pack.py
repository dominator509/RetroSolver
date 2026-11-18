#!/usr/bin/env python3
"""Extractor: a run batch folder (made by batch_generate.py, solved by run_all.*)
-> spot-pack JSON with a pack-level hash, plus a rejection log.

Usage:
  python3 extract_pack.py BATCH_DIR --out PACK.json [--pack-id ID] [--rejections REJECTS.jsonl] [--frequencies-only]

* A spot is accepted only if every required field came out of real solver files.
  Missing fields, missing EVs, failed or non-converged solves are REJECTED and logged
  (one JSON line each); nothing is estimated or filled in.
* Output files must not exist (opened with 'x'; never overwritten).
Exit codes: 0 all spots accepted; 2 pack written but some spots rejected;
            1 no pack written (no valid spots or bad input).
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retrosolver_pipeline import BATCH_MANIFEST_SCHEMA, PIPELINE_VERSION  # noqa: E402
from retrosolver_pipeline.canonical import file_sha256  # noqa: E402
from retrosolver_pipeline.extract import Reject, extract_spot  # noqa: E402
from retrosolver_pipeline.pack import PackError, build_pack  # noqa: E402


def run(batch_dir, out_path, rej_path, pack_id=None, now=None, allow_synthetic=False, frequencies_only=False):
    man_path = os.path.join(batch_dir, "manifest.json")
    if not os.path.isfile(man_path):
        print("[error] no manifest.json in %s" % batch_dir, file=sys.stderr)
        return 1
    with open(man_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    if manifest.get("schema") != BATCH_MANIFEST_SCHEMA:
        print("[error] manifest schema is not %s" % BATCH_MANIFEST_SCHEMA, file=sys.stderr)
        return 1
    for p in (out_path, rej_path):
        if os.path.exists(p):
            print("[error] refusing to overwrite existing file: %s" % p, file=sys.stderr)
            return 1
    solver = manifest["solver"]
    accepted, rejected = [], []
    for ms in manifest["spots"]:
        sid = ms["spot"]["spot_id"]
        try:
            accepted.append(extract_spot(batch_dir, ms, solver, allow_synthetic, frequencies_only))
            print("[accept] %s" % sid)
        except Reject as r:
            rejected.append({"spot_id": sid, "code": r.code, "detail": r.detail})
            print("[reject] %s %s: %s" % (sid, r.code, r.detail))
    now = now or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(rej_path, "x", encoding="utf-8") as f:
        for r in rejected:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    print("[summary] %d accepted, %d rejected (log: %s)" % (len(accepted), len(rejected), rej_path))
    if not accepted:
        print("[error] no valid spots; no pack written (nothing is ever filled in)", file=sys.stderr)
        return 1
    try:
        pack = build_pack(pack_id or manifest.get("list_id") or "pack-" + now.replace(":", ""),
                          now, {"name": "retrosolver extract_pack.py", "version": PIPELINE_VERSION},
                          solver, accepted, file_sha256(man_path),
                          ev_mode="frequencies_only" if frequencies_only else "full")
    except PackError as e:
        print("[error] pack failed schema check: %s" % e, file=sys.stderr)
        return 1
    with open(out_path, "x", encoding="utf-8") as f:
        json.dump(pack, f, indent=1, sort_keys=True)
        f.write("\n")
    print("[ok] wrote %s  spots=%d  pack_hash=%s" % (out_path, len(accepted), pack["pack_hash"]))
    return 2 if rejected else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rejections", help="default: <out>.rejections.jsonl")
    ap.add_argument("--pack-id")
    ap.add_argument("--allow-synthetic", action="store_true",
                    help="TESTS ONLY: accept outputs marked _SYNTHETIC_TEST_FIXTURE (pack is flagged and verify_pack refuses it)")
    ap.add_argument("--frequencies-only", action="store_true",
                    help="accept TexasSolver spots without EVs (evs=null, pack ev_mode=frequencies_only). "
                         "All other gates unchanged; EVs are never filled in.")
    a = ap.parse_args(argv)
    return run(a.batch_dir, a.out, a.rejections or a.out + ".rejections.jsonl", a.pack_id,
               allow_synthetic=a.allow_synthetic, frequencies_only=a.frequencies_only)


if __name__ == "__main__":
    sys.exit(main())
