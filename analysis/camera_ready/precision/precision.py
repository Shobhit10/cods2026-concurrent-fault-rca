"""Precision of the separation rate: exact (Clopper-Pearson) 95% intervals, the
one-sided 95% upper bound, and the probability that n cases contain at least one separated case if the true rate is
p, 1-(1-p)^n. Counts: core held-out 2/30 (Table 3), larger set 4/138 (Section 4.3), its 108 new cases 1/108.
Usage: python analysis/camera_ready/precision/precision.py   (needs scipy; README lists the expected values)"""
from scipy.stats import beta


def interval(k, n, a=0.05):
    lo = 0.0 if k == 0 else beta.ppf(a / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - a / 2, k + 1, n - k)
    up = 1.0 if k == n else beta.ppf(1 - a, k + 1, n - k)
    return lo, hi, up


print("| set | separated | n | rate | exact 95% CI | one-sided 95% upper |")
print("|---|---|---|---|---|---|")
for name, k, n in [("core, held-out (merged)", 2, 30), ("larger set (merged)", 4, 138), ("108 new cases only", 1, 108)]:
    lo, hi, up = interval(k, n)
    print(f"| {name} | {k} | {n} | {k / n:.3f} | {lo:.3f}-{hi:.3f} | {up:.3f} |")
print()
print("| n | true rate p | P(at least one separated case) |")
print("|---|---|---|")
for n in (30, 138):
    for p in (0.03, 0.05, 0.07, 0.10):
        print(f"| {n} | {p:.2f} | {1 - (1 - p) ** n:.3f} |")
