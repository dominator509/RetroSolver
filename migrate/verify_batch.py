#!/usr/bin/env python3
"""Migration design, step 5: run AT THE DESTINATION on a received staging dir.
Recomputes sha256 of every compressed file and of its decompressed tar stream, compares with MANIFEST.jsonl,
and checks MANIFEST.jsonl against BATCH.json's manifest_sha256. Read-only: never deletes or rewrites.
Exit 0 = every file verified; 1 = any mismatch or missing file (re-send; never delete)."""
import hashlib, json, lzma, os, sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__); return 1
    d = argv[0]
    with open(os.path.join(d, "BATCH.json")) as f:
        batch = json.load(f)
    with open(os.path.join(d, "MANIFEST.jsonl"), "rb") as f:
        mraw = f.read()
    bad = []
    if hashlib.sha256(mraw).hexdigest() != batch["manifest_sha256"]:
        bad.append("MANIFEST.jsonl sha256 != BATCH.json manifest_sha256")
    n = 0
    for line in mraw.decode().splitlines():
        r = json.loads(line); p = os.path.join(d, r["file"]); n += 1
        if not os.path.isfile(p):
            bad.append("missing " + r["file"]); continue
        with open(p, "rb") as f:
            comp = f.read()
        if hashlib.sha256(comp).hexdigest() != r["sha256_compressed"]:
            bad.append("compressed sha256 mismatch " + r["file"]); continue
        if hashlib.sha256(lzma.decompress(comp)).hexdigest() != r["sha256_uncompressed"]:
            bad.append("uncompressed sha256 mismatch " + r["file"])
    print(json.dumps({"batch_id": batch["batch_id"], "files_checked": n, "mismatches": bad,
                      "verified": not bad and n == batch["files"]}))
    return 0 if not bad and n == batch["files"] else 1


if __name__ == "__main__":
    sys.exit(main())
