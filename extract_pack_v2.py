#!/usr/bin/env python3
"""Emit retrosolver.spot_pack.v2 packs. Never overwrites; nothing is filled in.

  python3 extract_pack_v2.py texassolver BATCH_DIR --out PACK.json [--spot ID ...] [--frequencies-only]
  python3 extract_pack_v2.py donksolver DUMP.json RUN_DIR --spot-id ID --out PACK.json [--abstraction ABS.dab]

Exit: 0 all requested spots accepted; 2 pack written with some rejects; 1 nothing written.
"""
import argparse, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retrosolver_pipeline import PIPELINE_VERSION  # noqa: E402
from retrosolver_pipeline.canonical import file_sha256  # noqa: E402
from retrosolver_pipeline.extract import Reject  # noqa: E402
from retrosolver_pipeline.extract_v2 import from_donksolver, from_texassolver  # noqa: E402
from retrosolver_pipeline.pack_v2 import PackError, build_pack  # noqa: E402

GEN = {"name": "retrosolver extract_pack_v2.py", "version": PIPELINE_VERSION}


def _write(path, pack):
    with open(path, "x", encoding="utf-8") as f:
        json.dump(pack, f, indent=1, sort_keys=True); f.write("\n")
    print("[ok] wrote %s spots=%d ev_mode=%s pack_hash=%s" % (path, pack["spot_count"], pack["ev_mode"], pack["pack_hash"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("texassolver"); t.add_argument("batch_dir"); t.add_argument("--out", required=True)
    t.add_argument("--spot", action="append"); t.add_argument("--frequencies-only", action="store_true")
    t.add_argument("--pack-id"); t.add_argument("--allow-synthetic", action="store_true")
    k = sub.add_parser("donksolver"); k.add_argument("dump"); k.add_argument("run_dir")
    k.add_argument("--spot-id", required=True); k.add_argument("--out", required=True)
    k.add_argument("--abstraction"); k.add_argument("--pack-id")
    a = ap.parse_args(argv)
    if os.path.exists(a.out):
        print("[error] refusing to overwrite %s" % a.out, file=sys.stderr); return 1
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        if a.cmd == "texassolver":
            man_path = os.path.join(a.batch_dir, "manifest.json")
            with open(man_path, "r", encoding="utf-8") as f:
                man = json.load(f)
            want = a.spot or [m["spot"]["spot_id"] for m in man["spots"]]
            by_id = {m["spot"]["spot_id"]: m for m in man["spots"]}
            spots, rej = [], []
            for sid in want:
                if sid not in by_id:
                    rej.append((sid, "NOT_IN_MANIFEST")); continue
                try:
                    spots.append(from_texassolver(a.batch_dir, by_id[sid], man["solver"], a.frequencies_only, a.allow_synthetic))
                    print("[accept] %s" % sid)
                except Reject as r:
                    rej.append((sid, r.code)); print("[reject] %s %s: %s" % (sid, r.code, r.detail))
            if not spots:
                print("[error] no valid spots; no pack written", file=sys.stderr); return 1
            pack = build_pack(a.pack_id or "v2-" + man.get("list_id", "batch"), now, GEN, man["solver"], spots,
                              file_sha256(man_path), "frequencies_only" if a.frequencies_only else "full")
            _write(a.out, pack)
            return 2 if rej else 0
        spot = from_donksolver(a.dump, a.run_dir, a.spot_id, a.abstraction)
        print("[accept] %s" % a.spot_id)
        pack = build_pack(a.pack_id or "v2-" + a.spot_id, now, GEN, spot["solver"], [spot], file_sha256(a.dump),
                          "frequencies_only")
        _write(a.out, pack)
        return 0
    except Reject as r:
        print("[reject] %s: %s" % (r.code, r.detail), file=sys.stderr); return 1
    except PackError as e:
        print("[error] pack failed v2 schema check: %s" % e, file=sys.stderr); return 1


if __name__ == "__main__":
    sys.exit(main())
