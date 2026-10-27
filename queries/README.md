# Queries for Gaia DR4: eclipsing binaries and planetary-transit candidates

This folder holds ready-to-run queries for two tables of Gaia's fourth data release (DR4):
`vari_eclipsing_binary` (stars that dim when one star passes in front of the other, 2,392,500 rows) and
`vari_planetary_transit` (stars that dim a little when a planet may pass in front, 1,007 rows). The queries are
written in ADQL, the query language of the Gaia archive, a form of SQL. Each query has a twin that runs today on the
previous release, DR3. This is task [#4](https://github.com/Foundation-0/gaia-dr4/issues/4).

**Status: claimed.** The DR3 twins ran on the live archive on 27 Oct 2026 and gave the same answers on a second run. No query has run on
DR4, which does not exist yet. The DR4 names come from ESA's draft data model of 26 June 2026 and may change.

| Date | What happens |
|---|---|
| Wednesday 25 November 2026, 12:00 CET | The Gaia ESA Archive goes down until DR4. |
| Wednesday 2 December 2026, about 12:00 CET | DR4 is released and the archive reopens. |

## Reproduce

Python 3 with the standard library only. Every command is run from this folder. Answers are cached under `data/`
(not committed), so a re-run that finds them makes no request.

The draft DR4 data model is a PDF inside a zip. To fetch and read it (`pdftotext` is from the poppler tools, not Python):

```sh
mkdir -p data/datamodel_zip data/datamodel
curl -sS -A "Foundation0-gaia-dr4/0.1 (+https://github.com/Foundation-0/gaia-dr4)" \
  -o data/datamodel_zip/gaia-dr4-prerelease-draft-data-model_2026-06-26.zip \
  https://anonftp.cosmos.esa.int/pub/GAIA_PUBLIC_DATA/Gaia_DR4/dr4-prerelease/gaia-dr4-prerelease-draft-data-model_2026-06-26.zip
python3 -I -c "import zipfile; zipfile.ZipFile('data/datamodel_zip/gaia-dr4-prerelease-draft-data-model_2026-06-26.zip').extract('gaia-dr4-prerelease-draft-data-model.pdf', 'data/datamodel')"
pdftotext -layout data/datamodel/gaia-dr4-prerelease-draft-data-model.pdf data/datamodel/model.txt
python3 -I datamodel_columns.py data/datamodel/model.txt datamodel/dr4_draft_columns.tsv
python3 -I fetch_schema.py                   # DR3 column lists from the live archive (2 requests)
python3 -I build_column_map.py               # column_map.tsv
```

The rest:

```sh
python3 -m unittest discover                 # 50 tests, no network
python3 -I run_dr3_checks.py                 # run the 17 DR3 stand-ins, anonymous, one request at a time
python3 -I run_dr3_checks.py --verify        # ask again, bypass the cache, compare answers (all 21 were the same)
python3 -I check_columns.py dr3 --live       # every table and column in dr3/ exists in the live archive
python3 -I check_columns.py dr4              # every name in dr4/ exists in the draft DR4 data model
python3 -I analyze_dr3.py                    # writes results/dr3_checks.md (needs the answers from run_dr3_checks.py)
python3 -I check_ephemeris.py                # the eclipse-time check on 10 stars (10 DataLink requests, same need)
python3 -I validate_b.py sample              # the B-magnitude sample (10 requests), then: fit, report
python3 -I build_queries.py                  # rewrites dr4/, dr3/ and dr4_only/ (after run_dr3_checks.py)
```

`-I` makes Python ignore the current folder and environment, as asked for code that reads downloaded files.
To make the DR3 twin of one DR4 query: `python3 -I make_standin.py dr4/eb_long_period.adql`.

## Results on DR3 (27 Oct 2026)

Every number below comes from a query in `dr3/`. Counts and run times are in [results/run_log.tsv](results/run_log.tsv).
More tables are in [results/dr3_checks.md](results/dr3_checks.md). The first 20 rows of each row query are in `results/out/`.

| Question | Query | DR3 answer |
|---|---|---|
| Rows in `vari_eclipsing_binary` | `eb_count_all` | 2,184,477 (matches ESA's DR3 count) |
| Eclipsing binaries with a period over 100 days | `eb_count_long_period` | **2,588** |
| Of those, passing the B cut (see below) | `eb_count_long_period_bcut` | **86** (the row query `eb_long_period_bcut` returns the same 86) |
| Of those, missing from `gaia_source` | `eb_missing_from_gaia_source` | 0 |
| Rows in `vari_planetary_transit` | `pt_count_all` | 214 (DR4: 1,007) |

**Period.** 2,588 of 2,184,477 DR3 binaries (0.12%) have a period over 100 days. By range: 100 to 178 days 1,985 stars,
178 to 316 days 449, 316 to 562 days 145, 562 to 1000 days 9. The longest is 679 days. DR3 used 34 months of data (25 Jul 2014 to 28 May 2017, [Gaia DR3 page](https://www.cosmos.esa.int/web/gaia/dr3)), so a
period of 679 days is about 1.5 cycles. DR4 uses 66 months.

**Brightness (G, Gaia's broad-band magnitude, mean over the observations).** Of the 2,588 stars: 17 are brighter than G = 10,
74 are between 10 and 13, 44 between 13 and 14, 102 between 14 and 15 and 2,351 are fainter than 15. 107 are brighter than
G = 13.5. The brightest is G = 6.97. Full table: `eb_summary_long_period_gmag`.

**After the B cut (86 stars).** 58 have a primary eclipse at least 0.3 mag deep in G and 40 at least 0.5 mag. The astronomy report in
`notes/reports/` says Harvard plates only show eclipses deeper than about 0.3 to 0.5 mag. Four of the 86 have no eclipse in
their model (model type ELLIPSOIDAL, no eclipse phase). The count in DR4 may differ: the table has about 10% more rows and the data
span almost twice as long. That cannot be tested before release.

**Model types** among the 2,588: TWOGAUSSIANS 2,037, ONEGAUSSIAN_WITH_ELLIPSOIDAL 92, ELLIPSOIDAL 82, ONEGAUSSIAN 75,
and 302 more with a Gaussian plus an ellipsoidal term. Two Gaussians means two eclipses per orbit are modelled.

**Can an eclipse time be carried back to the Harvard plates (1890 to 1989)?** Only with difficulty on DR3 data. The error on the phase of an
eclipse after `dt` days is about `dt * frequency_error` cycles. This uses the formal error and ignores aliasing, so it is a lower bound.
Carried back to 1950 (24,106 days), only 345 of the 2,588 stars (17 of the 86 after the B cut) have a phase error under
0.1 cycle. Back to 1890 it is 258 (11 of 86). The median error at 1950 is 0.67 cycle. DR4's longer span should shrink these errors.
By how much is not known until DR4.

**Do the table's columns predict the eclipse in the star's own light curve?** On the 10 brightest DR3 stars that meet fixed rules
([results/ephemeris_check.md](results/ephemeris_check.md)), the predicted primary-eclipse window is among the faintest 20% of
50 windows for 8 stars with the table's phase and for 1 star with the sign reversed (chance: 2.2). The median rank is 6 against 25. This supports
the convention below, including the sign. It is a weak test: each window holds few points and the dimming rests on one or two visits.

**Transit table (DR3, 214 rows).** Periods run from 0.51 to 32.9 days. 66 of the 214 are between 0.6 and 1.0 day.
Every candidate has a `gaia_source` row. The neighbourhood stand-in returns 218 rows for 214 candidates, so some have two.

## The queries

`dr4/` holds the queries with DR4 names. `dr3/` holds the same queries with DR3 names. They are not edited by hand: `build_queries.py`
writes the DR4 text and `make_standin.py` derives the DR3 text from it. Each header lists the question served, the DR3 tables
that stood in, the DR4 columns relied on, the last error-free DR3 run with its row count, and what cannot be tested before release.

| File (`.adql`) | Serves | DR3 rows |
|---|---|---|
| `eb_count_all` | row count of the table | 1 |
| `eb_count_long_period` | question C: period over 100 days (`frequency < 0.01`) | 1 |
| `eb_count_long_period_bcut` | question C: the same with the B cut | 1 |
| `eb_missing_from_gaia_source` | question C: long-period binaries with no `gaia_source` row | 1 |
| `eb_summary_period` | binaries per quarter-decade of period | 15 |
| `eb_summary_long_period_model_type` | long-period binaries per model type | 6 |
| `eb_summary_long_period_gmag` | long-period binaries per G magnitude | 15 |
| `eb_summary_long_period_bmag` | long-period binaries per estimated B magnitude | 18 |
| `eb_long_period` | question C: the list, with everything needed to predict eclipse times, and `gaia_source` position, parallax, magnitudes, colour, and estimated V and B | 2,588 |
| `eb_long_period_bcut` | question C: the same list with the B cut | 86 |
| `eb_by_source_ids` | the same columns for a list of source IDs (template) | 5 |
| `pt_count_all` | row count of the transit table | 1 |
| `pt_summary_period` | transit candidates per quarter-decade of period | 9 |
| `pt_candidates` | the 1,007 candidates with transit time, period, duration, depth, and `gaia_source` columns | 214 |
| `pt_candidates_neighbours` | the same, with the table that links IDs between releases | 218 |
| `pt_by_source_ids` | the same columns for a list of source IDs (template) | 5 |
| `flags_in_cone` | question B: every source in a circle (a TESS aperture) with its variability flag and its binary and transit rows (template) | 2 |
| `dr4_only/eb_long_period_all_source` | question C fallback, DR4 only: position and magnitudes from `all_source_astrometry` and `all_source_photometry` | not testable |

Templates contain `@...@` words (`@SOURCE_IDS@`, `@RA@`, `@DEC@`, `@RADIUS_DEG@`) to fill in. `run_dr3_checks.py` fills them from earlier answers.

**Predicting times.** The table gives times as days of BJD(TCB) minus 2455197.5 (Barycentric Julian Date in Barycentric Coordinate Time).
Add 2455197.5 to get a Julian Date.

- Binary: the phase of a time `t` is `frac((t - reference_time) * frequency)`. A primary eclipse is at
  `reference_time + (derived_primary_ecl_phase + n) / frequency` for any whole number `n`. The period in days is `1 / frequency`.
  `derived_primary_ecl_duration` is a fraction of the period, not days.
  The DR4 data model says the phases are measured from `reference_time`. The check above supports this for DR3.
- Transit: transit `n` is at `transit_reference_time + n * transit_period`. The data model says an observation at time `t` is inside a transit when
  `abs(mod(t - T0 + P/2, P) - P/2) < w/2` with `w = transit_duration` in days. The table has no error on the period.

**No TESS cross-match table.** None exists for DR3 in the archive (no table name contains `tess` in the 248 tables of [results/archive_tables.csv](results/archive_tables.csv), 27 Oct 2026) or in the draft DR4 data model
(searched for TESS and TIC). The route to TESS is by ID: the TESS Input Catalog lists Gaia DR2 IDs, so a DR4 star needs DR4 to DR3
(`dr3_neighbourhood`, new in DR4) and DR3 to DR2 (`dr2_neighbourhood`). `pt_candidates_neighbours` tests the join pattern with the
DR3 to DR2 table as the stand-in. The step to a TIC number belongs to the tic-to-gaia task.

## The column map

[column_map.tsv](column_map.tsv) has one line per table or column: the DR4 draft name, the DR3 name, units, types, whether it is `same`,
`renamed`, `dr4_only` or `dr3_only`, and notes. `make_standin.py` reads it. Summary:

- `vari_planetary_transit`: all 7 columns have the same names in DR3 and DR4. `num_in_transit` is a narrower integer type in DR4.
- `vari_eclipsing_binary`: all 39 DR3 columns exist in DR4 with the same names. DR4 adds 11:
  `frequency_rv_consistency_flag`, `sample_classification`, `bp_usable`, `rp_usable`, `delta_global_ranking_bp_min_g`,
  `delta_global_ranking_rp_min_g`, `g_skewness`, `g_signal_to_noise`, `g_median`, `g_num_obs` and `classification_score`.
  The queries use four of them on lines tagged `-- DR4ONLY`, which the stand-in drops.
- `gaia_source`: 87 columns share a name. The queries use 14 of them, two DR4-only ones (`g_photometry_origin`, `colour_origin`) and one rename, `teff` (DR4) for `teff_gspphot` (DR3), whose meaning
  differs (DR4 takes it from the module named in `ap_origin`). DR3 columns missing from DR4 `gaia_source` include `phot_bp_rp_excess_factor`,
  `bp_g`, `g_rp`, `non_single_star`, `duplicated_source` and `has_epoch_photometry`. The draft puts some of them in `all_source_flags`
  and `all_source_astrometry`.
- `dr3_neighbourhood` (DR4) and `dr2_neighbourhood` (DR3) differ in two column names. Both are renamed in the map, and the two names swap roles.
  The stand-in tool renames them in one pass.
- The DR4 schema name is `gaiadr4`. The draft's own example query uses it (section 7.3). No live archive has confirmed it.
- Units are the same where the draft states them (`day-1` is `d**-1`). The draft gives the zero point of `reference_time`. DR3's schema says only `d`. The DR3 values
  (1723 to 2682) fall inside the DR3 span (25 Jul 2014 to 28 May 2017, which is 1666 to 2704 on that scale), which supports the same zero point.

**DR4 `gaia_source` is smaller in meaning.** The Gaia DR4 page (content table of 14 Sep 2026) says it holds sources "considered to have both
high-quality astrometry and high-quality photometry". A DR4 binary may have no row in it. So the queries use `LEFT OUTER JOIN`, and
`eb_missing_from_gaia_source` counts the binaries without a row. If it is above 0, use `dr4_only/eb_long_period_all_source`.

**DR4 G magnitudes of binaries may come from the binary model.** The draft says the G in `gaia_source` can come from `vari_eclipsing_binary`
(`g_photometry_origin`), and then `phot_g_n_obs` is 0. The draft does not say whether that value is a mean or an out-of-eclipse level.
The queries select `g_photometry_origin`, `colour_origin` and `eb.g_median` (DR4 only) so this can be seen.

## The B magnitude

Gaia does not measure Johnson B. The Harvard plates and DASCH use B-like magnitudes. `b_conversion.py` estimates V and B from Gaia G and the colour BP-RP
(BP and RP are Gaia's blue and red photometers).

**Method A, the published chain** (used by the queries):

1. V = G - f(BP-RP), where `f = -0.02704 + 0.01424 c - 0.2156 c^2 + 0.01426 c^3` and `c = BP-RP`.
   Riello et al. 2021, [A&A 649, A3](https://arxiv.org/abs/2012.01916), Table C.2. Valid for -0.5 < c < 5.0. Published scatter 0.030 mag.
2. The Tycho-2 colour `BT - VT` is `(G - VT) - (G - BT)`, two more relations of the same table, valid for -0.3 < c < 3.0 (scatter 0.054 and 0.071 mag).
3. B - V = 0.850 (BT - VT). ESA SP-1200 (1997), section 2.2, Eq. 2.2.2
   ([ESA document](https://www.cosmos.esa.int/documents/532822/553204/sect2_02.pdf/9f2b5393-bc66-4480-89d2-88200aecf5c8)). ESA states it for
   -0.2 < BT - VT < 1.8, with a systematic error up to 0.05 mag, for unreddened main-sequence stars.
4. B = V + (B - V).

Riello et al. give no direct Johnson B relation, so steps 2 and 3 are needed. The Gaia DR3 documentation has a section on these relations
("Photometric relationships with other photometric systems", 5.5.1 by the page title seen in a search). The page returned HTTP 503 on 27 Oct 2026, twice, so
the coefficients were taken from the paper only. Later work by Pancino et al. 2022 ([arXiv:2205.06186](https://arxiv.org/abs/2205.06186)) was not tried.

**Method B, an APASS fit** (a cross-check, not used by the queries): B - V as a cubic in BP-RP, fitted to 193 of 200 stars with APASS B and V. V as in step 1.

**Validation.** Measured B comes from APASS DR9. It has Johnson B and V magnitudes calibrated to Landolt standards (Henden et al. 2016,
[VizieR II/336](https://cdsarc.cds.unistra.fr/viz-bin/cat/II/336)). The stars were taken from the Gaia archive's copy of APASS and its official cross-match to
DR3. Three stars checked against VizieR itself gave identical B and V.

The sample has 8 colour bins of 25 stars each (200 test stars). In each bin the stars are those with the lowest `random_index` (a fixed pseudo-random number
every Gaia source carries) that meet the filters in `validate_b.py`: G from 10 to 14, one clean APASS neighbour within 1 arcsecond, APASS errors
below 0.06 mag and at least 3 nights. A second set of 25 stars per bin was used only to fit method B and, later, to check the cut. A third set of 100 red stars
(BP-RP from 2.0, G from 8 to 11) checks the red end. All three sets are in [results/b_sample.csv](results/b_sample.csv). The full report is
[results/b_validation.md](results/b_validation.md). Estimate minus APASS, in magnitudes:

| BP-RP | stars | V bias | V scatter | B bias, method A | B scatter, method A | B bias, method B | B scatter, method B |
|---|---|---|---|---|---|---|---|
| below 2.0 | 150 | +0.015 | 0.032 | +0.014 | 0.054 | +0.004 | 0.044 |
| 2.0 to 2.5 | 25 | +0.008 | 0.030 | -0.065 | 0.142 | -0.018 | 0.122 |
| 2.5 and above | 25 | +0.014 | 0.084 | -0.572 | 0.503 | -0.061 | 0.353 |

Scatter is the standard deviation. A positive bias means the estimate is fainter than APASS.
For BP-RP below 2.0 method A is within 0.2 mag of APASS for every test star (largest errors +0.18 and -0.16).

**Where it fails.**

- **BP-RP 2.5 and above (very red stars): method A fails.** It is too bright by 0.57 mag on average and by up to 1.5 mag. The Tycho-based relations stop at 3.0, and ESA's step is stated for BT - VT up to 1.8 and was derived for main-sequence stars.
  Riello's table also marks some of its other relations as valid only for M giants at red colours. Method B is better on average but has a scatter of 0.35 mag. B cannot be
  estimated from G and BP-RP for these stars to better than a few tenths of a magnitude. The cut uses G alone there.
- **BP-RP 2.0 to 2.5: usable with a wide margin.** The scatter is 0.14 mag and the worst error 0.47 mag.
- **Bluer than BP-RP = 0 (hot stars): not tested.** Only one test star is that blue. The polynomials are valid down to -0.3 or -0.5.
- **Brighter than G = 10: not tested** (APASS saturates). The bright red set reaches G = 8.
- **Stars with no BP-RP** get no estimate. The cut keeps them if G is below 13.8.
- **Eclipsing binaries are not ordinary stars.** G is a mean over observations, which includes some eclipse light. In the DR3 list, mean G minus the model's out-of-eclipse level has a median of +0.045 mag and a 95th percentile of +0.216 mag
  (results/dr3_checks.md). `b_mag_estimate_out_of_eclipse` gives B from the out-of-eclipse level. The APASS sample is of ordinary stars.

**The ADQL cut** keeps every star that might truly pass B < 13.5. It adds margins taken from the largest "too faint" errors of method A on the test stars, rounded up:

```
BP-RP below 2.0:       B estimate < 13.5 + 0.25
BP-RP 2.0 to 2.5:      B estimate < 13.5 + 0.50
BP-RP 2.5 and above:   G + 2.5 < 13.5        (the smallest B - G among 100 such stars was 2.71)
no BP-RP:              G - 0.3 < 13.5
```

The text is in `dr4/eb_long_period_bcut.adql`, written by `b_conversion.adql_bcut()`. Python and ADQL forms are tested against each other.
On the 200 other stars (the check set) the cut keeps 69 of 69 stars with APASS B below 13.5 and lets in 29 of 131 fainter ones.
On the 100 bright red stars it keeps 58 of 58. Few red stars with B below 13.5 are in the sample, so the red end rests on those 58 and on the B - G argument.
The margins are choices. A person should confirm them or change `MARGIN_BLUE`, `MARGIN_RED` and the other constants at the top of `b_conversion.py`.

## What was checked, and how

- **DR3 stand-ins run.** All 17 ran on the live archive, anonymously, on 27 Oct 2026, and a second run bypassing the cache gave identical answers for all 21 queries
  (the 4 row queries are run twice, with `TOP 20` and in full).
  Two queries first failed with HTTP 408 (the archive stops a synchronous query after 60 seconds) and were rewritten, which is why `run_log.tsv` has three error lines.
  A `LEFT OUTER JOIN` of all 2.2 million binaries to `gaia_source` is too slow, so `eb_missing_from_gaia_source` covers long periods only. A `LEFT OUTER JOIN` to the
  billion-row neighbourhood table is too slow, so `pt_candidates_neighbours` uses an inner join: a candidate with no neighbour row is left out. Compare its distinct `source_id` with 1,007.
- **DR4 and DR3 queries differ in names only.** `test_queries.py` masks every table and column name and compares the rest of each DR4 and DR3 file (17 pairs). It also
  restores the DR4 names from the DR3 text through the map and compares with the DR4 file.
- **Names exist.** Every DR4 name is in the draft data model's column list (`check_columns.py dr4`) and every DR3 name is in the live archive's `TAP_SCHEMA` (`check_columns.py dr3 --live`).
  The same program with `dr4 --live` on 27 Oct 2026 reported the three DR4 tables as not found, as it should.
- **The draft data model was read as text.** The zip (2.8 MB, one PDF of 1,231 pages) downloaded from the container without trouble.
  `datamodel_columns.py` turns it into [datamodel/dr4_draft_columns.tsv](datamodel/dr4_draft_columns.tsv). The parser reads headings that wrap over lines and drops the PDF's
  "Draft" watermark letters. One heading (`delta_global_ranking_bp_min_g`) had its type on another line and was set by hand. The columns, types, units and
  descriptions for the two tables were read by eye in the PDF text as well.
- **DataLink structure name.** While fetching DR3 epoch photometry the old name `DATA_STRUCTURE=INDIVIDUAL` returned HTTP 500 on 27 Oct 2026 and
  `DATAMODEL_STANDARD` worked. That fits the 14 Oct rename in the scouting notes. The DataLink task (#2) owns the fetcher.
- **Counts agree.** The row count of `eb_long_period` equals `eb_count_long_period`, the B-cut rows equal the B-cut count, and the summary totals equal the table's row count (tests).
- **Facts about DR4** (row counts, 66 months, J2017.5, `gaia_source` contents, the table list) were read on 27 Oct 2026 from the
  [Gaia DR4 page](https://www.cosmos.esa.int/web/gaia/dr4) (content table of 14 Sep 2026).

## Limits

- No query has run on DR4. Nobody else has re-run these queries yet. The same person ran them twice.
- The sample used anonymous synchronous queries only. A logged-in account and asynchronous jobs (for results over the sync row limit or over 60 seconds) were not tried.
- The validation covers G from 8 to 14 and BP-RP mostly from 0. It is for stars that APASS measured well. It says little about hot, very red, or very bright stars.
- The B cut was built from 200 stars, and its margins were then checked on 200 others and 100 red stars. It was not tried on a sample of actual long-period binaries with measured B.
- The ephemeris check is weak (10 stars, few points each). Period aliasing was not tested, and neither was whether the model frequency is the orbital frequency or half of it.
- Tycho-2 (VizieR I/259) was not used. APASS was, because it gives Johnson B directly. The method A chain uses Tycho-2 relations but was not tested against Tycho-2 magnitudes.
- Gaia DR3 documentation could not be read (HTTP 503). The relations come from Riello et al. 2021 only.

## What cannot be tested until DR4 exists

- Whether the DR4 schema is `gaiadr4`, and every DR4 table and column name. Run `check_columns.py dr4 --live` first on release day.
- The row counts (2,392,500 and 1,007) and every DR4 figure: how many binaries have a period over 100 days, their model types, magnitudes and colours.
- Whether DR4's `reference_time` and `transit_reference_time` use the same zero point. A check: DR4's data span 25 Jul 2014 to 20 Jan 2020, which is 1666 to 3671 on that scale.
- Whether the G magnitudes of binaries in DR4 `gaia_source` behave like DR3's, and so whether the B-cut margins hold.
- How many DR4 binaries have no `gaia_source` row, and the `all_source_*` fallback query.
- `dr3_neighbourhood`, and with it the DR3 to DR4 ID step.
- Run time. DR4 `gaia_source` has 2,000,033,276 rows. A join that takes seconds on DR3 may not on release day.
- Whether DR4 periods of long-period binaries are ambiguous. With about two eclipses in 66 months they may be. The astronomy report says ESA states no maximum period (not re-checked).

## Release day, in order

1. `python3 -I check_columns.py dr4 --live` (add `--tap-url` if DR4 is at another address). Fix any missing name in `build_queries.py`, then run `build_queries.py` and the tests.
2. Compare the notes in `column_map.tsv` with the published data model (units, zero points, model types).
3. Run `eb_count_all` and `pt_count_all`. Expect 2,392,500 and 1,007.
4. Run `eb_missing_from_gaia_source`. If above 0, use `dr4_only/eb_long_period_all_source` for the list.
5. Run `eb_long_period_bcut` for question C. Run it as an asynchronous job from an own archive account (5 jobs at once, 50 queued).
   Keep the query text and the run time with the list.
6. Run `pt_candidates` and `pt_candidates_neighbours`, and `flags_in_cone` for each TESS aperture of question B.

## What needs a person

- A person signs before the list from `eb_long_period_bcut` goes to plate-eclipses, and before any count is published.
- A person confirms the B-cut margins, or chooses others.
- Each person who runs queries on release day uses their own archive account. Nothing here uses an account.
- Contact with the Gaia team, ESA, or the authors of the relations needs a person.

## Files

| Path | What |
|---|---|
| `dr4/`, `dr3/`, `dr4_only/` | the queries |
| `column_map.tsv`, `build_column_map.py` | DR4 and DR3 names, units, mismatches |
| `build_queries.py`, `make_standin.py` | write the DR4 files, derive the DR3 files |
| `run_dr3_checks.py`, `check_columns.py`, `analyze_dr3.py`, `check_ephemeris.py` | run and check |
| `b_conversion.py`, `validate_b.py` | the B estimate and its validation |
| `datamodel_columns.py`, `datamodel/dr4_draft_columns.tsv` | the draft data model as a column list |
| `fetch_schema.py` | the archive's table list and the DR3 column lists (`results/archive_tables.csv`, `results/dr3_tap_schema_columns.csv`) |
| `common.py` | polite web client: identifying User-Agent, one request at a time with 1 second between, disk cache, request log |
| `test_*.py` | 50 tests, no network |
| `results/` | `run_log.tsv`, `request_log.tsv`, `dr3_checks.md`, `ephemeris_check.md`, `b_validation.md`, `b_sample.csv`, `b_minus_v_fit.json`, `dr3_tap_schema_columns.csv`, `out/` |
| `data/` | cached downloads, not committed |

Downloads: 108 requests in all, all anonymous, with the User-Agent `Foundation0-gaia-dr4/0.1 (+https://github.com/Foundation-0/gaia-dr4)`.
The request log lists 106: 75 Gaia archive queries answered, 4 refused for syntax (a test of what ADQL accepts, run twice), 5 timed out,
13 DataLink epoch-photometry files and 1 refused (the old structure name), 3 VizieR cone searches, 3 pages or papers and 2 documentation fetches that returned HTTP 503.
The other two were done outside the logger: the draft data model zip and the text of issue #4. A few web searches and page reads
through the assistant's web tools are not counted.
Requests went one at a time, so the archive never saw more than one job from this work at once.

## Acknowledgements

This work has made use of data from the European Space Agency (ESA) mission Gaia (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis Consortium (DPAC, https://www.cosmos.esa.int/web/gaia/dpac/consortium).
APASS DR9 magnitudes (Henden et al. 2016) were read from the Gaia archive's copy and, for three stars, from the VizieR service at CDS, Strasbourg.
No MAST/TESS or NASA Exoplanet Archive data were used.
