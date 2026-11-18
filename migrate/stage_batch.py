#!/usr/bin/env python3
"""Migration design, steps 2-3 (stage + manifest). Stdlib only.

For each solved spot dir in a batch: build a deterministic tar (sorted names, mtime/uid/gid zeroed),
compress it with xz (zstd is not installed on the build host; the design says xz then), write
<spot_id>.tar.xz into a NEW staging dir, and append one line to MANIFEST.jsonl:
  spot_id, file, bytes_files (sum of the spot's file sizes), bytes_tar, bytes_compressed, ratio,
  sha256_compressed, sha256_uncompressed (of the tar stream), solver, solver_commit, staged_at_utc.
Then BATCH.json: totals, overall ratio, sha256 of MANIFEST.jsonl.
Never overwrites (refuses an existing staging dir) and never deletes anything: deletion of host copies is
a separate, later step allowed only after the destination hash check passes and the manifest is committed.
Transfer (step 4) and destination verify (step 5, verify_batch.py) are separate.
"""
import argparse, datetime, hashlib, io, json, lzma, os, sys, tarfile


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def spot_tar(spot_dir, arc_root):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for name in sorted(os.listdir(spot_dir)):
            p = os.path.join(spot_dir, name)
            if not os.path.isfile(p):
                continue
            ti = tarfile.TarInfo(arc_root + "/" + name)
            ti.size = os.path.getsize(p); ti.mtime = 0; ti.mode = 0o644
            ti.uid = ti.gid = 0; ti.uname = ti.gname = ""
            with open(p, "rb") as f:
                tf.addfile(ti, f)
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spots_dir")
    ap.add_argument("--batch-id", required=True)
    ap.add_argument("--out", required=True, help="new staging dir")
    ap.add_argument("--solver", default="")
    ap.add_argument("--solver-commit", default="")
    ap.add_argument("--preset", type=int, default=9)
    a = ap.parse_args(argv)
    if os.path.exists(a.out):
        print("refusing to overwrite " + a.out, file=sys.stderr); return 1
    os.makedirs(a.out)
    man_path = os.path.join(a.out, "MANIFEST.jsonl")
    tot = {"files": 0, "bytes_files": 0, "bytes_tar": 0, "bytes_compressed": 0}
    with open(man_path, "x") as man:
        for sid in sorted(os.listdir(a.spots_dir)):
            sd = os.path.join(a.spots_dir, sid)
            if not os.path.isdir(sd):
                continue
            raw = spot_tar(sd, sid)
            comp = lzma.compress(raw, preset=a.preset | lzma.PRESET_EXTREME)
            fn = sid + ".tar.xz"
            with open(os.path.join(a.out, fn), "xb") as f:
                f.write(comp)
            bf = sum(os.path.getsize(os.path.join(sd, n)) for n in os.listdir(sd) if os.path.isfile(os.path.join(sd, n)))
            rec = {"spot_id": sid, "file": fn, "bytes_files": bf, "bytes_tar": len(raw), "bytes_compressed": len(comp),
                   "ratio_files_over_compressed": round(bf / len(comp), 3),
                   "sha256_compressed": hashlib.sha256(comp).hexdigest(),
                   "sha256_uncompressed": hashlib.sha256(raw).hexdigest(),
                   "solver": a.solver, "solver_commit": a.solver_commit, "staged_at_utc": utc()}
            man.write(json.dumps(rec, sort_keys=True) + "\n")
            tot["files"] += 1; tot["bytes_files"] += bf; tot["bytes_tar"] += len(raw); tot["bytes_compressed"] += len(comp)
    with open(man_path, "rb") as f:
        msha = hashlib.sha256(f.read()).hexdigest()
    batch = dict(tot, batch_id=a.batch_id, compression="xz preset %d extreme (python lzma)" % a.preset,
                 ratio_files_over_compressed=round(tot["bytes_files"] / tot["bytes_compressed"], 3) if tot["bytes_compressed"] else None,
                 mean_bytes_files_per_spot=round(tot["bytes_files"] / tot["files"], 1) if tot["files"] else None,
                 mean_bytes_compressed_per_spot=round(tot["bytes_compressed"] / tot["files"], 1) if tot["files"] else None,
                 manifest_sha256=msha, destination=None, destination_verified=False, created_at_utc=utc())
    with open(os.path.join(a.out, "BATCH.json"), "x") as f:
        json.dump(batch, f, indent=1, sort_keys=True); f.write("\n")
    print(json.dumps(batch, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
