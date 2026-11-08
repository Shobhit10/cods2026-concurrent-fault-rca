"""
make_merged_format.py -- the merged metric format of the concurrent cases.

The export holds five series per targeted service. Two of them, <svc>_memory_usage_bytes and
<svc>_memory_working_set_bytes, are the same signal (Pearson r = 1.0 in every case), whereas BARO's single-fault cases
carry one memory series per service. The merged format is the export minus every *_memory_usage_bytes column, with
the remaining columns in their exported order; it is the format on which the paper evaluates the separation stage
(README.md, "Two metric formats").

Write the merged format of an exported set (CSV files in OUT/concurrent/, the ground-truth file copied unchanged to
OUT/ground_truth_log.csv, sha256 of both in OUT/DATA_MANIFEST.sha256):

  python analysis/camera_ready/clean/make_merged_format.py data/concurrent_clean/concurrent --out rerun/merged/core

Check a stored merged set against the export instead of writing (same files, same columns in the same order, every
value within a relative difference of 1e-12, ground truth byte-identical); exits with status 1 on any failure:

  python analysis/camera_ready/clean/make_merged_format.py data/concurrent_clean/concurrent --check data/merged_format/core

The ground-truth file defaults to ground_truth_log.csv next to the concurrent folder (--ground-truth FILE overrides).
With the pinned pandas the written CSV files are byte-identical to those in data/merged_format/ (CRLF line endings,
as in the export); the check does not depend on it.
"""
import argparse
import hashlib
import os
import shutil
import sys

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DROP_SUFFIX = "_memory_usage_bytes"
KEEP_TWIN = "_memory_working_set_bytes"
TOL = 1e-12


def merged(path):
    df = pd.read_csv(path)
    drop = [c for c in df.columns if c.endswith(DROP_SUFFIX)]
    for c in drop:
        if c[: -len(DROP_SUFFIX)] + KEEP_TWIN not in df.columns:
            raise SystemExit(f"{path}: {c} has no {KEEP_TWIN} twin")
    return df[[c for c in df.columns if c not in drop]], df, drop


def to_bytes(df):
    return df.to_csv(index=False, lineterminator="\r\n").encode("utf-8")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def write_manifest(out):
    names = ["ground_truth_log.csv"] + [f"concurrent/{f}" for f in sorted(os.listdir(os.path.join(out, "concurrent")))
                                        if f.endswith(".csv")]
    lines = [f"{sha256(os.path.join(out, *n.split('/')))}  {n}" for n in names]
    with open(os.path.join(out, "DATA_MANIFEST.sha256"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return len(lines)


def max_rel_diff(a, b):
    a, b = a.to_numpy(dtype=float), b.to_numpy(dtype=float)
    nan_a, nan_b = np.isnan(a), np.isnan(b)
    if (nan_a != nan_b).any():
        return np.inf
    a, b = np.where(nan_a, 0.0, a), np.where(nan_b, 0.0, b)
    den = np.maximum(np.abs(a), np.abs(b))
    rel = np.divide(np.abs(a - b), den, out=np.zeros_like(den), where=den > 0)
    return float(rel.max()) if rel.size else 0.0


def min_twin_corr(full, drop):
    rs = []
    for c in drop:
        x, y = full[c], full[c[: -len(DROP_SUFFIX)] + KEEP_TWIN]
        if x.std() > 0 and y.std() > 0:
            rs.append(float(np.corrcoef(x, y)[0, 1]))
    return rs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("concurrent", help="folder of exported case CSVs (e.g. data/concurrent_clean/concurrent)")
    ap.add_argument("--ground-truth", help="ground-truth file (default: ../ground_truth_log.csv of the folder)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--out", help="write the merged set to this folder")
    g.add_argument("--check", help="compare with the merged set in this folder; write nothing")
    args = ap.parse_args()

    src = os.path.abspath(args.concurrent)
    gt = args.ground_truth or os.path.join(os.path.dirname(src), "ground_truth_log.csv")
    cases = sorted(f for f in os.listdir(src) if f.endswith(".csv"))
    if not cases:
        raise SystemExit(f"no CSV files in {src}")
    target = args.out or args.check
    tdir = os.path.join(target, "concurrent")

    rs, worst, n_bytes_same, failures, n_drop = [], 0.0, 0, [], 0
    if args.check:
        stored = sorted(f for f in os.listdir(tdir) if f.endswith(".csv"))
        if stored != cases:
            failures.append(f"file sets differ: {len(set(cases) - set(stored))} missing, "
                            f"{len(set(stored) - set(cases))} extra")
    else:
        os.makedirs(tdir, exist_ok=True)

    for name in cases:
        m, full, drop = merged(os.path.join(src, name))
        n_drop += len(drop)
        rs += min_twin_corr(full, drop)
        if args.out:
            with open(os.path.join(tdir, name), "wb") as f:
                f.write(to_bytes(m))
            continue
        path = os.path.join(tdir, name)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            raw = f.read()
        n_bytes_same += raw == to_bytes(m)
        s = pd.read_csv(path)
        if list(s.columns) != list(m.columns) or s.shape != m.shape:
            failures.append(f"{name}: columns or shape differ")
            continue
        d = max_rel_diff(m, s)
        worst = max(worst, d)
        if d > TOL:
            failures.append(f"{name}: max relative difference {d:.3g} > {TOL:g}")

    print(f"{len(cases)} cases in {src}; dropped {n_drop} *{DROP_SUFFIX} columns "
          f"(Pearson r with the {KEEP_TWIN} twin: min {min(rs):.8f} over {len(rs)} non-constant pairs)")
    if args.out:
        shutil.copyfile(gt, os.path.join(target, "ground_truth_log.csv"))
        n = write_manifest(target)
        print(f"wrote {len(cases)} merged CSV files, ground_truth_log.csv and DATA_MANIFEST.sha256 ({n} hashes) "
              f"to {os.path.abspath(target)}")
        return
    with open(gt, "rb") as f1, open(os.path.join(target, "ground_truth_log.csv"), "rb") as f2:
        if f1.read() != f2.read():
            failures.append("ground_truth_log.csv differs")
    print(f"check against {os.path.abspath(target)}: max relative difference {worst:.3g} (tolerance {TOL:g}); "
          f"{n_bytes_same}/{len(cases)} files byte-identical; ground truth "
          f"{'identical' if 'ground_truth_log.csv differs' not in failures else 'DIFFERENT'}")
    if failures:
        print("FAIL\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
