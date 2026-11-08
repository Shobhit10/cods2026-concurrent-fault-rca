| Fold (held-out pair) | services | chosen (alpha, eps) | separation k/n | grouped AC@1 (sum/n) | single kept k/n | hit k/n | Both@2 k | Both@5 k | both causes in stage input k | Prop. 2.1: sep <= Both@|pi| |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 (boutique:pair1) | adservice (CPU) + cartservice (mem) | (0.7, 0.4) | 0/5 = 0.000 | 1.5/5 = 0.300 | 32/35 = 0.914 | 28/35 = 0.800 | 1 | 4 | 5/5 | holds (0 <= 5) |
| 2 (boutique:pair2) | currencyservice (CPU) + cartservice (mem) | (0.7, 0.4) | 0/5 = 0.000 | 2/5 = 0.400 | 34/35 = 0.971 | 19/35 = 0.543 | 1 | 5 | 5/5 | holds (0 <= 5) |
| 3 (boutique:pair3) | currencyservice (CPU) + productcatalogservice (mem) | (0.7, 0.4) | 1/5 = 0.200 | 0.5/5 = 0.100 | 32/35 = 0.914 | 33/35 = 0.943 | 1 | 3 | 5/5 | holds (1 <= 5) |
| 4 (sockshop:pair1) | catalogue (CPU) + carts (mem) | (0.7, 0.4) | 0/5 = 0.000 | 1.5/5 = 0.300 | 34/35 = 0.971 | 20/35 = 0.571 | 4 | 5 | 5/5 | holds (0 <= 5) |
| 5 (sockshop:pair2) | catalogue (CPU) + payment (mem) | (0.7, 0.4) | 0/5 = 0.000 | 2.5/5 = 0.500 | 24/30 = 0.800 | 23/30 = 0.767 | 5 | 5 | 5/5 | holds (0 <= 5) |
| 6 (sockshop:pair3) | carts (CPU) + payment (mem) | (0.7, 0.4) | 1/5 = 0.200 | 2.5/5 = 0.500 | 26/30 = 0.867 | 25/30 = 0.833 | 2 | 5 | 5/5 | holds (1 <= 5) |
| **Mean +/- SD (6 folds)** | | 6/6 (0.7, 0.4) | 0.067 +/- 0.103 | 0.350 +/- 0.152 | 0.906 +/- 0.066 | 0.743 +/- 0.156 | | | | |
| **Pooled held-out** | | | 2/30 = 0.067 | 10.5/30 = 0.350 | 182/200 = 0.910 | 148/200 = 0.740 | 14 | 27 | 30/30 | 6/6 folds |

Design comparison (same grid, same selection rule, same per-case scoring):

| design | folds | separation mean +/- SD | grouped AC@1 mean +/- SD | single kept mean +/- SD | hit mean +/- SD | pooled sep / gAC / kept / hit | params |
|---|---|---|---|---|---|---|---|
| published (crossval_results.csv) | 5 case-random | 0.073 +/- 0.101 | 0.277 +/- 0.132 | 0.910 +/- 0.034 | 0.740 +/- 0.055 | 2/28, 7.5/28, 182/200, 148/200 (implied) | 5/5 (0.7, 0.4) |
| published design re-run (seed 42, GT order) | 5 | 0.067 +/- 0.149 | 0.350 +/- 0.109 | 0.910 +/- 0.042 | 0.740 +/- 0.084 | 2/30, 10.5/30, 182/200, 148/200 | all (0.7, 0.4) |
| **LOPO (primary)**: pairs held out; single-fault scenarios grouped | 6 | 0.067 +/- 0.103 | 0.350 +/- 0.152 | 0.906 +/- 0.066 | 0.743 +/- 0.156 | 2/30, 10.5/30, 182/200, 148/200 | all (0.7, 0.4) |
| LOPO, single-fault split by case | 6 | 0.067 +/- 0.103 | 0.350 +/- 0.152 | 0.910 +/- 0.072 | 0.740 +/- 0.049 | 2/30, 10.5/30, 182/200, 148/200 | all (0.7, 0.4) |
| grouped 5-fold (pairs kept together, seed 42) | 5 | 0.060 +/- 0.089 | 0.340 +/- 0.152 | 0.910 +/- 0.052 | 0.740 +/- 0.063 | 2/30, 10.5/30, 182/200, 148/200 | all (0.7, 0.4) |
| grouped 5-fold, all 15 pair-merge choices | 5 each | 0.040-0.080 (means) | 0.320-0.380 | 0.910 | 0.740 | 2-2/30, 10.5-10.5/30, 182-182/200, 148-148/200 (min-max over 15) | all (0.7, 0.4) in 15/15 |

| quantity | scope | k / n | estimate | exact (Clopper-Pearson) 95% | Wilson 95% | bootstrap 95% | other |
|---|---|---|---|---|---|---|---|
| single-fault AC@1 | Online Boutique | 70/100 | 0.700 | [0.600, 0.788] | [0.604, 0.781] | [0.550, 0.840] (scenario-clustered) | |
| single-fault AC@1 | Sock Shop | 85/100 | 0.850 | [0.765, 0.914] | [0.767, 0.907] | [0.730, 0.950] (scenario-clustered) | |
| single-fault AC@1 | Both systems | 155/200 | 0.775 | [0.711, 0.831] | [0.712, 0.827] | [0.675, 0.865] (scenario-clustered) | |
| concurrent AC@2 | Online Boutique | 17/30 cause slots (15 cases) | 0.567 | [0.374, 0.745] (slots, approx.); conservative exact bracket [0.043, 0.998] | [0.392, 0.726] (slots) | [0.500, 0.600] (pair-clustered); [0.433, 0.700] (case) | cluster-robust t [0.423, 0.710] |
| concurrent AC@2 | Sock Shop | 26/30 cause slots (15 cases) | 0.867 | [0.693, 0.962] (slots, approx.); conservative exact bracket [0.449, 1.000] | [0.703, 0.947] (slots) | [0.700, 1.000] (pair-clustered); [0.733, 0.967] (case) | cluster-robust t [0.487, 1.246] |
| concurrent AC@2 | Both systems | 43/60 cause slots (30 cases) | 0.717 | [0.586, 0.825] (slots, approx.); conservative exact bracket [0.283, 0.999] | [0.592, 0.815] (slots) | [0.633, 0.783] (pair-clustered); [0.633, 0.800] (case) | cluster-robust t [0.513, 0.920] |
| **drop** single AC@1 - concurrent AC@2 | Online Boutique | 70/100 vs 17/30 | 0.133 | lower bound -0.398 (conservative exact) | [-0.053, 0.326] (Newcombe, slots) | [-0.030, 0.283] (pair/scenario-clustered) | cluster-robust t [-0.229, 0.496]; bootstrap P(diff<=0) = 0.05665 |
| **drop** single AC@1 - concurrent AC@2 | Sock Shop | 85/100 vs 26/30 | -0.017 | lower bound -0.235 (conservative exact) | [-0.132, 0.156] (Newcombe, slots) | [-0.197, 0.163] (pair/scenario-clustered) | cluster-robust t [-0.475, 0.441]; bootstrap P(diff<=0) = 0.57750 |
| **drop** single AC@1 - concurrent AC@2 | Both systems | 155/200 vs 43/60 | 0.058 | lower bound -0.288 (conservative exact) | [-0.058, 0.193] (Newcombe, slots) | [-0.063, 0.175] (pair/scenario-clustered) | cluster-robust t [-0.182, 0.299]; bootstrap P(diff<=0) = 0.17465 |
| Both@2 | Online Boutique | 3/15 | 0.200 | [0.043, 0.481] | [0.070, 0.452] |  | one-sided 95% upper 0.440 |
| Both@2 | Sock Shop | 11/15 | 0.733 | [0.449, 0.922] | [0.480, 0.891] |  | one-sided 95% upper 0.903 |
| Both@2 | Both systems | 14/30 | 0.467 | [0.283, 0.657] | [0.302, 0.639] | [0.300, 0.600] (pair-clustered) | one-sided 95% upper 0.630 |
| Both@3 | Online Boutique | 7/15 | 0.467 | [0.213, 0.734] | [0.248, 0.699] |  | one-sided 95% upper 0.700 |
| Both@3 | Sock Shop | 14/15 | 0.933 | [0.681, 0.998] | [0.702, 0.988] |  | one-sided 95% upper 0.997 |
| Both@3 | Both systems | 21/30 | 0.700 | [0.506, 0.853] | [0.521, 0.833] | [0.633, 0.767] (pair-clustered) | one-sided 95% upper 0.834 |
| Both@5 | Online Boutique | 12/15 | 0.800 | [0.519, 0.957] | [0.548, 0.930] |  | one-sided 95% upper 0.943 |
| Both@5 | Sock Shop | 15/15 | 1.000 | [0.782, 1.000] | [0.796, 1.000] |  | one-sided 95% upper 1.000 |
| Both@5 | Both systems | 27/30 | 0.900 | [0.735, 0.979] | [0.744, 0.965] | [0.800, 1.000] (pair-clustered) | one-sided 95% upper 0.972 |
| Any@5 | Online Boutique | 15/15 | 1.000 | [0.782, 1.000] | [0.796, 1.000] |  | one-sided 95% upper 1.000 |
| Any@5 | Sock Shop | 15/15 | 1.000 | [0.782, 1.000] | [0.796, 1.000] |  | one-sided 95% upper 1.000 |
| Any@5 | Both systems | 30/30 | 1.000 | [0.884, 1.000] | [0.886, 1.000] | [1.000, 1.000] (pair-clustered) | one-sided 95% upper 1.000 |
| Any@2 (post hoc helper) | Online Boutique | 14/15 | 0.933 | [0.681, 0.998] | [0.702, 0.988] | | |
| Any@2 (post hoc helper) | Sock Shop | 15/15 | 1.000 | [0.782, 1.000] | [0.796, 1.000] | | |
| Any@2 (post hoc helper) | Both systems | 29/30 | 0.967 | [0.828, 0.999] | [0.833, 0.994] | | |
| separation, reconstructed published 5-fold (pooled held-out; fold mean 0.067) | Both systems | 2/30 | 0.067 | [0.008, 0.221] | [0.018, 0.213] | | one-sided 95% upper 0.195 |
| separation, LOPO (pooled held-out; fold mean 0.067) | Both systems | 2/30 | 0.067 | [0.008, 0.221] | [0.018, 0.213] | | one-sided 95% upper 0.195 |
| single kept, LOPO pooled | Both systems | 182/200 | 0.910 | [0.861, 0.946] | [0.862, 0.942] | | one-sided 95% upper 0.941 |
| hit rate, LOPO pooled | Both systems | 148/200 | 0.740 | [0.673, 0.799] | [0.675, 0.796] | | one-sided 95% upper 0.791 |
| grouped AC@1, LOPO pooled (cause slots, approx.) | Both systems | 21/60 | 0.350 | [0.231, 0.484] | [0.242, 0.476] | | one-sided 95% upper 0.464 |

| exact / permutation test | scope | table | statistic | p (one-sided) |
|---|---|---|---|---|
| Fisher exact, one-sided (single AC@1 hits vs concurrent top-2 cause-slot hits) | Online Boutique | [[70,30],[17,13]] | 1.784 | 0.13 |
| Fisher exact, one-sided, case level, concurrent success = at least one cause in top-2 (generous to concurrent) | Online Boutique | [[70,30],[14,1]] | 0.167 | 0.99 |
| Fisher exact, one-sided (single AC@1 hits vs concurrent top-2 cause-slot hits) | Sock Shop | [[85,15],[26,4]] | 0.872 | 0.69 |
| Fisher exact, one-sided, case level, concurrent success = at least one cause in top-2 (generous to concurrent) | Sock Shop | [[85,15],[15,0]] | 0.000 | 1 |
| Fisher exact, one-sided (single AC@1 hits vs concurrent top-2 cause-slot hits) | Both systems | [[155,45],[43,17]] | 1.362 | 0.22 |
| Fisher exact, one-sided, case level, concurrent success = at least one cause in top-2 (generous to concurrent) | Both systems | [[155,45],[29,1]] | 0.119 | 1 |
| exact cluster-permutation test, one-sided (all C(23,3) relabelings of 3 of 23 clusters as 'concurrent'); statistic = mean(single) - mean(concurrent) | Online Boutique | 20 scenario clusters + 3 pair clusters; 1771 relabelings | 0.133 | 0.27 |
| exact cluster-permutation test, one-sided (all C(23,3) relabelings of 3 of 23 clusters as 'concurrent'); statistic = mean(single) - mean(concurrent) | Sock Shop | 20 scenario clusters + 3 pair clusters; 1771 relabelings | -0.017 | 0.56 |
| exact stratified cluster-permutation test, one-sided (relabel within each system; statistic = pooled mean(single) - pooled mean(concurrent)) | Both systems | 3136441 relabelings | 0.058 | 0.33 |
| case-level stratified permutation test, one-sided, Monte Carlo (200000 permutations) | Both systems | 200 single + 30 concurrent cases | 0.058 | 0.26 |
| exact McNemar (separated vs Both@2, paired per case) | Both systems | separated-not-Both@2=2, Both@2-not-separated=14 | -12.000 | 0.0042 |

