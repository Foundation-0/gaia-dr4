# B conversion check: results

Test sample: 200 stars from APASS DR9 (Johnson B, V) matched to Gaia DR3, G between 10.0 and 14.0, 8 colour bins of 25 stars.

Differences are estimate minus APASS, in magnitudes. `robust` is 1.4826 x the median absolute deviation, which ignores a few wild stars. A positive difference means the estimate is fainter than APASS. 'Most too faint' and 'most too bright' are the largest differences in each direction.


## V from Riello et al. 2021 (G - V relation)

| BP-RP | n | bias | median | std | robust | most too faint | most too bright |
|---|---|---|---|---|---|---|---|
| -0.5 to 0.3 | 25 | +0.017 | +0.024 | 0.027 | 0.019 | +0.06 | -0.04 |
| 0.3 to 0.6 | 25 | +0.014 | +0.012 | 0.031 | 0.022 | +0.12 | -0.03 |
| 0.6 to 0.9 | 25 | +0.002 | -0.003 | 0.031 | 0.023 | +0.10 | -0.05 |
| 0.9 to 1.2 | 25 | +0.013 | +0.012 | 0.032 | 0.034 | +0.07 | -0.05 |
| 1.2 to 1.6 | 25 | +0.028 | +0.029 | 0.038 | 0.036 | +0.11 | -0.05 |
| 1.6 to 2.0 | 25 | +0.016 | +0.016 | 0.031 | 0.029 | +0.08 | -0.05 |
| 2.0 to 2.5 | 25 | +0.008 | +0.005 | 0.030 | 0.028 | +0.06 | -0.04 |
| 2.5 to 5.0 | 25 | +0.014 | -0.008 | 0.084 | 0.045 | +0.38 | -0.05 |
| **all, BP-RP below 2.0** | 150 | +0.015 | +0.014 | 0.032 | 0.030 | +0.12 | -0.05 |
| **all, BP-RP 2.0 to 2.5** | 25 | +0.008 | +0.005 | 0.030 | 0.028 | +0.06 | -0.04 |
| **all, BP-RP 2.5 and above** | 25 | +0.014 | -0.008 | 0.084 | 0.045 | +0.38 | -0.05 |
| **all test stars** | 200 | +0.014 | +0.012 | 0.042 | 0.035 | +0.38 | -0.05 |

## B, method A (published chain)

| BP-RP | n | bias | median | std | robust | most too faint | most too bright |
|---|---|---|---|---|---|---|---|
| -0.5 to 0.3 | 25 | -0.005 | -0.005 | 0.036 | 0.031 | +0.08 | -0.08 |
| 0.3 to 0.6 | 25 | -0.018 | -0.020 | 0.043 | 0.033 | +0.06 | -0.16 |
| 0.6 to 0.9 | 25 | -0.027 | -0.027 | 0.029 | 0.015 | +0.07 | -0.08 |
| 0.9 to 1.2 | 25 | +0.019 | +0.018 | 0.036 | 0.030 | +0.10 | -0.06 |
| 1.2 to 1.6 | 25 | +0.054 | +0.049 | 0.051 | 0.038 | +0.18 | -0.04 |
| 1.6 to 2.0 | 25 | +0.060 | +0.049 | 0.059 | 0.060 | +0.17 | -0.03 |
| 2.0 to 2.5 | 25 | -0.065 | -0.063 | 0.142 | 0.066 | +0.23 | -0.47 |
| 2.5 to 5.0 | 25 | -0.572 | -0.580 | 0.503 | 0.421 | +0.60 | -1.46 |
| **all, BP-RP below 2.0** | 150 | +0.014 | +0.008 | 0.054 | 0.050 | +0.18 | -0.16 |
| **all, BP-RP 2.0 to 2.5** | 25 | -0.065 | -0.063 | 0.142 | 0.066 | +0.23 | -0.47 |
| **all, BP-RP 2.5 and above** | 25 | -0.572 | -0.580 | 0.503 | 0.421 | +0.60 | -1.46 |
| **all test stars** | 200 | -0.069 | -0.006 | 0.269 | 0.056 | +0.60 | -1.46 |

## B, method B (cubic B - V fit to APASS, other stars)

| BP-RP | n | bias | median | std | robust | most too faint | most too bright |
|---|---|---|---|---|---|---|---|
| -0.5 to 0.3 | 25 | +0.001 | +0.001 | 0.035 | 0.020 | +0.09 | -0.09 |
| 0.3 to 0.6 | 25 | +0.010 | +0.013 | 0.043 | 0.037 | +0.10 | -0.14 |
| 0.6 to 0.9 | 25 | +0.003 | +0.002 | 0.029 | 0.012 | +0.10 | -0.06 |
| 0.9 to 1.2 | 25 | +0.020 | +0.020 | 0.038 | 0.020 | +0.09 | -0.08 |
| 1.2 to 1.6 | 25 | +0.006 | +0.009 | 0.050 | 0.052 | +0.12 | -0.11 |
| 1.6 to 2.0 | 25 | -0.013 | -0.030 | 0.059 | 0.057 | +0.11 | -0.11 |
| 2.0 to 2.5 | 25 | -0.018 | -0.041 | 0.122 | 0.086 | +0.25 | -0.26 |
| 2.5 to 5.0 | 25 | -0.061 | -0.184 | 0.353 | 0.352 | +0.54 | -0.61 |
| **all, BP-RP below 2.0** | 150 | +0.004 | +0.004 | 0.044 | 0.036 | +0.12 | -0.14 |
| **all, BP-RP 2.0 to 2.5** | 25 | -0.018 | -0.041 | 0.122 | 0.086 | +0.25 | -0.26 |
| **all, BP-RP 2.5 and above** | 25 | -0.061 | -0.184 | 0.353 | 0.352 | +0.54 | -0.61 |
| **all test stars** | 200 | -0.007 | +0.002 | 0.137 | 0.045 | +0.54 | -0.61 |

## B - V, method A

| BP-RP | n | bias | median | std | robust | most too faint | most too bright |
|---|---|---|---|---|---|---|---|
| -0.5 to 0.3 | 25 | -0.022 | -0.024 | 0.028 | 0.027 | +0.03 | -0.08 |
| 0.3 to 0.6 | 25 | -0.032 | -0.033 | 0.047 | 0.033 | +0.03 | -0.20 |
| 0.6 to 0.9 | 25 | -0.029 | -0.025 | 0.035 | 0.027 | +0.03 | -0.15 |
| 0.9 to 1.2 | 25 | +0.006 | +0.006 | 0.053 | 0.055 | +0.09 | -0.14 |
| 1.2 to 1.6 | 25 | +0.025 | +0.036 | 0.055 | 0.050 | +0.13 | -0.09 |
| 1.6 to 2.0 | 25 | +0.044 | +0.028 | 0.075 | 0.056 | +0.19 | -0.09 |
| 2.0 to 2.5 | 25 | -0.073 | -0.060 | 0.138 | 0.081 | +0.25 | -0.44 |
| 2.5 to 5.0 | 25 | -0.586 | -0.547 | 0.458 | 0.449 | +0.22 | -1.44 |
| **all, BP-RP below 2.0** | 150 | -0.001 | -0.010 | 0.058 | 0.048 | +0.19 | -0.20 |
| **all, BP-RP 2.0 to 2.5** | 25 | -0.073 | -0.060 | 0.138 | 0.081 | +0.25 | -0.44 |
| **all, BP-RP 2.5 and above** | 25 | -0.586 | -0.547 | 0.458 | 0.449 | +0.22 | -1.44 |
| **all test stars** | 200 | -0.083 | -0.022 | 0.259 | 0.056 | +0.25 | -1.44 |

## B - V, method B

| BP-RP | n | bias | median | std | robust | most too faint | most too bright |
|---|---|---|---|---|---|---|---|
| -0.5 to 0.3 | 25 | -0.017 | -0.018 | 0.028 | 0.020 | +0.03 | -0.07 |
| 0.3 to 0.6 | 25 | -0.004 | +0.002 | 0.048 | 0.040 | +0.06 | -0.17 |
| 0.6 to 0.9 | 25 | +0.001 | +0.002 | 0.036 | 0.025 | +0.07 | -0.13 |
| 0.9 to 1.2 | 25 | +0.007 | +0.005 | 0.057 | 0.057 | +0.11 | -0.16 |
| 1.2 to 1.6 | 25 | -0.023 | -0.025 | 0.055 | 0.050 | +0.09 | -0.14 |
| 1.6 to 2.0 | 25 | -0.029 | -0.046 | 0.075 | 0.061 | +0.12 | -0.17 |
| 2.0 to 2.5 | 25 | -0.026 | -0.050 | 0.119 | 0.098 | +0.26 | -0.23 |
| 2.5 to 5.0 | 25 | -0.075 | -0.151 | 0.373 | 0.360 | +0.51 | -0.99 |
| **all, BP-RP below 2.0** | 150 | -0.011 | -0.013 | 0.053 | 0.049 | +0.12 | -0.17 |
| **all, BP-RP 2.0 to 2.5** | 25 | -0.026 | -0.050 | 0.119 | 0.098 | +0.26 | -0.23 |
| **all, BP-RP 2.5 and above** | 25 | -0.075 | -0.151 | 0.373 | 0.360 | +0.51 | -0.99 |
| **all test stars** | 200 | -0.021 | -0.017 | 0.145 | 0.060 | +0.51 | -0.99 |

## The proposed cut (method A with margins, see README.md)

Share of stars with APASS B below 13.5 that the cut keeps, and how many fainter stars it lets in. 'test' stars chose the margins. 'train' stars are an independent check.

| BP-RP | role | APASS B < 13.5: kept | share | APASS B >= 13.5: let in |
|---|---|---|---|---|
| BP-RP below 2.0 | test | 77 of 77 | 100% | 7 of 73 |
| BP-RP below 2.0 | train | 64 of 64 | 100% | 16 of 86 |
| BP-RP 2.0 to 2.5 | test | 0 of 0 | 0% | 0 of 25 |
| BP-RP 2.0 to 2.5 | train | 4 of 4 | 100% | 6 of 21 |
| BP-RP 2.5 and above | test | 1 of 1 | 100% | 5 of 24 |
| BP-RP 2.5 and above | train | 1 of 1 | 100% | 7 of 24 |
| all colours | test | 78 of 78 | 100% | 12 of 122 |
| all colours | train | 69 of 69 | 100% | 29 of 131 |

## Bright red stars (G 8.0 to 11.0), a check of the red end

| BP-RP | n | B - G, smallest | B - G, median | method A bias (B) | method A std | APASS B < 13.5: kept by cut |
|---|---|---|---|---|---|---|
| 2.0 to 2.5 | 50 | 2.28 | 2.59 | -0.02 | 0.15 | 43 of 43 |
| 2.5 to 5.0 | 50 | 2.71 | 3.45 | -0.51 | 0.59 | 15 of 15 |

Smallest B - G over all 100 sample stars with BP-RP 2.5 and above (main sample and bright red set): 2.71. Smallest in the main sample alone (50 stars): 2.74. This sets MIN_B_MINUS_G_VERY_RED in b_conversion.py.
