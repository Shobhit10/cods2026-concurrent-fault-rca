"""
case_numbers.py -- the concurrent-fault numbers of the paper, computed from the per-case records that
analysis/camera_ready/folds_stats/precompute.py writes (CODS_OUT/raw/cases/conc__*.json). No single-fault data needed.

Works for the core set (data/concurrent_clean) and the larger set (data/larger_set), and for both in the merged format
(data/merged_format/core, data/merged_format/larger_set); point CODS_OUT and CODS_GROUND_TRUTH at the set (see
README.md). Read-only: prints the numbers, and writes a CSV only with --csv FILE.

Prints
  * Table 1 column: AC@1/2/3/5 (cause slots), Both@2/3/5 and Any@5 (cases), overall and per system;
  * ranks: median rank of the better and of the second cause, second cause outside the top 5, CPU and memory cause in
    the top 5, change point detected;
  * cases whose top two entries are two series of one service;
  * the stage at alpha = 0.7, eps = 0.4 (the setting chosen in every fold): cases separated (exact 95% CI), cases in
    which both causes head their own group, Proposition 2.1 violations, separated cases with both causes in the top 5,
    separated cases in which one cause's group is just that service's two memory series (possible only on the series
    as exported; see "Two metric formats" in README.md);
  * the usable case whose first true cause appears latest, with its ranked list down to the second cause (in the core
    set this rule picks the case of Figure 9).

Usage: python analysis/camera_ready/clean/case_numbers.py [--csv FILE]
"""
import os
import sys

sys.dont_write_bytecode = True
FS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "folds_stats")
sys.path.insert(0, os.path.abspath(FS))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import beta  # noqa: E402

import common as C  # noqa: E402
import load_cache as L  # noqa: E402

SEL = (0.7, 0.4)
SUFFIXES = ("cpu_usage_seconds", "memory_usage_bytes", "memory_working_set_bytes", "istio_latency", "istio_requests")


def service_of(entry):
    for s in SUFFIXES:
        if entry.endswith("_" + s):
            return entry[: -len(s) - 1]
    return entry.rsplit("_", 1)[0]


def memory_pair_group(rec):
    """1 if, at alpha = 0.7, eps = 0.4, the group of a cause (the first group holding an entry of that service, as in
    common.score_concurrent_case) holds exactly the service's two memory series."""
    groups = rec["grid"].get("groups_0.7_0.4", {})
    first = {}
    for label, entries in groups.items():
        for svc in (rec["svc_a"], rec["svc_b"]):
            if svc not in first and any(e.startswith(f"{svc}_") for e in entries):
                first[svc] = label
    return int(any(sorted(groups[lab]) == [f"{s}_memory_usage_bytes", f"{s}_memory_working_set_bytes"]
                   for s, lab in first.items()))


def exact_ci(k, n, level=0.95):
    a = (1 - level) / 2
    lo = 0.0 if k == 0 else beta.ppf(a, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - a, k + 1, n - k)
    return lo, hi


def main():
    recs, conc, grid = L.concurrent_tables()
    if conc.empty:
        raise SystemExit(f"no usable per-case records in {os.path.join(C.RAW, 'cases')}")
    by_id = {r["case_id"]: r for r in recs}
    sel = grid[(grid.alpha == SEL[0]) & (grid.eps == SEL[1])].set_index("case_id")
    conc = conc.set_index("case_id").join(sel[["separated", "grouped_ac1"]]).reset_index()
    conc["same_service_top2"] = [int(len({service_of(e) for e in by_id[c]["ranked"][:2]}) == 1) for c in conc.case_id]
    conc["detected"] = [int(bool(by_id[c].get("detected"))) for c in conc.case_id]
    conc["heads_both"] = (conc.grouped_ac1 == 1.0).astype(int)
    conc["violation"] = ((conc.separated == 1) & (conc.both_in_input == 0)).astype(int)
    conc["memory_pair_split"] = [int(s == 1 and memory_pair_group(by_id[c])) for c, s in zip(conc.case_id, conc.separated)]
    better = conc[["rank_cpu", "rank_mem"]].min(axis=1)
    second = conc[["rank_cpu", "rank_mem"]].max(axis=1)
    conc["rank_better"], conc["rank_second"] = better, second

    print(f"records: {len(recs)} in {os.path.join(C.RAW, 'cases')}; usable: {len(conc)}; "
          f"excluded: {[r['case_id'] for r in recs if r.get('status') != 'ok']}")
    rows = []
    for ns, name in (("all", "overall"), ("boutique", "Online Boutique"), ("sock-shop", "Sock Shop")):
        sub = conc if ns == "all" else conc[conc.namespace == ns]
        n = len(sub)
        if n == 0:
            continue
        r = {"scope": name, "cases": n}
        for m in ("ac1", "ac2", "ac3", "ac5"):
            r[m.upper().replace("AC", "AC@")] = sub[m].sum() * 2 / (2 * n)
        for m, lab in (("both2", "Both@2"), ("both3", "Both@3"), ("both5", "Both@5"), ("any5", "Any@5")):
            r[lab] = sub[m].mean()
        b, s = sub.rank_better, sub.rank_second
        r.update({"median rank, better cause": float(np.median(b)), "median rank, second cause": float(np.median(s)),
                  "second cause outside top 5": (s > 5).mean(), "CPU cause in top 5": (sub.rank_cpu <= 5).mean(),
                  "memory cause in top 5": (sub.rank_mem <= 5).mean(), "change point detected": sub.detected.mean(),
                  "one service fills the top two": int(sub.same_service_top2.sum()),
                  "separated (alpha 0.7, eps 0.4)": int(sub.separated.sum()),
                  "both causes head their groups": int(sub.heads_both.sum()),
                  "Prop. 2.1 violations": int(sub.violation.sum()),
                  "separated with both in top 5": int(((sub.separated == 1) & (sub.both5 == 1)).sum())})
        rows.append(r)
    t = pd.DataFrame(rows).set_index("scope").T
    with pd.option_context("display.width", 200, "display.max_rows", 100):
        print(t.to_string(float_format=lambda v: f"{v:.3f}"))

    n, k = len(conc), int(conc.separated.sum())
    lo, hi = exact_ci(k, n)
    h = int(conc.heads_both.sum())
    print(f"\nseparated: {k}/{n} = {k / n:.3f} (exact 95% CI {lo:.3f}-{hi:.3f}); both causes head their groups: "
          f"{h}/{n} = {h / n:.3f}; Prop. 2.1 violations: {int(conc.violation.sum())}; separated with both causes in "
          f"the top 5: {int(((conc.separated == 1) & (conc.both5 == 1)).sum())}/{k}")
    print(f"separated cases in which one cause's group is just its two memory series: "
          f"{int(conc.memory_pair_split.sum())}/{k}")
    b2 = int(conc.both2.sum())
    lo2, hi2 = exact_ci(b2, n)
    print(f"Both@2: {b2}/{n} = {b2 / n:.3f} (exact 95% CI {lo2:.3f}-{hi2:.3f}); one service fills the top two: "
          f"{int(conc.same_service_top2.sum())}/{n}")

    fig = conc.assign(first=better).sort_values(["first", "rank_second"], ascending=False, kind="stable").iloc[0]
    r = by_id[fig.case_id]
    print(f"\ncase whose first true cause appears latest (the rule that picked the case of Figure 9 in the core set): "
          f"{fig.case_id} ({r['svc_a']} {r['fault_a']} at rank "
          f"{r['rank_a']}, {r['svc_b']} {r['fault_b']} at rank {r['rank_b']}); top {int(fig.rank_second)}:")
    for i, e in enumerate(r["ranked"][: int(fig.rank_second)], 1):
        tag = "true cause" if service_of(e) in (r["svc_a"], r["svc_b"]) else ""
        print(f"  {i:2d}  {e}  {tag}")

    if "--csv" in sys.argv:
        path = sys.argv[sys.argv.index("--csv") + 1]
        cols = ["case_id", "namespace", "pair", "rep", "svc_cpu", "svc_mem", "ac1", "ac2", "ac3", "ac5", "both2", "both3",
                "both5", "any5", "rank_cpu", "rank_mem", "n_ranked", "detected", "same_service_top2", "separated",
                "grouped_ac1", "heads_both", "both_in_input", "violation", "memory_pair_split"]
        conc[cols].to_csv(path, index=False, lineterminator="\n")
        print(f"\nper-case table written to {path}")


if __name__ == "__main__":
    main()
