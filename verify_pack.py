#!/usr/bin/env python3
"""Verify a spot pack: schema, required fields on every spot, and pack_hash.
Usage: python3 verify_pack.py PACK.json [--allow-synthetic]   (exit 0 = valid, 1 = invalid)
Packs flagged as synthetic test data are refused unless --allow-synthetic (tests only).
This is the pipeline's own self-check; an independent validator does the second-model check."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retrosolver_pipeline.pack import PackError, compute_pack_hash, validate_pack  # noqa: E402
from retrosolver_pipeline import pack_v2  # noqa: E402


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    allow_synthetic = "--allow-synthetic" in argv
    argv = [a for a in argv if a != "--allow-synthetic"]
    if len(argv) != 1:
        print(__doc__)
        return 1
    with open(argv[0], "r", encoding="utf-8") as f:
        pack = json.load(f)
    if pack.get("schema") == pack_v2.SCHEMA_V2:   # v2 packs use their own checks
        try:
            pack_v2.validate_pack(pack, allow_synthetic=allow_synthetic)
        except pack_v2.PackError as e:
            print("[invalid] %s" % e)
            return 1
        print("[valid] %s schema=v2 ev_mode=%s spots=%d pack_hash=%s" % (pack["pack_id"], pack["ev_mode"], pack["spot_count"], pack_v2.compute_pack_hash(pack)))
        return 0
    try:
        validate_pack(pack, allow_synthetic=allow_synthetic)
    except PackError as e:
        print("[invalid] %s" % e)
        return 1
    print("[valid] %s spots=%d pack_hash=%s" % (pack["pack_id"], pack["spot_count"], compute_pack_hash(pack)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
