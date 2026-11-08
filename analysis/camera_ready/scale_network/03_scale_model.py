"""Step 3 (plain Python: numpy + pandas). SCALE MODEL for the Both@k ceiling (Proposition 2.1).
THIS IS A MODEL, NOT A MEASUREMENT. It is calibrated on the paper's 28 concurrent CPU+memory cases.

Unit of scale: N = candidate services the ranker scores (about five metric entries each). The measured
lists had N0 = 5 candidate services in Online Boutique (n = 15-25 entries, mostly 21-25) and N0 = 3 in
Sock Shop (n = 7-13). k counts metric entries, as in the paper (Eq. 3): Both@k holds when both causes have
an entry in the top k entries. Each case is grown from its own N0 to max(N, N0), so the pooled curve equals the
measured pooled value at N = 3 and every N >= 5 grows both systems.

Per case, with w the worse-ranked cause and b the better one, the measured rank of w's first entry is
    r_w = 1 + a_b + a_h,
a_b = entries of b ranked above it, a_h = non-cause entries ranked above it. Both@k holds iff r_w <= k.
Scaling to N adds N - N0 non-cause services. Models (all reproduce the measured Both@k at N = N0 except the
envelope marked *):

  R      random ranking, analytic: C(N-2,k-2)/C(N,k) = k(k-1)/(N(N-1)) over services (as specified);
         entry-level variant with m = 5 entries per service in the CSV.
  i      relative rank, literal: a cause at rank r of n keeps its relative position, r -> r N/N0
         (both causes; continuous, no rounding).
  i'     relative rank among non-causes (percentile-preserving): the non-cause entries above w scale with the
         number of non-cause services, r_w -> 1 + a_b + a_h (N-2)/(N0-2); a cause with no non-cause above it
         stays where it is.
  ii     noise floor: every added service is an independent draw from an EMPIRICAL pool of healthy-service
         score vectors and contributes its entries that score strictly above w's best score.
         ii-quiet   pool = placebo scores of every instrumented service on the fault-free pre-injection window
                    (out/quiet_pool_scores.csv, split 9+9 rows; 12+6 as sensitivity). Blast radius fixed at what
                    was measured; only far-away healthy services are added.
         ii-perturbed pool = post-change-point scores of the non-injected services in the same cases
                    (pessimistic: every added service is as disturbed as the faults' neighbours).
         ii-quiet* envelope with coupling removed (a_h := 0): only healthy noise competes with the causes.
         Exact: P(a_b + a_h + X <= k-1), X = sum of N-N0 iid draws, by truncated polynomial powers.

Uncertainty: stratified case bootstrap (B = 4000; Boutique and Sock Shop resampled separately); the empirical
pools are rebuilt from the resampled cases in every replicate, so calibration AND pool uncertainty propagate.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUT, atomic_write_csv, atomic_write_text, comb_ratio_both, random_entry_both

N_TABLE = [12, 25, 50, 100, 250, 500]
N_PLOT = [3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 35, 50, 75, 100, 150, 250, 350, 500]
KS = [2, 5]
B = 4000
SEED = 20261025
MAXC = 5  # count bins 0..4 kept exactly, bin 5 = ">= 5" (never compatible with k <= 5)


def decompose(ent):
    rows = []
    for cid, g in ent.groupby("case_id", sort=False):
        g = g.sort_values("rank")
        ns = g.ns.iloc[0]
        n0 = 5 if ns == "boutique" else 3
        first = {r: int(g[g.role == r]["rank"].min()) for r in ("cpu_cause", "mem_cause")}
        w = max(first, key=first.get)
        b = "mem_cause" if w == "cpu_cause" else "cpu_cause"
        rw = first[w]
        above = g[g["rank"] < rw]
        a_b, a_h = int((above.role == b).sum()), int((above.role == "non_cause").sum())
        assert rw == 1 + a_b + a_h
        rows.append({"case_id": cid, "ns": ns, "N0": n0, "n_entries": len(g), "worse": w,
                     "r_cpu": first["cpu_cause"], "r_mem": first["mem_cause"], "r_better": first[b],
                     "r_worse": rw, "a_b": a_b, "a_h": a_h,
                     "s_worse": float(g[g.role == w].score.max()), "s_better": float(g[g.role == b].score.max())})
    return pd.DataFrame(rows)


def pool_vectors(df, ns_col="ns"):
    vec = []
    for (cid, svc), v in df.groupby(["case_id", "service"], sort=True):
        vec.append((cid, v[ns_col].iloc[0], v.score.to_numpy()))
    return vec


def trunc_mul(a, b):
    out = np.zeros(np.broadcast_shapes(a.shape, b.shape))
    for i in range(MAXC):
        out[..., i:MAXC] += a[..., i:i + 1] * b[..., : MAXC - i]
    return out


def trunc_pow(p, n):
    res = np.zeros_like(p)
    res[..., 0] = 1.0
    base = p.copy()
    while n > 0:
        if n & 1:
            res = trunc_mul(res, base)
        base = trunc_mul(base, base)
        n >>= 1
    return res


def p_le(pmf, add, t):
    """pmf (..., C, MAXC+1); t (C,) -> P(sum of `add` draws <= t) with shape (..., C)."""
    coef = trunc_pow(pmf[..., :MAXC], int(add))
    cdf = np.cumsum(coef, axis=-1)
    tt = np.clip(t, 0, MAXC - 1).astype(int)
    val = np.take_along_axis(cdf, np.broadcast_to(tt, cdf.shape[:-1])[..., None], axis=-1)[..., 0]
    return np.where(t < 0, 0.0, val)


def main():
    ent = pd.read_csv(os.path.join(OUT, "cods_entry_scores.csv"))
    quiet = pd.read_csv(os.path.join(OUT, "quiet_pool_scores.csv"))
    dec = decompose(ent)
    atomic_write_csv(dec, os.path.join(OUT, "cods_case_decomposition.csv"))
    cases = dec.case_id.tolist()
    C = len(cases)
    cidx = {c: i for i, c in enumerate(cases)}
    ns_arr = dec.ns.to_numpy()

    pools = {"quiet": pool_vectors(quiet[quiet.split == "9+9"]),
             "quiet12": pool_vectors(quiet[quiet.split == "12+6"]),
             "perturbed": pool_vectors(ent[ent.role == "non_cause"])}

    # onehot[j, v, c]: pool vector v (same system as case j) has c entries above case j's worse-cause score
    onehots, vcase = {}, {}
    for name, vec in pools.items():
        oh = np.zeros((C, len(vec), MAXC + 1))
        for v, (cid, ns, sc) in enumerate(vec):
            for j in range(C):
                if ns_arr[j] == ns:
                    oh[j, v, min(int((sc > dec.s_worse.iloc[j]).sum()), MAXC)] = 1.0
        onehots[name] = oh
        vcase[name] = np.array([cidx[cid] for cid, _, _ in vec])

    # per-case calibration of the noise floor (reported)
    prow = []
    for j, c in dec.iterrows():
        r = {"case_id": c.case_id, "ns": c.ns, "s_worse": c.s_worse, "s_better": c.s_better}
        for name, vec in pools.items():
            same = [sc for _, ns, sc in vec if ns == c.ns]
            r[f"p_{name}_above_worse"] = float(np.mean([(sc > c.s_worse).any() for sc in same]))
            r[f"p_{name}_above_better"] = float(np.mean([(sc > c.s_better).any() for sc in same]))
            r[f"mean_entries_{name}_above_worse"] = float(np.mean([(sc > c.s_worse).sum() for sc in same]))
        prow.append(r)
    pdf = pd.DataFrame(prow)
    atomic_write_csv(pdf, os.path.join(OUT, "noise_floor_p.csv"))

    # stratified bootstrap weights; row 0 = the observed sample
    rng = np.random.default_rng(SEED)
    W = np.zeros((B + 1, C))
    W[0] = 1.0
    for ns in ("boutique", "sock-shop"):
        ids = np.where(ns_arr == ns)[0]
        draw = rng.choice(ids, size=(B, len(ids)), replace=True)
        for b in range(B):
            W[b + 1] += np.bincount(draw[b], minlength=C)

    pmfs = {}
    for name, oh in onehots.items():
        wv = W[:, vcase[name]]                                     # (B+1, V)
        num = np.einsum("bv,jvc->bjc", wv, oh)
        den = num.sum(axis=-1, keepdims=True)
        pmfs[name] = np.divide(num, den, out=np.zeros_like(num), where=den > 0)

    a_b, a_h, N0 = dec.a_b.to_numpy(), dec.a_h.to_numpy(), dec.N0.to_numpy()
    r_cpu, r_mem = dec.r_cpu.to_numpy(), dec.r_mem.to_numpy()
    scopes = {"overall": np.ones(C, bool), "boutique": ns_arr == "boutique", "sock-shop": ns_arr == "sock-shop"}

    def summarise(vals):  # vals (B+1, C)
        out = {}
        for s, m in scopes.items():
            ws = W[:, m]
            est = (ws * vals[:, m]).sum(1) / ws.sum(1)
            out[s] = (est[0], np.percentile(est[1:], 2.5), np.percentile(est[1:], 97.5), est)
        return out

    rows, boot_keep = [], {}
    for N in N_PLOT:
        for k in KS:
            vals = {}
            Ne = np.maximum(N, N0)  # a case is never shrunk below its instrumented size (matters only for N < 5)
            vals["i_relative_rank"] = np.broadcast_to(
                (np.maximum(r_cpu, r_mem) * Ne / N0 <= k + 1e-9).astype(float), (B + 1, C))
            vals["i2_relative_rank_noncause"] = np.broadcast_to(
                (1 + a_b + a_h * (Ne - 2) / (N0 - 2) <= k + 1e-9).astype(float), (B + 1, C))
            for name in pools:
                pv = np.zeros((B + 1, C))
                for n0 in (3, 5):
                    m = N0 == n0
                    pv[:, m] = p_le(pmfs[name][:, m], max(N - n0, 0), (k - 1 - a_b - a_h)[m])
                vals[f"ii_noise_{name}"] = pv
            pv = np.zeros((B + 1, C))
            for n0 in (3, 5):
                m = N0 == n0
                pv[:, m] = p_le(pmfs["quiet"][:, m], max(N - n0, 0), (k - 1 - a_b)[m])
            vals["ii_noise_quiet_nocoupling_envelope"] = pv
            for model, v in vals.items():
                for s, (est, lo, hi, bs) in summarise(v).items():
                    rows.append({"N": N, "k": k, "model": model, "scope": s, "both_k": est,
                                 "ci_lo": lo, "ci_hi": hi, "n_cases": int(scopes[s].sum())})
                    if s == "overall":
                        boot_keep[(model, k, N)] = bs
            rows.append({"N": N, "k": k, "model": "R_random_service", "scope": "analytic",
                         "both_k": comb_ratio_both(N, k), "ci_lo": np.nan, "ci_hi": np.nan, "n_cases": 0})
            rows.append({"N": N, "k": k, "model": "R_random_entry_m5", "scope": "analytic",
                         "both_k": random_entry_both(N, 5, k), "ci_lo": np.nan, "ci_hi": np.nan, "n_cases": 0})
    long = pd.DataFrame(rows)
    atomic_write_csv(long, os.path.join(OUT, "scale_model_long.csv"))

    # measured (N = N0) with the same bootstrap
    meas = {}
    for k in KS:
        v = np.broadcast_to((dec.r_worse.to_numpy() <= k).astype(float), (B + 1, C))
        meas[k] = summarise(v)

    # wide table at the requested N
    order = ["R_random_service", "R_random_entry_m5", "i_relative_rank", "i2_relative_rank_noncause",
             "ii_noise_quiet", "ii_noise_quiet12", "ii_noise_perturbed", "ii_noise_quiet_nocoupling_envelope"]
    trows = []
    for k in KS:
        for model in order:
            sub = long[(long.k == k) & (long.model == model) & long.scope.isin(["overall", "analytic"])]
            r = {"k": k, "model": model}
            for N in N_TABLE:
                x = sub[sub.N == N].iloc[0]
                r[f"N{N}"] = x.both_k
                r[f"N{N}_lo"], r[f"N{N}_hi"] = x.ci_lo, x.ci_hi
            trows.append(r)
    tab = pd.DataFrame(trows)
    atomic_write_csv(tab, os.path.join(OUT, "scale_table.csv"))

    # plot data (overall), pgfplots-friendly column names
    short = {"R_random_service": "rand", "i_relative_rank": "rel", "i2_relative_rank_noncause": "relnc",
             "ii_noise_quiet": "quiet", "ii_noise_quiet12": "quiettwelve", "ii_noise_perturbed": "pert",
             "ii_noise_quiet_nocoupling_envelope": "env", "R_random_entry_m5": "randentry"}
    pl = long[long.scope.isin(["overall", "analytic"])].copy()
    pl["col"] = pl.model.map(short) + pl.k.map({2: "two", 5: "five"})
    piv = pl.pivot_table(index="N", columns="col", values="both_k").reset_index()
    for k, kk in ((2, "two"), (5, "five")):
        q = long[(long.model == "ii_noise_quiet") & (long.k == k) & (long.scope == "overall")].set_index("N")
        piv[f"quiet{kk}lo"] = piv.N.map(q.ci_lo)
        piv[f"quiet{kk}hi"] = piv.N.map(q.ci_hi)
    atomic_write_csv(piv.round(5), os.path.join(OUT, "scale_plot_data.csv"))

    # honest test: does the ceiling fall with N?  drop = measured - model(N), per bootstrap replicate
    tests = []
    for k in KS:
        mb = meas[k]["overall"][3]
        for model in order[2:]:
            for N in N_TABLE:
                d = mb - boot_keep[(model, k, N)]
                tests.append({"k": k, "model": model, "N": N, "measured": mb[0], "model_value": boot_keep[(model, k, N)][0],
                              "drop": d[0], "drop_lo": np.percentile(d[1:], 2.5), "drop_hi": np.percentile(d[1:], 97.5),
                              "p_boot_drop_le_0": float((d[1:] <= 1e-12).mean())})
    tests = pd.DataFrame(tests)
    atomic_write_csv(tests, os.path.join(OUT, "scale_fall_test.csv"))

    summary = {
        "measured_at_N0": {k: {s: [round(v[0], 4), round(v[1], 4), round(v[2], 4)] for s, v in meas[k].items()} for k in KS},
        "pool_sizes": {name: {ns: sum(1 for _, n, _ in vec if n == ns) for ns in ("boutique", "sock-shop")}
                       for name, vec in pools.items()},
        "p_service_above_worse_mean": {c: {ns: round(float(pdf[pdf.ns == ns][c].mean()), 4) for ns in ("boutique", "sock-shop")}
                                       for c in pdf.columns if c.startswith("p_")},
        "worse_cause_score_median": round(float(dec.s_worse.median()), 3),
        "better_cause_score_median": round(float(dec.s_better.median()), 3),
        "cases_with_a_h_zero": int((dec.a_h == 0).sum()),
        "B": B, "seed": SEED,
    }
    atomic_write_text(os.path.join(OUT, "scale_model_summary.json"), json.dumps(summary, indent=2))

    pd.set_option("display.width", 250)
    print(json.dumps(summary, indent=1))
    show = tab[["k", "model"] + [f"N{N}" for N in N_TABLE]]
    print(show.round(4).to_string(index=False))
    print(tests[tests.model.isin(["ii_noise_quiet", "i2_relative_rank_noncause"])].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
