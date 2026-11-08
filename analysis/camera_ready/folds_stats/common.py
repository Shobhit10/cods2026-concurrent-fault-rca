"""
common.py -- shared helpers for the camera-ready (post hoc) folds/statistics analysis.

* Reads code from analysis/original/ and data from data/ (or the BARO dataset); never writes there.
* The clustering stage is NOT re-implemented: `cluster_candidates_v2`, `compute_deviation_scores`,
  `GRAPHS` are imported from the released run_rq2_v2.py
  (analysis/original/, md5 checked at import), and the rank-position first design from run_rq2.py.
* All writes go to OUT via crash-safe tmp + fsync + os.replace.
"""
import sys

sys.dont_write_bytecode = True  # never drop __pycache__ next to read-only sources

import hashlib
import importlib.util
import json
import os

# Paths (repository layout by default; override with environment variables).
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
DATA = os.environ.get("CODS_DATA_DIR", os.path.join(REPO, "data"))
CONC_DIR = os.environ.get("CODS_CONCURRENT_DIR", os.path.join(DATA, "concurrent"))
GT_PATH = os.environ.get("CODS_GROUND_TRUTH", os.path.join(DATA, "ground_truth_log.csv"))
PUB = os.environ.get("CODS_PUBLISHED_RESULTS", os.path.join(DATA, "results", "original"))
BARO_DATA = os.environ.get("BARO_DATA_DIR", os.path.join(REPO, "external", "baro_data"))
OUT = os.environ.get("CODS_OUT", os.path.join(DATA, "results", "camera_ready", "folds_stats"))
RAW = os.path.join(OUT, "raw")
ORIG = os.path.join(REPO, "analysis", "original")  # the released analysis scripts (imported, not copied)

sys.path.insert(0, ORIG)
if os.environ.get("BARO_SRC"):  # optional: a BARO source checkout instead of the pip-installed fse-baro
    sys.path.insert(0, os.environ["BARO_SRC"])

# md5 of the released scripts in analysis/original/. The versions that produced the paper's numbers differ
# from these only in the path-configuration lines (input and output paths); their md5 were
# run_rq2_v2.py ccc210808ffcb3d85ecf4be0fcab4d75, run_crossval_parallel.py 36f6fa50f20711add0fdc3083eb7dc7d,
# run_rq1.py 960b9858dce770b4f76998ae00dbb2e2.
EXPECTED_MD5 = {
    "run_rq2_v2.py": "9048be757b90424cb8547912eb7ea9ec",
    "run_crossval_parallel.py": "4ec6766aa9ceedab5da6d28f49677230",
    "run_rq1.py": "fc4e89e4d5d6959ab9d5814faab4b873",
}

ALPHAS = [0.3, 0.5, 0.7]          # same grid as run_crossval_parallel.py
EPSS = [0.1, 0.15, 0.2, 0.3, 0.4]
GRID = [(a, e) for a in ALPHAS for e in EPSS]  # same iteration order (alpha outer, eps inner)


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(name):
    path = os.path.join(ORIG, name)
    spec = importlib.util.spec_from_file_location(name[:-3] + "_orig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_rq2_v2():
    for name, exp in EXPECTED_MD5.items():
        got = md5(os.path.join(ORIG, name))
        if got != exp:
            raise RuntimeError(f"md5 mismatch for {name}: got={got} expected={exp}")
    return _load("run_rq2_v2.py")


def load_rq2_v1():
    return _load("run_rq2.py")


def atomic_write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_json(path, obj):
    atomic_write_text(path, json.dumps(obj, indent=1, sort_keys=False, default=_json_default))


def atomic_write_df(path, df):
    atomic_write_text(path, df.to_csv(index=False, lineterminator="\n"))


def _json_default(o):
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def parse_ground_truth(path=None):
    """Same parsing rule as the original scripts (8-field lines), plus pair id and fault types."""
    path = path or GT_PATH
    cases = {}
    with open(path) as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) == 8:
                case_id, namespace, svc_a, fault_a, svc_b, fault_b, stagger, start_time = parts
                pair = case_id.rsplit("_rep", 1)[0]  # e.g. boutique_cpu-mem_pair1
                cases[case_id] = {
                    "namespace": namespace, "svc_a": svc_a, "fault_a": fault_a,
                    "svc_b": svc_b, "fault_b": fault_b, "pair": pair,
                    "rep": int(case_id.rsplit("_rep", 1)[1]),
                }
    return cases


def find_single_fault_cases():
    """Same discovery rule as run_crossval_parallel.find_single_fault_cases, but SORTED for determinism."""
    import glob
    out = []
    for base, ns in (("fse-ob", "boutique"), ("fse-ss", "sock-shop")):
        base_dir = os.path.join(BARO_DATA, base)
        for combo_dir in sorted(glob.glob(f"{base_dir}/*")):
            combo_name = os.path.basename(combo_dir)
            parts = combo_name.rsplit("_", 1)
            if len(parts) != 2:
                continue
            true_service, fault_type = parts
            for rep_dir in sorted(glob.glob(f"{combo_dir}/*")):
                data_path = os.path.join(rep_dir, "simple_data.csv")
                if os.path.exists(data_path):
                    out.append({
                        "sf_id": f"{ns}/{combo_name}/{os.path.basename(rep_dir)}",
                        "path": data_path, "true_service": true_service, "fault_type": fault_type,
                        "namespace": ns, "combo": f"{ns}/{combo_name}",
                    })
    return out


def hits_at_k(ranked, true_services, k):
    top = ranked[:k]
    return sum(1 for s in true_services if any(e.startswith(f"{s}_") for e in top))


def first_rank(ranked, svc):
    for i, e in enumerate(ranked):
        if e.startswith(svc + "_"):
            return i + 1
    return None


def score_concurrent_case(groups, true_services):
    """Verbatim logic of run_crossval_parallel.score_concurrent for ONE case."""
    svc_to_group = {}
    for label, entries in groups.items():
        for svc in true_services:
            if any(e.startswith(f"{svc}_") for e in entries) and svc not in svc_to_group:
                svc_to_group[svc] = label
    real_labels = {s: l for s, l in svc_to_group.items() if not str(l).startswith("noise_")}
    separated = len(real_labels) == 2 and len(set(real_labels.values())) == 2
    hits = 0
    for svc, label in svc_to_group.items():
        if str(label).startswith("noise_"):
            continue
        if groups[label] and groups[label][0].startswith(f"{svc}_"):
            hits += 1
    return {"separated": bool(separated), "grouped_ac1": hits / 2}


def score_single_case(groups, true_service):
    """Verbatim logic of run_crossval_parallel.score_single_fault for ONE case."""
    real_groups = [g for label, g in groups.items() if not str(label).startswith("noise_")]
    single_group = len(real_groups) <= 1
    hit = 0
    for label, entries in groups.items():
        if str(label).startswith("noise_"):
            continue
        if entries and entries[0].startswith(f"{true_service}_"):
            hit = 1
            break
    return {"single_group": bool(single_group), "hit": hit}
