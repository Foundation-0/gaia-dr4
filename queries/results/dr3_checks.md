# What the DR3 stand-in queries returned

Run on the live Gaia archive (anonymous, synchronous queries). Dates are in `run_log.tsv`. The full row lists are in `data/full/` and are not committed; the first 20 rows of each are in `out/`.

## Row counts

| query | rows returned | count value | date |
|---|---|---|---|
| eb_by_source_ids | 5 |  | 2026-10-27 |
| eb_count_all | 1 | 2184477 | 2026-10-27 |
| eb_count_long_period | 1 | 2588 | 2026-10-27 |
| eb_count_long_period_bcut | 1 | 86 | 2026-10-27 |
| eb_long_period | 2588 |  | 2026-10-27 |
| eb_long_period_bcut | 86 |  | 2026-10-27 |
| eb_missing_from_gaia_source | 1 | 0 | 2026-10-27 |
| eb_summary_long_period_bmag | 18 |  | 2026-10-27 |
| eb_summary_long_period_gmag | 15 |  | 2026-10-27 |
| eb_summary_long_period_model_type | 6 |  | 2026-10-27 |
| eb_summary_period | 15 |  | 2026-10-27 |
| flags_in_cone | 2 |  | 2026-10-27 |
| pt_by_source_ids | 5 |  | 2026-10-27 |
| pt_candidates | 214 |  | 2026-10-27 |
| pt_candidates_neighbours | 218 |  | 2026-10-27 |
| pt_count_all | 1 | 214 | 2026-10-27 |
| pt_summary_period | 9 |  | 2026-10-27 |

## Checks on the stand-in tables

- `vari_eclipsing_binary.reference_time` ranges from 1723.4 to 2682.0. Gaia DR3 covers 25 Jul 2014 to 28 May 2017, which is 1666 to 2704 on the scale BJD(TCB) minus 2455197.5. The values fit that scale, which supports the zero point the DR4 data model states.
- `frequency` ranges from 0.00147 to 5.00 per day, so periods run from 0.20 to 679 days.

- `vari_planetary_transit.transit_reference_time` ranges from 1967.3 to 2412.6 (same scale, inside the DR3 span). `transit_period` ranges from 0.51 to 32.9 days.
- `vari_planetary_transit` and `vari_planetary_transit_13june2022` both have 214 rows. Joined on source_id, 214 rows differ in period or reference time, so the second table is a different solution of the same stars. The stand-in uses the table without a date in its name.

## Eclipsing binaries by period (all DR3 rows)

| period range (days) | log10 period, lower edge | stars |
|---|---|---|
| 0.1778 to 0.3162 | -0.75 | 425313 |
| 0.3162 to 0.5623 | -0.50 | 766097 |
| 0.5623 to 1 | -0.25 | 318284 |
| 1 to 1.778 | 0.00 | 223519 |
| 1.778 to 3.162 | 0.25 | 167253 |
| 3.162 to 5.623 | 0.50 | 115566 |
| 5.623 to 10 | 0.75 | 71854 |
| 10 to 17.78 | 1.00 | 48277 |
| 17.78 to 31.62 | 1.25 | 29236 |
| 31.62 to 56.23 | 1.50 | 13445 |
| 56.23 to 100 | 1.75 | 3045 |
| 100 to 177.8 | 2.00 | 1985 |
| 177.8 to 316.2 | 2.25 | 449 |
| 316.2 to 562.3 | 2.50 | 145 |
| 562.3 to 1000 | 2.75 | 9 |

Total 2184477. The bin edges are quarter-decades of log10(period), so the bins are not round numbers of days.

## Long-period eclipsing binaries (period over 100 days): 2588 stars

Period: median 121 d, 90th percentile 236 d, longest 679 d. Stars over 200 d: 337. Over 400 d: 41.

Model types: ELLIPSOIDAL 82, ONEGAUSSIAN 75, ONEGAUSSIAN_WITH_ELLIPSOIDAL 92, TWOGAUSSIANS 2037, TWOGAUSSIANS_WITH_ELLIPSOIDAL_ON_ECLIPSE1 152, TWOGAUSSIANS_WITH_ELLIPSOIDAL_ON_ECLIPSE2 150.

### Magnitude of G (mean, from gaia_source)

| G | stars |
|---|---|
| 6 to 7 | 1 |
| 7 to 8 | 3 |
| 8 to 9 | 4 |
| 9 to 10 | 9 |
| 10 to 11 | 19 |
| 11 to 12 | 22 |
| 12 to 13 | 33 |
| 13 to 14 | 44 |
| 14 to 15 | 102 |
| 15 to 16 | 168 |
| 16 to 17 | 226 |
| 17 to 18 | 409 |
| 18 to 19 | 864 |
| 19 to 20 | 677 |
| 20 to 21 | 7 |

Brighter than G = 13.5: 107 stars. Brighter than G = 12: 58. Brightest G: 6.97.

### Estimated B (published chain, README.md)

| estimated B | stars |
|---|---|
| 7 to 8 | 2 |
| 8 to 9 | 2 |
| 9 to 10 | 3 |
| 10 to 11 | 10 |
| 11 to 12 | 22 |
| 12 to 13 | 18 |
| 13 to 14 | 32 |
| 14 to 15 | 45 |
| 15 to 16 | 74 |
| 16 to 17 | 154 |
| 17 to 18 | 168 |
| 18 to 19 | 327 |
| 19 to 20 | 574 |
| 20 to 21 | 650 |
| 21 to 22 | 341 |
| 22 to 23 | 112 |
| 23 to 24 | 1 |
| no BP-RP | 53 |

Stars that pass the B cut (ADQL in `eb_long_period_bcut.adql`): **86**. The count query `eb_count_long_period_bcut` gave 86.
Of them, BP-RP below 2.0: 86. From 2.0 to 2.5: 0. 2.5 and above: 0. No BP-RP: 0.

### Eclipse depth and model type among the stars that pass the B cut

Primary eclipse at least 0.3 mag deep (G): 58 of 86. At least 0.5 mag: 40. No eclipse phase (NaN): 4. Harvard plates only show eclipses deeper than about 0.3 to 0.5 mag (astronomy report in `notes/reports/`).

Model types among them: ELLIPSOIDAL 4, ONEGAUSSIAN_WITH_ELLIPSOIDAL 8, TWOGAUSSIANS 48, TWOGAUSSIANS_WITH_ELLIPSOIDAL_ON_ECLIPSE1 10, TWOGAUSSIANS_WITH_ELLIPSOIDAL_ON_ECLIPSE2 16.

### Can an eclipse time be carried back to the Harvard plates?

The error on the phase of an eclipse after dt days is about dt times `frequency_error`, in cycles. dt is counted from each star's own `reference_time` back to 1 January of the plate year. This uses the formal error only. It ignores aliasing, which makes it a lower bound.
A phase error well below 0.1 cycle is needed to say where an eclipse fell.

| year | days back: median (range) | median phase error, all (cycles) | all with error < 0.1 | of | median, B-cut stars | B-cut with error < 0.1 | of |
|---|---|---|---|---|---|---|---|
| 1989 | 9981 (9462 to 10352) | 0.28 | 562 | 2588 | 0.20 | 28 | 86 |
| 1950 | 24226 (23707 to 24597) | 0.68 | 344 | 2588 | 0.50 | 17 | 86 |
| 1890 | 46140 (45621 to 46511) | 1.29 | 258 | 2588 | 0.95 | 11 | 86 |

### Mean G against the model's out-of-eclipse level

`phot_g_mean_mag` minus `geom_model_reference_level`, 2588 stars: 5th percentile +0.000, median +0.045, 95th percentile +0.216 mag. A positive value means the mean is fainter than the out-of-eclipse level. Cut margins in README.md are larger than this.

## Planetary-transit table

| period (days) | candidates | mean depth (mmag) | mean duration (d) | fewest in-transit obs | most |
|---|---|---|---|---|---|
| 0.32 to 0.56 | 15 | 13.3 | 0.050 | 3 | 35 |
| 0.56 to 1.00 | 66 | 12.4 | 0.062 | 3 | 45 |
| 1.00 to 1.78 | 55 | 13.8 | 0.096 | 4 | 35 |
| 1.78 to 3.16 | 40 | 15.4 | 0.119 | 3 | 34 |
| 3.16 to 5.62 | 21 | 16.3 | 0.153 | 4 | 25 |
| 5.62 to 10.00 | 13 | 19.0 | 0.188 | 6 | 23 |
| 10.00 to 17.78 | 2 | 8.2 | 0.308 | 14 | 26 |
| 17.78 to 31.62 | 1 | 14.4 | 0.261 | 14 | 14 |
| 31.62 to 56.23 | 1 | 13.1 | 0.125 | 3 | 3 |

Candidates: 214. With a gaia_source row: 214. The neighbourhood stand-in (DR3 to DR2 IDs) returned 218 rows for 214 distinct candidates.

There is no TESS cross-match table in the Gaia archive for DR3 (checked in `TAP_SCHEMA.tables` on 27 Oct 2026) and none in the draft DR4 data model (searched for TESS, TIC).

## Cone search stand-in (`flags_in_cone`)

Circle of 0.0175 degrees (63 arcseconds, 3 TESS pixels) around the first long-period binary: 2 rows. The target has eb_frequency 0.006662 and flag VARIABLE.

## First rows

`out/eb_long_period_top20.csv`, `out/pt_candidates_top20.csv` and the other files in `out/` hold the first rows of each query.

