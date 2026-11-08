"""Paths used by the original analysis scripts.

Defaults follow the repository layout; every path can be overridden with an environment variable:

  CODS_DATA_DIR        data directory                       (default: <repo>/data)
  CODS_CONCURRENT_DIR  concurrent-fault metric CSVs          (default: <repo>/data/concurrent)
  CODS_GROUND_TRUTH    ground-truth log                      (default: <repo>/data/ground_truth_log.csv)
  BARO_DATA_DIR        BARO single-fault dataset, holding fse-ob/ and fse-ss/
                                                             (default: <repo>/external/baro_data)
  CODS_OUT_DIR         where result CSVs are written         (default: <repo>/outputs/original)
"""
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DATA_DIR = os.environ.get("CODS_DATA_DIR", os.path.join(REPO, "data"))
CONCURRENT_DIR = os.environ.get("CODS_CONCURRENT_DIR", os.path.join(DATA_DIR, "concurrent"))
GROUND_TRUTH = os.environ.get("CODS_GROUND_TRUTH", os.path.join(DATA_DIR, "ground_truth_log.csv"))
BARO_DATA_DIR = os.environ.get("BARO_DATA_DIR", os.path.join(REPO, "external", "baro_data"))
OUT_DIR = os.environ.get("CODS_OUT_DIR", os.path.join(REPO, "outputs", "original"))


def concurrent_csv(case_id):
    return os.path.join(CONCURRENT_DIR, f"{case_id}.csv")


def out_path(name):
    os.makedirs(OUT_DIR, exist_ok=True)
    return os.path.join(OUT_DIR, name)
