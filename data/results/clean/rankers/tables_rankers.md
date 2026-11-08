## Concurrent faults (n = 30 cases; metric-level lists, paper definitions)

| Ranker | AC@1 | AC@2 | AC@3 | AC@5 | Both@2 [95% CI] | Both@5 [95% CI] | Any@5 [95% CI] | Both@all (list) | mean list length |
|---|---|---|---|---|---|---|---|---|---|
| Robust (paper) | 0.317 | 0.383 | 0.717 | 0.867 | 0.100 [0.02, 0.27] | 0.767 [0.58, 0.90] | 0.967 [0.83, 1.00] | 1.000 | 19.5 |
| N-Sigma | 0.133 | 0.200 | 0.433 | 0.683 | 0.067 [0.01, 0.22] | 0.500 [0.31, 0.69] | 0.867 [0.69, 0.96] | 1.000 | 19.5 |
| PageRank (graph) | 0.250 | 0.250 | 0.250 | 0.267 | 0.000 [0.00, 0.12] | 0.000 [0.00, 0.12] | 0.533 [0.34, 0.72] | 1.000 | 19.5 |
| CIRCA (causal) | 0.217 | 0.367 | 0.533 | 0.683 | 0.133 [0.04, 0.31] | 0.467 [0.28, 0.66] | 0.900 [0.73, 0.98] | 1.000 | 19.5 |
| CIRCA, RCAEval defaults | 0.200 | 0.350 | 0.467 | 0.717 | 0.100 [0.02, 0.27] | 0.500 [0.31, 0.69] | 0.933 [0.78, 0.99] | 1.000 | 17.1 |
| RCD (causal) (10 seeds) | 0.223 ± 0.045 | 0.397 ± 0.031 | 0.475 ± 0.055 | 0.553 ± 0.052 | 0.117 ± 0.042 | 0.293 ± 0.081 | 0.813 ± 0.042 | 0.327 ± 0.081 | 3.7 |
| Random ranking | 0.268 | 0.472 | 0.624 | 0.816 | 0.162 | 0.659 | 0.973 | 1.000 | 19.5 |

### Stage (released cluster_candidates_v2, alpha=0.7, eps=0.4, minPts=2) on each ranker's list

k_in = entries the stage partitions; Prop. 2.1 bound = Both@k_in (fraction of cases with both causes among those entries); violations = cases separated although a cause is missing from the input.

| Ranker | input | k_in | separation [95% CI] | bound Both@k_in | ≤ Both@2? | violations | grouped AC@1 | separation, suffix-aware svc mapping | oracle-grid max sep. (α,ε) |
|---|---|---|---|---|---|---|---|---|---|
| Robust (paper) | full | 19.5 | 0.567 [0.37, 0.75] | 1.000 | NO | 0 | 0.633 | 0.533 | 0.567 (0.7, 0.40); 1/15 settings > Both@2 |
| Robust (paper) | top10 | 10.0 | 0.533 [0.34, 0.72] | 0.967 | NO | 0 | 0.617 | 0.533 | 0.533 (0.7, 0.40); 1/15 settings > Both@2 |
| Robust (paper) | top5 | 5.0 | 0.333 [0.17, 0.53] | 0.767 | NO | 0 | 0.583 | 0.400 | 0.333 (0.7, 0.40); 1/15 settings > Both@2 |
| N-Sigma | full | 19.5 | 0.067 [0.01, 0.22] | 1.000 | yes | 0 | 0.167 | 0.067 | 0.467 (0.3, 0.30); 14/15 settings > Both@2 |
| N-Sigma | top10 | 10.0 | 0.133 [0.04, 0.31] | 0.933 | NO | 0 | 0.200 | 0.133 | 0.133 (0.7, 0.40); 1/15 settings > Both@2 |
| N-Sigma | top5 | 5.0 | 0.067 [0.01, 0.22] | 0.500 | yes | 0 | 0.150 | 0.067 | 0.067 (0.7, 0.40); 0/15 settings > Both@2 |
| PageRank (graph) | full | 19.5 | 0.433 [0.25, 0.63] | 1.000 | NO | 0 | 0.200 | 0.367 | 0.433 (0.7, 0.40); 14/15 settings > Both@2 |
| PageRank (graph) | top10 | 10.0 | 0.133 [0.04, 0.31] | 0.267 | NO | 0 | 0.200 | 0.100 | 0.133 (0.7, 0.40); 1/15 settings > Both@2 |
| PageRank (graph) | top5 | 5.0 | 0.000 [0.00, 0.12] | 0.000 | yes | 0 | 0.200 | 0.000 | 0.000 (0.3, 0.10); 0/15 settings > Both@2 |
| CIRCA (causal) | full | 19.5 | 0.033 [0.00, 0.17] | 1.000 | yes | 0 | 0.250 | 0.033 | 0.433 (0.3, 0.30); 14/15 settings > Both@2 |
| CIRCA (causal) | top10 | 10.0 | 0.067 [0.01, 0.22] | 0.900 | yes | 0 | 0.267 | 0.067 | 0.100 (0.3, 0.30); 0/15 settings > Both@2 |
| CIRCA (causal) | top5 | 5.0 | 0.067 [0.01, 0.22] | 0.467 | yes | 0 | 0.233 | 0.067 | 0.067 (0.7, 0.40); 0/15 settings > Both@2 |
| CIRCA, RCAEval defaults | full | 17.1 | 0.033 [0.00, 0.17] | 1.000 | yes | 0 | 0.233 | 0.000 | 0.633 (0.3, 0.30); 14/15 settings > Both@2 |
| CIRCA, RCAEval defaults | top10 | 10.0 | 0.067 [0.01, 0.22] | 0.900 | yes | 0 | 0.233 | 0.000 | 0.100 (0.3, 0.10); 0/15 settings > Both@2 |
| CIRCA, RCAEval defaults | top5 | 5.0 | 0.000 [0.00, 0.12] | 0.500 | yes | 0 | 0.233 | 0.000 | 0.067 (0.3, 0.10); 0/15 settings > Both@2 |
| RCD (causal) | full | 3.7 | 0.030 ± 0.025 | 0.327 ± 0.081 | yes | 0 | 0.210 ± 0.041 | 0.030 ± 0.029 | 0.030 (0.7, 0.40); 0/15 settings > Both@2 |
| RCD (causal) | top10 | 3.7 | 0.030 ± 0.025 | 0.327 ± 0.081 | yes | 0 | 0.210 ± 0.041 | 0.030 ± 0.029 | 0.030 (0.7, 0.40); 0/15 settings > Both@2 |
| RCD (causal) | top5 | 3.2 | 0.020 ± 0.023 | 0.293 ± 0.081 | yes | 0 | 0.207 ± 0.045 | 0.020 ± 0.028 | 0.020 (0.7, 0.40); 0/15 settings > Both@2 |
| Random ranking | full | 19.5 | 0.091 | 1.000 | yes | 0 | 0.296 | 0.059 | – |
| Random ranking | top10 | 10.0 | 0.076 | 0.946 | yes | 0 | 0.291 | 0.049 | – |
| Random ranking | top5 | 5.0 | 0.036 | 0.663 | yes | 0 | 0.277 | 0.028 | – |

### Below chance? P(X ≤ observed) under a uniformly random ranking of the same candidates (Poisson-binomial over the 28 exact per-case probabilities)

| Ranker | Both@2 obs / E_random (p) | Both@5 obs / E_random (p) | Any@5 obs / E_random (p) |
|---|---|---|---|
| Robust (paper) | 3 / 4.9 (p = 0.254) | 23 / 19.8 (p = 0.943) | 29 / 29.2 (p = 0.56) |
| N-Sigma | 2 / 4.9 (p = 0.109) | 15 / 19.8 (p = 0.0397) | 26 / 29.2 (p = 0.00676) |
| PageRank (graph) | 0 / 4.9 (p = 0.00438) | 0 / 19.8 (p = 1.01e-16) | 16 / 29.2 (p = 2.21e-17) |
| CIRCA (causal) | 4 / 4.9 (p = 0.448) | 14 / 19.8 (p = 0.0156) | 27 / 29.2 (p = 0.0423) |
| CIRCA, RCAEval defaults | 3 / 4.9 (p = 0.254) | 15 / 19.8 (p = 0.0397) | 28 / 29.2 (p = 0.188) |
| RCD (causal) | 3.5 (seeds 2–6) / 4.9 (median p 0.254) | 8.8 (seeds 4–13) / 19.8 (median p 1.59e-05) | 24.4 (seeds 23–27) / 29.2 (median p 7.28e-05) |

### Service-level lists (each service once, first occurrence)

| Ranker | svc AC@1 | svc AC@2 | svc Both@2 | svc Both@3 | svc Both@5 | svc Any@1 | svc Any@2 | svc Any@5 |
|---|---|---|---|---|---|---|---|---|
| Robust (paper) | 0.317 | 0.733 | 0.500 | 0.767 | 1.000 | 0.633 | 0.967 | 1.000 |
| N-Sigma | 0.133 | 0.483 | 0.167 | 0.600 | 1.000 | 0.267 | 0.800 | 1.000 |
| PageRank (graph) | 0.250 | 0.500 | 0.200 | 0.600 | 1.000 | 0.500 | 0.800 | 1.000 |
| CIRCA (causal) | 0.217 | 0.500 | 0.200 | 0.667 | 1.000 | 0.433 | 0.800 | 1.000 |
| CIRCA, RCAEval defaults | 0.200 | 0.417 | 0.100 | 0.600 | 1.000 | 0.400 | 0.733 | 1.000 |
| RCD (causal) | 0.223 ± 0.045 | 0.445 ± 0.029 | 0.130 ± 0.046 | 0.287 ± 0.080 | 0.327 ± 0.081 | 0.447 ± 0.089 | 0.760 ± 0.031 | 0.820 ± 0.042 |
| Random ranking | 0.267 | 0.533 | 0.217 | 0.650 | 1.000 | 0.533 | 0.850 | 1.000 |
| pagerank_all_graph_nodes (original run_graph_ranker.py design) | 0.000 | 0.183 | 0.000 | 0.000 | 0.533 | 0.000 | 0.367 | 1.000 |
| deviation_service_max (original run_graph_ranker.py design) | 0.333 | 0.733 | 0.500 | 0.767 | 1.000 | 0.667 | 0.967 | 1.000 |

### Per system (AC@2 / Both@2 / Both@5 / Any@5)

| Ranker | Online Boutique (15) | Sock Shop (13) |
|---|---|---|
| Robust (paper) | 0.300 / 0.000 / 0.533 / 0.933 | 0.467 / 0.200 / 1.000 / 1.000 |
| N-Sigma | 0.133 / 0.000 / 0.200 / 0.733 | 0.267 / 0.133 / 0.800 / 1.000 |
| PageRank (graph) | 0.100 / 0.000 / 0.000 / 0.267 | 0.400 / 0.000 / 0.000 / 0.800 |
| CIRCA (causal) | 0.267 / 0.067 / 0.333 / 0.800 | 0.467 / 0.200 / 0.600 / 1.000 |
| CIRCA, RCAEval defaults | 0.200 / 0.067 / 0.200 / 0.867 | 0.500 / 0.133 / 0.800 / 1.000 |
| RCD (causal) | 0.263 / 0.020 / 0.180 / 0.667 | 0.530 / 0.213 / 0.407 / 0.960 |
| Random ranking | 0.372 / 0.086 / 0.486 / 0.947 | 0.571 / 0.238 / 0.833 / 1.000 |

Runtime per case (s, mean): Robust (paper) 0.02, N-Sigma 0.01, PageRank (graph) 0.02, CIRCA (causal) 0.81, CIRCA, RCAEval defaults 0.72, RCD (causal) 4.53; bocpd 0.16.

## Collapse per ranker: single-fault AC@1 (paired subset, 80 cases) vs concurrent AC@2 (28 cases)

Skill = (AC − AC_random)/(1 − AC_random): 0 = chance level, 1 = perfect, < 0 = below chance; the two settings have very different chance levels, so skill is the like-for-like comparison.

| Ranker | single AC@1 | single skill | concurrent AC@2 | concurrent skill | concurrent Both@2 |
|---|---|---|---|---|---|
| Robust (paper) | 0.762 | +0.74 | 0.383 | -0.17 | 0.100 |
| N-Sigma | 0.700 | +0.67 | 0.200 | -0.51 | 0.067 |
| PageRank (graph) | 0.075 | -0.02 | 0.250 | -0.42 | 0.000 |
| CIRCA (causal) | 0.550 | +0.50 | 0.367 | -0.20 | 0.133 |
| RCD (causal) | 0.237 | +0.16 | 0.397 | -0.14 | 0.117 |
| Random ranking | 0.095 | +0.00 | 0.472 | +0.00 | 0.162 |

## Single fault — all 200 cases

| Ranker | n | AC@1 [95% CI] | AC@3 | AC@5 | Boutique AC@1 | Sock Shop AC@1 | stage: kept one group | stage: hit |
|---|---|---|---|---|---|---|---|---|
| Robust (paper) | 200 | 0.775 [0.71, 0.83] | 0.935 | 0.970 | 0.700 | 0.850 | 0.910 | 0.740 |
| N-Sigma | 200 | 0.605 [0.53, 0.67] | 0.860 | 0.910 | 0.520 | 0.690 | 0.910 | 0.590 |
| PageRank (graph) | 200 | 0.105 [0.07, 0.16] | 0.155 | 0.160 | 0.100 | 0.110 | 0.910 | 0.150 |
| CIRCA (causal) | 80 | 0.550 [0.43, 0.66] | 0.875 | 0.925 | 0.375 | 0.725 | 0.938 | 0.487 |
| RCD (causal) | 80 | 0.237 [0.15, 0.35] | 0.425 | 0.487 | 0.150 | 0.325 | 1.000 | 0.225 |
| Random ranking | 200 | 0.095 | 0.264 | 0.406 | 0.092 | 0.099 | – | – |

## Single fault — paired subset, 80 cases (reps 1,2 of every service x fault)

| Ranker | n | AC@1 [95% CI] | AC@3 | AC@5 | Boutique AC@1 | Sock Shop AC@1 | stage: kept one group | stage: hit |
|---|---|---|---|---|---|---|---|---|
| Robust (paper) | 80 | 0.762 [0.65, 0.85] | 0.925 | 0.950 | 0.650 | 0.875 | 0.938 | 0.713 |
| N-Sigma | 80 | 0.700 [0.59, 0.80] | 0.887 | 0.912 | 0.575 | 0.825 | 0.938 | 0.650 |
| PageRank (graph) | 80 | 0.075 [0.03, 0.16] | 0.138 | 0.138 | 0.050 | 0.100 | 0.938 | 0.113 |
| CIRCA (causal) | 80 | 0.550 [0.43, 0.66] | 0.875 | 0.925 | 0.375 | 0.725 | 0.938 | 0.487 |
| RCD (causal) | 80 | 0.237 [0.15, 0.35] | 0.425 | 0.487 | 0.150 | 0.325 | 1.000 | 0.225 |
| Random ranking | 80 | 0.095 | 0.264 | 0.406 | 0.091 | 0.099 | – | – |
