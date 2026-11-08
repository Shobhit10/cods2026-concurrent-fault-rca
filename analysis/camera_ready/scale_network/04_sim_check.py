"""Step 4 (plain Python). Two checks on the scale model.

(a) Brute-force SIMULATION cross-check of the exact noise-floor computation in 03_scale_model.py: for each case,
    draw N - N0 healthy services from the pool, MERGE their real entry scores with the case's real ranked entries,
    re-sort, and evaluate Both@k with the paper's definition (common.entry_metrics, Eq. 3). Independent code path
    (no rank decomposition). Must agree with the exact values within Monte-Carlo error.
(b) Random-ranking reference AT THE MEASURED SCALE: exact probability that a uniformly random order of each
    case's own n entries puts an entry of both causes in the top k (entry convention of Eq. 3).
"""
import os
import sys
from math import comb

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUT, atomic_write_csv, entry_metrics

R = 2000
SEED = 7
N_CHECK = [6, 8, 12, 25]


def rand_both(n, ma, mb, k):
    if k >= n:
        return 1.0
    t = comb(n, k)
    return 1 - comb(n - ma, k) / t - comb(n - mb, k) / t + comb(n - ma - mb, k) / t


def main():
    ent = pd.read_csv(os.path.join(OUT, "cods_entry_scores.csv"))
    quiet = pd.read_csv(os.path.join(OUT, "quiet_pool_scores.csv"))
    exact = pd.read_csv(os.path.join(OUT, "scale_model_long.csv"))
    pools = {"quiet": quiet[quiet.split == "9+9"], "perturbed": ent[ent.role == "non_cause"]}
    pvec = {name: {ns: [g.score.to_numpy() for _, g in df[df.ns == ns].groupby(["case_id", "service"])]
                   for ns in ("boutique", "sock-shop")} for name, df in pools.items()}
    rng = np.random.default_rng(SEED)

    rows = []
    for name in pools:
        for N in N_CHECK:
            hits = {2: [], 5: []}
            for cid, g in ent.groupby("case_id", sort=False):
                g = g.sort_values("rank")
                ns = g.ns.iloc[0]
                n0 = 5 if ns == "boutique" else 3
                svc = sorted(g.service.unique())
                causes = [g[g.role == "cpu_cause"].service.iloc[0], g[g.role == "mem_cause"].service.iloc[0]]
                base_e, base_s = g.entry.tolist(), g.score.to_numpy()
                pool = pvec[name][ns]
                for _ in range(R):
                    pick = rng.integers(0, len(pool), size=max(N - n0, 0))
                    add_s = [pool[i] for i in pick]
                    add_e = [f"added{a}_m{j}" for a, s in enumerate(add_s) for j in range(len(s))]
                    sc = np.concatenate([base_s] + add_s) if add_s else base_s
                    names = base_e + add_e
                    order = np.argsort(-sc, kind="stable")  # ties: measured entries stay ahead
                    ranked = [names[i] for i in order]
                    m = entry_metrics(ranked, causes, svc + [f"added{a}" for a in range(len(add_s))])
                    hits[2].append(m["both2"])
                    hits[5].append(m["both5"])
            for k in (2, 5):
                mc = float(np.mean(hits[k]))
                se = float(np.std(hits[k]) / np.sqrt(len(hits[k])))
                ex = exact[(exact.model == f"ii_noise_{name}") & (exact.k == k) & (exact.N == N)
                           & (exact.scope == "overall")].both_k.iloc[0]
                rows.append({"pool": name, "N": N, "k": k, "simulated": mc, "mc_se": se, "exact": ex,
                             "z": (mc - ex) / se if se > 0 else 0.0})
    chk = pd.DataFrame(rows)
    atomic_write_csv(chk, os.path.join(OUT, "mc_crosscheck.csv"))
    print(chk.round(4).to_string(index=False))
    print("max |z| =", round(chk.z.abs().max(), 2))

    rr = []
    for cid, g in ent.groupby("case_id", sort=False):
        n = len(g)
        ma, mb = int((g.role == "cpu_cause").sum()), int((g.role == "mem_cause").sum())
        rr.append({"case_id": cid, "ns": g.ns.iloc[0], "n": n, "m_cpu": ma, "m_mem": mb,
                   "rand_both2": rand_both(n, ma, mb, 2), "rand_both5": rand_both(n, ma, mb, 5),
                   "rand_any5": 1 - comb(n - ma - mb, 5) / comb(n, 5)})
    rr = pd.DataFrame(rr)
    atomic_write_csv(rr, os.path.join(OUT, "random_at_measured_scale.csv"))
    print(rr.groupby("ns")[["n", "m_cpu", "m_mem", "rand_both2", "rand_both5", "rand_any5"]].mean().round(3).to_string())
    print("overall:", rr[["rand_both2", "rand_both5", "rand_any5"]].mean().round(3).to_dict())


if __name__ == "__main__":
    main()
