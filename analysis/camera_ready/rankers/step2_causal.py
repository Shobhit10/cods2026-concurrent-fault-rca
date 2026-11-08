"""
step2_causal.py -- causal rankers on the SAME change point and the SAME candidate metrics as the paper.

  python step2_causal.py circa   <concurrent|single>     (rcaeval-env, py3.10, RCAEval 1.6.0)
  python step2_causal.py rcd     <concurrent|single>     (RCAEval/env-rcd, py3.8, RCD-patched causal-learn)

Inputs : outputs/precompute_<kind>.json from step1 (cp = bocpd change point, candidates = paper candidates).
Outputs: outputs/cache/<method>/<case>[__seedS].json  (one file per run, resume-safe)
         outputs/causal_<method>_<kind>.json            (combined, atomic)

CIRCA ("circa")  = RCAEval's circa(): PC (causal-learn, Fisher-z, alpha=0.05) over the candidate metrics,
                   then regression-based hypothesis testing (RHT) of each metric given its PC parents.
   Adaptations (documented in RESULTS_RANKERS.md):
   (a) columns are renamed "<service>_<metric-without-underscores>" because RCAEval's rht() parses
       name.split("_")[0:2]; data_v2 names such as cartservice_memory_usage_bytes and
       cartservice_memory_working_set_bytes would otherwise collide on ("cartservice","memory").
   (b) train window = all rows before the bocpd change point, test window = all rows from it to the end,
       at the native sampling interval -- i.e. exactly the paper's windows. RCAEval's default
       (1 s interval, 111-point train, 10-point test placed at inject_time+291..300 s) lies beyond the end
       of our 290 s concurrent windows; it is run as the sensitivity variant "circa_rcaeval".
   (c) metrics with no PC edge are kept as isolated nodes (scored by their marginal RHT z-score);
       RCAEval's rht() silently drops them. Variant "circa_rcaeval" keeps RCAEval's behaviour.
   (d) exact-collinear twins collapsed before PC (see collapse_twins).
   (e) NaN cells filled as RCAEval's @rca wrapper does (bfill, ffill, 0)   [single-fault files only].
   (f) trailing rows with NaN timestamps dropped (all after the change point) [single-fault files only].
RCD ("rcd")      = RCAEval's rcd() unchanged (gamma=5, bins=5, localized=True, chi-square CI tests);
                   split at time[cp]; stochastic -> several seeds (concurrent 0-9; single RCD_SINGLE_SEEDS, default 0,1,2).
Env: WORKERS, LIMIT (smoke test, no combined file), SUBSET_REPS (single-fault stratified subset, e.g. "1,2").

=== Learned rankers (CausalRCA and RUN) ===
  python step2_causal.py run        <concurrent|single>   (environment: RCAEval 1.6.0 + CPU torch)
  python step2_causal.py run_native <concurrent|single>
  python step2_causal.py causalrca  <concurrent|single>
RUN ("run")        = RCAEval's run() unchanged (DLinear neural Granger discovery, contrastive pre-training,
                     1 epoch, lr 1e-3, Adam, window 32, batch 128, PageRank). Input = the case window and the
                     candidate metrics, linearly interpolated onto a 1 s grid (RUN's reference model needs
                     >= 214 samples; our cases have 60 at 5 s). "run_native" = same on the 5 s series.
CausalRCA ("causalrca") = RCAEval's causalrca() unchanged (DAG-GNN VAE, 500 epochs per augmented-Lagrangian
                     step, threshold 0.3, PageRank) on the case window and candidate metrics, native sampling.
Both are stochastic -> LEARNED_SEEDS (default 0,1,2,3,4); random/numpy/torch seeded per run; torch 1 thread.
Each run executes in its own subprocess with a wall-clock time box TIMEBOX_S (default 600 s); a run that
raises or times out is recorded with ok=False and an empty list.
Execution-only change: RUN's DataLoaders use num_workers=RUN_NUM_WORKERS (default 0; RCAEval hard-codes 8).
"""

import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import timedelta

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

import common as C

RCD_SEEDS = {"concurrent": list(range(10)),
             "single": [int(s) for s in os.environ.get("RCD_SINGLE_SEEDS", "0,1,2").split(",")]}
LEARNED = ("run", "run_native", "causalrca")
LEARNED_SEEDS = [int(s) for s in os.environ.get("LEARNED_SEEDS", "0,1,2,3,4").split(",")]
TIMEBOX_S = float(os.environ.get("TIMEBOX_S", "600"))


def rename_map(cands):
    ren = {}
    for c in cands:
        s = C.svc_fixed(c)
        m = c[len(s) + 1:].replace("_", "")
        ren[c] = "%s_%s" % (s, m)
    assert len(set(ren.values())) == len(ren), "rename collision"
    return ren


def collapse_twins(data, cands, thr=0.9999):
    """Adaptation (d): Fisher-z PC needs an invertible correlation matrix. In data_v2 every
    <svc>_memory_working_set_bytes is an exact affine copy of <svc>_memory_usage_bytes (|r|=1), so PC
    raises 'correlation matrix is singular' and RCAEval's @rca wrapper silently returns the INPUT COLUMN
    ORDER as the ranking. We keep the first column of every |r|>=thr group as its representative (the same
    de-duplication RCAEval's own mmcirca applies at 0.99), plus a rank-based fallback; each dropped twin
    is re-inserted directly after its representative with the representative's score."""
    X = data[cands].astype(float)
    corr = X.corr().abs().fillna(0).to_numpy()
    idx = {c: i for i, c in enumerate(cands)}
    kept, twin = [], {}
    for c in cands:
        rep = next((k for k in kept if corr[idx[c], idx[k]] >= thr), None)
        if rep is None:
            kept.append(c)
        else:
            twin[c] = rep

    def rank_of(cols):
        Z = X[cols].to_numpy()
        Z = (Z - Z.mean(0)) / np.where(Z.std(0) > 0, Z.std(0), 1.0)
        return np.linalg.matrix_rank(Z)

    while rank_of(kept) < len(kept):
        full = rank_of(kept)
        for c in reversed(kept):
            rest = [k for k in kept if k != c]
            if rank_of(rest) == full:
                twin[c] = max(rest, key=lambda k: corr[idx[c], idx[k]])
                kept = rest
                break
    return kept, twin


def circa_rank(data, cp, cands_all, variant):
    import networkx as nx
    from RCAEval.graph_construction.pc import pc_default
    from RCAEval.io.time_series import preprocess
    from RCAEval.classes.data import CaseData, MemoryDataLoader
    from RCAEval.classes.graph import MemoryGraph, Node
    from RCAEval.graph_heads.rht import RHTScorer

    cands, twin = collapse_twins(data, cands_all)
    ren = rename_map(cands)
    inv = {v: k for k, v in ren.items()}
    df = data[["time"] + cands].rename(columns=ren)
    time_col = df["time"]
    inject_time = float(time_col.iloc[cp])

    # == circa(): preprocess + PC (verbatim) ==
    d = preprocess(data=df, dataset="cods", dk_select_useful=False)
    d["time"] = time_col
    pc_input = d.drop(columns=["time"])
    adj = pc_default(pc_input, dataset="ob")

    # == rht(): graph conversion (verbatim) ==
    # The graph conversion, data-loader construction and CaseData set-up below (to the RHTScorer call) follow
    # RCAEval's circa()/rht() code; RCAEval: MIT licence, Copyright (c) 2024 Luan Pham. See THIRD_PARTY_NOTICES.md.
    node_names = d.columns.to_list()
    nodes = [Node(name.split("_")[0], name.split("_")[1]) for name in node_names if name != "time"]
    graph = nx.DiGraph()
    n_edges = 0
    node_num = len(adj)
    for a in range(node_num):
        for b in range(node_num):
            if adj[a, b] == adj[b, a] == 0:
                pass
            elif adj[a, b] == adj[b, a] == -1:
                graph.add_edge(nodes[b], nodes[a]); n_edges += 1
            elif adj[a, b] == 1 and adj[b, a] == -1:
                graph.add_edge(nodes[b], nodes[a]); n_edges += 1
            elif adj[a, b] == -1 and adj[b, a] == 1:
                graph.add_edge(nodes[a], nodes[b]); n_edges += 1
            else:
                raise ValueError("Unexpected value: %s, %s" % (adj[a, b], adj[b, a]))
    graph = graph.reverse()
    n_isolated = len([n for n in nodes if n not in graph])
    if variant == "circa":
        graph.add_nodes_from(nodes)          # adaptation (c)
    mem_graph = MemoryGraph(graph)

    timestamps = d["time"]
    services = list(set([c.split("_")[0] for c in d.columns if c != "time"]))
    metrics = list(set([c.split("_")[1] for c in d.columns if c != "time"]))
    out_data = {s: {} for s in services}
    for s in services:
        for m in metrics:
            if "%s_%s" % (s, m) in d.columns:
                out_data[s][m] = list(zip(timestamps, d["%s_%s" % (s, m)]))
    loader = MemoryDataLoader(out_data)

    if variant == "circa":                    # adaptation (b): the paper's windows
        dt = float(np.median(np.diff(time_col.to_numpy())))
        case = CaseData(data_loader=loader, sli=nodes[0], detect_time=inject_time, interval=timedelta(seconds=dt))
        n_before, n_after = cp, len(d) - cp
        case._train_window = n_before
        case._test_window = n_after
        case._lookup_window = inject_time - float(time_col.iloc[0])
        current = float(time_col.iloc[-1])
    else:                                     # RCAEval default, verbatim
        case = CaseData(data_loader=loader, sli=nodes[0], detect_time=inject_time, interval=timedelta(seconds=1))
        current = inject_time + 300
    scores = RHTScorer().score(graph=mem_graph, data=case, current=current, scores=None)
    scores = sorted(scores.items(), key=lambda item: item[1].key, reverse=True)
    ranked_reps = [inv["%s_%s" % (n.entity, n.metric)] for n, _ in scores]
    sc = {inv["%s_%s" % (n.entity, n.metric)]: float(s.score) for n, s in scores}
    ranked = []
    for r in ranked_reps:
        ranked.append(r)
        for c in cands_all:
            if twin.get(c) == r:
                ranked.append(c)
                sc[c] = sc[r]
    return {"ranks": ranked, "scores": sc, "n_pc_edges_directed_pairs": n_edges, "n_isolated": n_isolated,
            "n_nodes": len(nodes), "twins": twin, "n_scored_reps": len(ranked_reps)}


def rcd_rank(data, cp, cands, seed):
    from RCAEval.e2e.rcd import rcd
    df = data[["time"] + cands]
    inject_time = float(df["time"].iloc[cp])
    res = rcd(df, inject_time=inject_time, dataset="cods", gamma=5, localized=True, bins=5, seed=seed)
    return {"ranks": list(res["ranks"])}


# ------------------------------------------------------------------ learned rankers
def seed_all(seed):
    import random
    import torch
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)


def to_1s_grid(df):
    """Linear interpolation of every column onto a 1 s grid spanning the same window (identity for 1 s data)."""
    t = df["time"].to_numpy(dtype=float)
    grid = np.arange(t[0], t[-1] + 1e-9, 1.0)
    out = {"time": grid}
    for c in df.columns:
        if c != "time":
            out[c] = np.interp(grid, t, df[c].to_numpy(dtype=float))
    return pd.DataFrame(out, columns=list(df.columns))


def run_rank(data, cp, cands, seed, tag, variant):
    """RCAEval's run() verbatim; it reads its input from args.root_path/args.data_path, so the case window
    (time + candidate metrics) is written to a scratch CSV first."""
    import argparse
    import contextlib
    import io
    import networkx as nx
    from torch.utils.data import DataLoader
    import importlib
    R = importlib.import_module("RCAEval.e2e.run")  # the package re-exports a function named run; get the module

    def _dl(*a, **k):           # execution-only: RCAEval hard-codes num_workers=8
        k["num_workers"] = int(os.environ.get("RUN_NUM_WORKERS", "0"))
        return DataLoader(*a, **k)

    R.DataLoader = _dl
    df = data[["time"] + cands].copy()
    inject_time = float(df["time"].iloc[cp])
    if variant == "run":
        df = to_1s_grid(df)
    d = os.path.join(C.CACHE, "_inputs", variant)
    os.makedirs(d, exist_ok=True)
    fn = tag + ".csv"
    df.to_csv(os.path.join(d, fn), index=False)
    captured = {}
    orig_pr = nx.pagerank

    def _pr(G, *a, **k):        # observe the learned graph and the PageRank scores (no effect on the result)
        out = orig_pr(G, *a, **k)
        captured["n_edges"] = G.number_of_edges()
        captured["n_nodes"] = G.number_of_nodes()
        captured["scores"] = {str(n): float(v) for n, v in out.items()}
        return out

    R.nx.pagerank = _pr
    try:
        seed_all(seed)
        args = argparse.Namespace(root_path=d, data_path=fn)
        with contextlib.redirect_stdout(io.StringIO()):
            res = R.run(df, inject_time=inject_time, dataset="cods", args=args)
    finally:
        R.nx.pagerank = orig_pr
        try:
            os.remove(os.path.join(d, fn))
        except OSError:
            pass
    ranks = [str(r) for r in res["ranks"]]
    sc = captured.get("scores", {})
    vals = [sc[r] for r in ranks] if sc else []
    return {"ranks": ranks, "scores": sc, "n_edges": captured.get("n_edges"), "n_nodes": captured.get("n_nodes"),
            "n_rows_input": int(len(df)), "n_distinct_scores": len(set(round(v, 12) for v in vals)),
            "degenerate_input_order": bool(captured.get("n_edges") == 0)}


def causalrca_rank(data, cp, cands, seed):
    import contextlib
    import io
    from RCAEval.e2e.causalrca import causalrca
    df = data[["time"] + cands].copy()
    inject_time = float(df["time"].iloc[cp])
    seed_all(seed)
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        res = causalrca(df, inject_time=inject_time, dataset="cods")
    adj = np.asarray(res["adj"], dtype=float)
    n_nan = int(np.isnan(adj).sum())
    n_edges = int(np.count_nonzero(np.nan_to_num(adj)))
    ranks = [str(r) for r in res["ranks"]]
    return {"ranks": ranks, "n_edges": n_edges, "n_nan_adj": n_nan, "n_nodes": len(res["node_names"]),
            "nan_messages": buf.getvalue().count("nan error"),
            "degenerate_input_order": bool(n_edges == 0 or n_nan > 0) and ranks == list(res["node_names"])}


def job(args):
    method, rec, seed = args
    tag = rec["case_id"] if seed is None else "%s__seed%d" % (rec["case_id"], seed)
    cache = "%s/%s/%s.json" % (C.CACHE, method, tag)
    if os.path.exists(cache):
        return C.read_json(cache)
    data = pd.read_csv(C.resolve(rec["path"]))
    out = {"case_id": rec["case_id"], "method": method, "seed": seed}
    # adaptation (f): a few single-fault files end with rows whose timestamp is NaN (no data at all); RCD's own
    # time split already ignores them, for CIRCA we drop them. They all lie after the change point, so cp is unchanged.
    if data["time"].isna().any():
        keep = data["time"].notna()
        assert bool(keep.iloc[: rec["cp"] + 1].all()), "NaN timestamp before the change point"
        out["dropped_nan_time_rows"] = int((~keep).sum())
        data = data[keep].reset_index(drop=True)
    # adaptation (e): NaN cells are filled exactly as RCAEval's own @rca wrapper does (bfill, ffill, 0).
    # Only single-fault files contain NaN (e.g. *_error columns); the concurrent data_v2 files have none.
    nan_cols = [c for c in rec["candidates"] if data[c].isna().any()]
    if nan_cols:
        data[nan_cols] = data[nan_cols].bfill().ffill().fillna(0)
        out["nan_filled_cols"] = nan_cols
    t0 = time.time()
    try:
        if method in ("circa", "circa_rcaeval"):
            out.update(circa_rank(data, rec["cp"], rec["candidates"], method))
        elif method in ("run", "run_native"):
            out.update(run_rank(data, rec["cp"], rec["candidates"], seed, tag, method))
        elif method == "causalrca":
            out.update(causalrca_rank(data, rec["cp"], rec["candidates"], seed))
        else:
            out.update(rcd_rank(data, rec["cp"], rec["candidates"], seed))
        out["ok"] = True
    except Exception as e:
        import traceback
        out.update({"ok": False, "error": repr(e), "tb": traceback.format_exc()[-1500:], "ranks": []})
    out["runtime_s"] = time.time() - t0
    C.atomic_write_json(cache, out)
    return out


def run_boxed(args):
    """Run one (method, case, seed) job in its own interpreter with a wall-clock time box."""
    import subprocess
    method, rec, seed = args
    tag = rec["case_id"] if seed is None else "%s__seed%d" % (rec["case_id"], seed)
    cache = "%s/%s/%s.json" % (C.CACHE, method, tag)
    if os.path.exists(cache):
        return C.read_json(cache)
    env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", TQDM_DISABLE="1", PYTHONWARNINGS="ignore")
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, os.path.abspath(__file__), "_one", method, KIND, rec["case_id"],
                            str(seed)], env=env, timeout=TIMEBOX_S, capture_output=True, text=True)
        if os.path.exists(cache):
            return C.read_json(cache)
        out = {"case_id": rec["case_id"], "method": method, "seed": seed, "ok": False, "ranks": [],
               "error": "subprocess rc=%s without result" % p.returncode, "tb": (p.stderr or "")[-1500:]}
    except subprocess.TimeoutExpired:
        out = {"case_id": rec["case_id"], "method": method, "seed": seed, "ok": False, "ranks": [],
               "error": "timeout > %.0f s" % TIMEBOX_S, "timeout": True}
    out["runtime_s"] = time.time() - t0
    C.atomic_write_json(cache, out)
    return out


KIND = None


def load_recs(kind):
    recs = [r for r in C.read_json("%s/precompute_%s.json" % (C.OUT, kind)) if r.get("usable")]
    # SUBSET_REPS (single-fault only): stratified subset = the given repetitions of EVERY service x fault combo
    # (CIRCA's PC step costs ~2-4 min per 721x54 single-fault case).
    subset = os.environ.get("SUBSET_REPS")
    if subset and kind == "single":
        keep = set(subset.split(","))
        recs = [r for r in recs if r["case_id"].split("__")[-1] in keep]
    return recs


def main():
    global KIND
    if sys.argv[1] == "_one":          # child of run_boxed
        method, kind, case_id, seed = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
        rec = next(r for r in load_recs(kind) if r["case_id"] == case_id)
        job((method, rec, None if seed == "None" else int(seed)))
        return
    method, kind = sys.argv[1], sys.argv[2]
    KIND = kind
    workers = int(os.environ.get("WORKERS", "8"))
    limit = int(os.environ.get("LIMIT", "0"))
    recs = load_recs(kind)
    only = os.environ.get("ONLY_CASES")
    if only:
        recs = [r for r in recs if r["case_id"] in set(only.split(","))]
    if limit:
        recs = recs[:limit]
    os.makedirs("%s/%s" % (C.CACHE, method), exist_ok=True)
    if method == "rcd":
        jobs = [(method, r, s) for r in recs for s in RCD_SEEDS[kind]]
    elif method in LEARNED:
        jobs = [(method, r, s) for s in LEARNED_SEEDS for r in recs]
    else:
        jobs = [(method, r, None) for r in recs]
    t_start = time.time()
    res = []
    if method in LEARNED:
        from concurrent.futures import ThreadPoolExecutor
        ex = ThreadPoolExecutor(max_workers=workers)
        fn = run_boxed
    else:
        ex = ProcessPoolExecutor(max_workers=workers)
        fn = job
    with ex:
        futs = [ex.submit(fn, j) for j in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            res.append(f.result())
            if i % 10 == 0 or i == len(jobs):
                print("  %s/%s %d/%d (%.0fs)" % (method, kind, i, len(jobs), time.time() - t_start), flush=True)
    res.sort(key=lambda r: (r["case_id"], -1 if r["seed"] is None else r["seed"]))
    if not limit and not only:
        C.atomic_write_json("%s/causal_%s_%s.json" % (C.OUT, method, kind), res)
    nok = sum(1 for r in res if r["ok"])
    print("%s/%s: %d runs, %d ok, wall %.0fs, mean runtime/run %.2fs" % (
        method, kind, len(res), nok, time.time() - t_start, np.mean([r["runtime_s"] for r in res])))
    for r in res:
        if not r["ok"]:
            print("  FAIL", r["case_id"], r["seed"], r["error"])


if __name__ == "__main__":
    main()
