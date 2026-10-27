# TIC to Gaia DR3

This folder links each target star of the gaia-dr4 project to its Gaia DR3 source ID. It does the work of
[issue #1](https://github.com/Foundation-0/gaia-dr4/issues/1).

The targets are the stars of eumemic's TESS planet candidates. TESS is NASA's planet-hunting satellite. Each
target has a TIC ID, its number in the TESS Input Catalog. Gaia is ESA's star-mapping spacecraft. It publishes its
catalogue in numbered data releases, written DR2, DR3 and DR4 (the second, third and fourth). Each release gives its
stars new numbers, called source IDs. The route from a TIC ID to Gaia DR3 is: TIC ID, then Gaia DR2 source ID (a
column of the TIC), then Gaia DR3 source ID (through the archive table `gaiadr3.dr2_neighbourhood`). The Gaia archive goes
offline on Wednesday 25 November 2026 at 12:00 CET until DR4 opens on Wednesday 2 December 2026 at about 12:00 CET
([ESA news, 8 Oct 2026, read 27 Oct 2026](https://www.cosmos.esa.int/web/gaia/news)). The mapping for the 14 Oct
candidate list is done. It has to be run again on the final lists before then.

Status: **claimed**. Nothing here has been checked by a person. Everything was run on 27 October 2026.

## Result

The input has 665 candidate rows. They belong to 651 different stars, because 14 stars have two candidate
signals. The table `tic_to_gaia_dr3.csv` has one row per star.

| Status | Stars | Meaning |
|---|---|---|
| one-to-one | 638 | The archive lists one DR3 star for the DR2 ID, and no other DR2 source points at it. |
| ambiguous | 13 | The archive lists two DR3 neighbours, or the DR3 star is also linked to another DR2 source. One was chosen and the rest are kept in the row. |
| no match | 0 | |
| no DR2 ID | 0 | |
| not in the TIC | 0 | |

- **21 of the 651 stars have a different ID in DR3 than in DR2.** Their DR2 IDs do not exist in DR3 at all (one
  query on 27 Oct 2026 asked for all 21 and got no rows). Looking a star up by its old ID would have lost 3.2% of
  the targets. All 21 are one-to-one.
- **The 13 ambiguous stars are not in real doubt.** In each, one DR3 star lies within 0.25 mas of the DR2 position
  (a mas is a thousandth of an arcsecond, and an arcsecond is 1/3600 of a degree). The other neighbour is 1.25 to
  1.95 arcsec away and 3.5 to 7.9 magnitudes fainter in DR3 (12 of the 13 have a G magnitude to compare, the 13th
  has none). They are flagged because the issue asks for every case with more than one possible match to be flagged.
- **Position check: all 651 pass.** Stars move, so a position is right for one date only, called its epoch. The
  TIC's positions are for the year 2000 and Gaia DR3's are for 2016.0. Each chosen DR3 star, moved to the TIC's epoch
  with its own proper motion, lies within 0.2 arcsec of the TIC position. Proper motion is a star's slow drift
  across the sky, in mas per year. The differences are tiny: the median is 1.7 mas, 90% are under 3.2 mas, 99% are
  under 4.9 mas, and the largest is 14.4 mas. No star is near the 0.2 arcsec line. Without the move to 2000, 505 of the
  651 would differ by more than 0.2 arcsec (median 0.43 arcsec, largest 9.2 arcsec).
- **Flags** (a star can carry several, the full list is in the `flags` column): 13 `several_dr3_neighbours`,
  11 `dr3_duplicated_source`, 9 `dr3_shared_with_other_dr2`, and 1 each of `dr3_two_parameter_solution`,
  `no_proper_motion_correction_in_crossmatch`, `proper_motion_from_tic`, `tic_gaia_quality_not_passed` and
  `tic_proper_motion_not_from_gaia_dr2`. The last two come from the TIC's own flags `gaiaqflag` and `pmflag`. The five
  flags that occur once all belong to TIC 370244729 (see "Where a person has to decide"). The counts are also in
  `tic_to_gaia_dr3.meta.json`.
- **No target is marked in the TIC as an artifact, duplicate or split star.** No record has a `disposition` or a
  `duplicate_id`, and all are of type `STAR`.

## Reproduce

Run these in this folder. Everything uses only the Python standard library. Python 3.13 was used.

```sh
# 1. Rebuild the table from the small snapshots in git. No network.
python3 -I ticmap.py build

# 2. Download everything again from the archives, then rebuild (28 requests, 4 to 7 minutes).
python3 -I ticmap.py run --targets /path/to/f0/docs/research/exoplanets/candidates.json

# Any other list works: a text file with one TIC ID per line, or a CSV with a `tic` column.
python3 -I ticmap.py run --targets my_tic_ids.txt --out my_table.csv --snap-dir my_snapshots --data-dir my_data

# 3. Checks
python3 -I simbad_check.py                  # SIMBAD cross-check (7 requests, cached)
python3 -I check_inputs.py                  # target file against the TIC, no network
python3 -I release_day/dr4_link.py standin-test   # test of the position fallback (4 requests)
python3 -m unittest discover tests          # 111 tests, no network
```

Without `--out` and `--snap-dir`, `fetch` and `run` replace the committed table and snapshots in this folder. That is
intended when you re-run on a new final list. For a trial, give your own `--out`, `--snap-dir` and `--data-dir`, as in
the last command of step 2.

If a download fails, nothing in the snapshot folder changes. Run the same command again. Answers already received are
kept in `data/` and are not asked for twice. A temporary failure is tried again twice, after 10 and 30 seconds,
before the command gives up. Temporary means a reset connection, a timeout, or one of the HTTP codes 429, 500, 502,
503 and 504 (the codes a web server sends when it is busy or restarting). A MAST query took about 20 to 85 seconds in
the runs so far. The timeout is 300 seconds, and `--timeout` changes it.

Each snapshot file is written to a temporary folder first and moved in only after every download has worked.
`snapshots/run_info.json` holds a checksum (a fingerprint) of each snapshot file, and `build` stops if a file does not
match.

`data/` holds every raw answer from the archives and is not committed (it is in `.gitignore`). A second run with
`data/` present sends nothing. The target file `targets_eumemic.csv` was made with
`python3 -I ticmap.py targets candidates.json -o targets_eumemic.csv`.

### The queries and when they ran

All four are sent as anonymous TAP queries, 100 IDs at a time. TAP is the standard way to send a query to an
archive, and the queries are written in ADQL, a form of SQL. They are synchronous: the archive answers on the same
connection and does not queue a job. The exact text is in `ticmap.py` and in
`snapshots/run_info.json`, which also has the times.

| What | Service | Ran (UTC, 27 Oct 2026) |
|---|---|---|
| TIC records, table `dbo.catalogrecord` | [MAST TIC TAP](https://mast.stsci.edu/vo-tap/api/v0.1/tic/sync) | 00:27 to 00:30 |
| `gaiadr3.dr2_neighbourhood` by DR2 ID | [Gaia archive TAP](https://gea.esac.esa.int/tap-server/tap/sync) | 00:30 |
| `gaiadr3.dr2_neighbourhood` by DR3 ID (the reverse check) | Gaia archive TAP | 00:30 |
| `gaiadr3.gaia_source` for the DR3 IDs | Gaia archive TAP | 00:31 |

```sql
-- the Gaia query that matters (the others have the same shape; see ticmap.py)
SELECT dr2_source_id, dr3_source_id, angular_distance, magnitude_difference, proper_motion_propagation
FROM gaiadr3.dr2_neighbourhood
WHERE dr2_source_id IN (...up to 100 IDs...)
ORDER BY dr2_source_id, angular_distance
```

## How a neighbour is chosen

`gaiadr3.dr2_neighbourhood` lists every DR3 star near a DR2 star. It does not say which one is "the" match.

- **Gaia gives no "best neighbour" for this table.** The archive's DR3 schema has 12 `*_best_neighbour` tables, all
  for external catalogues (2MASS, Pan-STARRS1, SkyMapper DR2 and others). None is for Gaia DR2. For DR2 to DR3 there is
  only `dr2_neighbourhood` (asked of the archive's `tap_schema` on 27 Oct 2026). The archive's own description of the
  table gives no selection rule. It says a DR3 source may have "none, one or (rarely) several" DR2 counterparts and
  that there is "no guaranteed one-to-one correspondence".
- **ESA's tutorial** ([How to combine Gaia data with other data](https://www.cosmos.esa.int/web/gaia-users/archive/combine-with-other-data),
  read 27 Oct 2026) says the table was made by moving DR3 positions with a linear proper motion correction "when
  possible" and matching within 2 arcsec. Its example query keeps only pairs with
  `ABS(magnitude_difference) < 0.1`, with the comment "Exclude sources having G-band magnitude differences above 0.1
  mag".
- **ESA's DR3 documentation, chapter 16** has example queries that take the closest neighbour. I could not read it.
  Its pages answered with an error (HTTP 503, "service unavailable") every time I tried on 27 Oct 2026 (four tries by
  script, more by a web reader). I know
  its content only from a search summary, so I do not rely on it.
- **The rule used here**, which is the task's rule built from the two readable sources: among the neighbours with
  `ABS(magnitude_difference) < 0.1`, take the one with the smallest `angular_distance`. If none passes the cut, take
  the closest and flag it. In this run the closest neighbour passed the cut for every star, so the two rules never
  disagreed. The 0.1 cut is ESA's example, not a Gaia rule.
- **Status** is `one-to-one` only if the table has exactly one neighbour row for the DR2 ID and no other DR2 source
  also points at the chosen DR3 star. Otherwise it is `ambiguous`. A second query (by DR3 ID) finds the other DR2
  sources.

What the Gaia columns mean. Read from the archive's table description, then tested on our 651 stars:

| Column | Meaning |
|---|---|
| `angular_distance` | Distance between the DR2 and DR3 positions in mas, with the DR3 position moved to the DR2 epoch when DR3 has a proper motion. It matches our own calculation to 0.002 mas (median difference). |
| `magnitude_difference` | G magnitude (Gaia's main brightness band) of the DR3 star minus that of the DR2 star. The archive does not give the sign. It is DR3 minus DR2: against DR3 G minus the TIC's DR2 G the correlation is 1.000 and the median difference is 0. |
| `proper_motion_propagation` | True if the DR3 star had a proper motion to move it with. False for one star (see below). |

## What the table columns mean

| Column | Meaning |
|---|---|
| `tic`, `dr2_source_id`, `dr3_source_id` | The three IDs. `dr3_source_id` is the chosen one. |
| `status` | one-to-one, ambiguous, no match, no DR2 ID or not in TIC. |
| `n_neighbours`, `n_mag_consistent` | DR3 neighbours listed for the DR2 ID, and how many have a magnitude difference under 0.1. |
| `angular_distance_mas`, `magnitude_difference`, `proper_motion_propagation` | The three Gaia columns above, for the chosen neighbour. |
| `runner_up_*` | The next-closest neighbour: its ID, distance, magnitude difference, and its DR3 G minus the chosen star's DR3 G (`runner_up_delta_g`). |
| `n_dr2_for_dr3` | Number of DR2 sources the chosen DR3 star is linked to. Above 1 means ambiguous. |
| `pos_sep_tic_epoch_arcsec` | Position check: separation between the TIC position (epoch 2000) and the DR3 position moved to 2000. |
| `pos_sep_dr2_epoch_arcsec` | The same at the DR2 epoch 2015.5, using the TIC's original DR2 position. |
| `pos_check` | `ok` up to 0.2 arcsec, `check` up to 1 arcsec, `large` above. These limits are this project's choice. |
| `nearest_by_position_dr3` | Filled only if another neighbour lies nearer the TIC position than the chosen one. Never filled in this run. |
| `flags`, `needs_judgement`, `judgement_reasons` | Flags and the reasons a person should look. A TIC flag other than `gaiaqflag` 1 and `pmflag` gaia2 sets `needs_judgement`. |
| `tic_ra`, `tic_dec`, `tic_pmra`, `tic_pmdec`, `tmag`, `tic_disposition` | From the TIC. `tmag` is the TESS magnitude. |
| `tic_gaiaqflag`, `tic_pmflag` | The TIC's own flags ([TIC column schema](https://outerspace.stsci.edu/x/chSeBg), read 27 Oct 2026). `gaiaqflag` says whether the Gaia information passed the TIC's quality check: 1 passes, 0 fails, -1 means not enough information. `pmflag` names where the TIC proper motion comes from. `gaia2` is Gaia DR2, `tgas` is the Tycho-Gaia solution. |
| `dr3_pmra`, `dr3_pmdec`, `dr3_g`, `dr3_ruwe` | From `gaiadr3.gaia_source`. RUWE is a number that grows when a star's positions do not fit a single star. All are under 1.4 (largest 1.386). One star has no RUWE. |

The TIC step: the TIC column `gaia` holds the DR2 source ID. The TIC `ra` and `dec` are for epoch 2000
([TIC column schema, STScI, read 27 Oct 2026](https://outerspace.stsci.edu/x/chSeBg)). Our check agrees: the DR3
positions only line up with the TIC when moved to 2000. `ra_orig` and `dec_orig` are the positions of the source
catalogue. For these 651 stars that catalogue is Gaia DR2, and the numbers match DR3 moved to 2015.5.

## What was checked

| Check | Result |
|---|---|
| Same table on a second run. A second download was made about 10 minutes after the first, into a separate folder. | Identical table and identical snapshots. All Gaia answers were identical byte for byte. The TIC answers had the same rows in another order. |
| Rebuild from the saved raw answers | Identical to the committed table. |
| Snapshots against the raw answers | All 651 TIC records, 664 neighbour rows, 683 reverse rows and 664 DR3 rows match. |
| Independent recomputation by the builder, with pandas and numpy and another separation formula. The script was not kept in this folder, so it cannot be re-run from here. | Same DR3 IDs, neighbour counts, shared-star counts and statuses for all 651. Separations agree to 5 millionths of an arcsecond. |
| Target file against the TIC (`check_inputs.py`). eumemic gives positions to 0.001 degree and Tmag to 0.01. | No target is flagged. Position differences are at most 2.39 arcsec (rounding can explain 2.55). Tmag differences are at most 0.005. |
| Position check at the TIC epoch | 651 of 651 within 0.2 arcsec. |
| SIMBAD cross-check (`simbad_check.py`) | See below. No disagreement. |
| Position fallback test (`release_day/dr4_link.py standin-test`) | 100 of 100 targets gave the same DR3 star as the table, including all 13 ambiguous ones. |
| Unit tests | 111 pass. They cover the retries, the refusal of a bad MAST answer, the all-or-nothing snapshots and the SIMBAD verdicts. |
| A second agent (the verifier) checked this folder on 27 Oct 2026 and did not edit it. **Reported to me, not repeated by me. Its scripts are not in this folder.** | A full download from an empty cache gave the same table. A separate route that does not use `dr2_neighbourhood` (the TIC position and proper motion moved to 2016.0, then the nearest DR3 source within 3 arcsec) chose the same DR3 ID for 651 of 651 stars. Of 10 targets listed in the [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu), 9 have Gaia IDs there and all 9 agree with the table on DR2 and DR3. The Tycho-2 star ID that 185 TIC records carry agrees with Gaia's own Tycho-2 match for the chosen DR3 star in 185 of 185 cases. The TIC's original position (`ra_orig`, `dec_orig`) equals the position of the TIC's DR2 ID in the CDS copy of Gaia DR2 for 651 of 651 stars. |

**SIMBAD** is an astronomy database that lists all the names of each object. For each star the script asks SIMBAD
for the objects named `TIC <id>`, `Gaia DR2 <id>` and `Gaia DR3 <id>`, using the IDs in our table.

| SIMBAD answer | Stars |
|---|---|
| TIC, DR2 and DR3 names are all known and sit on one object | 232 |
| TIC and DR3 names sit on one object, SIMBAD has no DR2 name | 15 |
| DR2 and DR3 names sit on one object, SIMBAD has no TIC name | 20 |
| Only one name is known (the DR3 name in all 34 cases) | 34 |
| Star not in SIMBAD | 350 |
| Names on different objects | 0 |

The 350 and the 34 are neither confirmed nor contradicted. SIMBAD's TIC link is itself built from the TIC, so the
TIC name does not test the TIC to DR2 step. Where a DR3 name and a DR2 name or a TIC name sit on one object (267 stars),
the DR2 to DR3 step agrees with SIMBAD's own cross-match.

The issue asks for a spot check of a few mappings by hand. The script draws 10 targets with a fixed random seed, 4
from the 13 ambiguous stars and 6 from the 638 one-to-one stars. The draw uses all stars, not only those SIMBAD
confirms. A sample taken from confirmed stars would be confirmed by construction and would show nothing. SIMBAD
confirms 4 of the 10 through all three names. For the other 6 it knows too few names or not the star at all, so those
need the check below. **A person has not yet looked at any of the 10.**

To check one, open its link. VizieR (CDS's catalogue service) shows the Gaia DR3 record, including the columns
`RAJ2000` and `DEJ2000`, which are the DR3 position that CDS has moved to the year 2000. That position should match the
TIC position in the table to within a few mas. The last column before SIMBAD is our own offset for comparison. I
tested the link on the first row only. VizieR gave 72.44924492 and -1.41682391 against the TIC's 72.44924533 and
-1.41682383, a difference of 1.5 mas, equal to our own 1.5 mas.

| TIC | Status | Gaia DR3 (VizieR) | TIC position, degrees, year 2000 | Our offset (mas) | SIMBAD |
|---|---|---|---|---|---|
| 11083646 | ambiguous | [3226574909603691392](https://vizier.cds.unistra.fr/viz-bin/VizieR-4?-source=I/355/gaiadr3&Source=3226574909603691392) | 72.44924533, -1.41682383 | 1.5 | all three names (TYC 4736-245-1) |
| 21409936 | one-to-one | [4804609734548020864](https://vizier.cds.unistra.fr/viz-bin/VizieR-4?-source=I/355/gaiadr3&Source=4804609734548020864) | 85.03854097, -41.52156668 | 1.0 | all three names (TYC 7605-1507-1) |
| 79278415 | one-to-one | [6320381307658461184](https://vizier.cds.unistra.fr/viz-bin/VizieR-4?-source=I/355/gaiadr3&Source=6320381307658461184) | 228.43517978, -8.91705007 | 1.6 | not in SIMBAD |
| 90903678 | ambiguous | [6674714941347333632](https://vizier.cds.unistra.fr/viz-bin/VizieR-4?-source=I/355/gaiadr3&Source=6674714941347333632) | 307.66296831, -46.41121476 | 2.0 | DR2 and DR3 names (UCAC4 218-192181) |
| 137157568 | ambiguous | [561865255137893504](https://vizier.cds.unistra.fr/viz-bin/VizieR-4?-source=I/355/gaiadr3&Source=561865255137893504) | 30.12392638, 77.40310989 | 2.0 | all three names (TYC 4499-2196-1) |
| 155816991 | one-to-one | [6838693223591525760](https://vizier.cds.unistra.fr/viz-bin/VizieR-4?-source=I/355/gaiadr3&Source=6838693223591525760) | 326.44602382, -14.80214133 | 5.3 | not in SIMBAD |
| 178827999 | one-to-one | [3821986672523474816](https://vizier.cds.unistra.fr/viz-bin/VizieR-4?-source=I/355/gaiadr3&Source=3821986672523474816) | 150.62717067, -5.08718886 | 2.1 | DR3 name only (UCAC4 425-052883) |
| 310979214 | one-to-one | [2661885799368229376](https://vizier.cds.unistra.fr/viz-bin/VizieR-4?-source=I/355/gaiadr3&Source=2661885799368229376) | 346.86717905, 3.85797777 | 3.3 | all three names (TYC 579-966-1) |
| 420978569 | ambiguous | [5929065776501514624](https://vizier.cds.unistra.fr/viz-bin/VizieR-4?-source=I/355/gaiadr3&Source=5929065776501514624) | 252.48801080, -56.76427518 | 0.8 | not in SIMBAD |
| 448985959 | one-to-one | [5846248872737552768](https://vizier.cds.unistra.fr/viz-bin/VizieR-4?-source=I/355/gaiadr3&Source=5846248872737552768) | 214.99910896, -70.56444451 | 2.5 | not in SIMBAD |

The full per-star SIMBAD result is in `snapshots/simbad_crosscheck.csv`.

## Limits

- **The TIC release is not confirmed as v8.2.** The MAST service holds one table, `dbo.catalogrecord`, and does not
  name its release. STScI's [release notes](https://outerspace.stsci.edu/spaces/TESS/pages/40927681/TIC+v8+and+CTL+v8.xx+Data+Release+Notes)
  (read 27 Oct 2026) call v8.2 "the current version". All 651 records carry the entry date `20190415`, close to the
  v8.0 delivery date the notes give (10 or 15 April 2019). Versions 8.1 and 8.2 changed only some entries, so this
  fits v8.2 but does not prove it. A query for entries with any other date timed out (HTTP 504, "gateway timeout")
  and was not repeated. The verifier (see "What was checked") compared the 651 MAST records with the copy that CDS
  names "TIC-8.2" ([VizieR IV/39/tic82](https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=IV/39/tic82)). The
  Gaia DR2 ID agrees for 651 of 651, and position, proper motion and Tmag agree to rounding. That supports v8.2 for
  these stars. It does not show that MAST serves v8.2, because an earlier version may have left these entries unchanged.
  I did not repeat that comparison.
- **The position check does not test the TIC to DR2 step.** The TIC position comes from the same Gaia DR2 star, so a
  wrong DR2 ID in the TIC would not show. Two partial checks cover it: eumemic's own positions and Tmag agree with the
  TIC, and for 247 stars SIMBAD has a TIC name and a DR3 name on one object. SIMBAD's TIC link is itself built from
  the TIC. Two of the verifier's checks (see "What was checked") bear on this step too, and I did not repeat them.
- **The check ignores parallax and radial velocity**, and moves positions in a straight line on the sky. Parallax is
  the small yearly shift of a nearby star caused by the Earth's orbit. Radial velocity is a star's speed towards or
  away from us. Over the 16 years from 2016 to 2000 the straight-line move is wrong by about 1 mas for a star moving
  1 arcsec a year. It is far below the 0.2 arcsec limit.
- **The table covers neighbours within 2 arcsec of the DR2 star.** It does not list every star inside a TESS
  aperture (a patch of TESS pixels, each about 21 arcsec wide). The blend question B needs that wider list from
  another query.
- **No Kepler or K2 hosts yet.** The planet-host list of
  [issue #3](https://github.com/Foundation-0/gaia-dr4/issues/3) does not exist yet. The pipeline takes TIC IDs only.
  Kepler and K2 hosts would need a TIC ID first. The TIC has a `kic` column for Kepler IDs, but no lookup is built.
- **The candidate list has changed.** This run used the list of 14 Oct 2026 (665 rows, commit `58c6318` of
  [eumemic/exoplanets](https://github.com/eumemic/exoplanets)). eumemic's README of 22 Oct 2026 counts 645. Run the
  pipeline again on the current list before 25 November.
- **The Gaia documentation pages did not load** (HTTP 503), as described above.
- **The fallback by position searches only DR4's `gaia_source`, in the first instance.** The draft DR4 data model says
  `gaia_source` holds only the sources with both good astrometry and good photometry. The complete lists are in the
  tables `all_source_astrometry` and `all_source_photometry` (draft data model, sections 1.1, 2.1 and 2.4, read 27 Oct
  2026). A target outside that subset could be missed by the first search. `position-queries --all-sources` repeats
  the search on the complete tables. It is untested, because those tables do not exist yet.
- **Not tested:** the DR3 to DR4 step. The table `dr3_neighbourhood` does not exist yet.
- About 90 requests were sent by the scripts (Gaia archive 62, MAST 18 plus 2 early metadata probes, SIMBAD 7, two
  file downloads), one at a time with at least 1 second between them, anonymous, with the User-Agent
  `Foundation0-gaia-dr4/0.1 (+https://github.com/Foundation-0/gaia-dr4)`. Five returned errors (four documentation
  pages with 503, one TIC query with 504). A web reader also fetched a few ESA, STScI and AIP pages to read them.
  The round of fixes after the verification added 3 requests, one to the STScI schema page and two to VizieR (one Gaia
  DR3 record page and one catalogue page), and re-ran everything else from the saved answers. The verifier sent about 88 requests of its own.

## Where a person has to decide

1. **TIC 370244729.** Its DR3 source has only a position, no proper motion (a "two-parameter solution", flagged
   `dr3_two_parameter_solution`). The TIC's own flags for this star also differ from all 650 others. `gaiaqflag` is 0,
   which the TIC defines as a failed quality check on the Gaia information (`tic_gaia_quality_not_passed`). `pmflag`
   is `tgas`, so the TIC proper motion comes from the Tycho-Gaia solution and not from Gaia DR2
   (`tic_proper_motion_not_from_gaia_dr2`). The other 650 stars have `gaiaqflag` 1 and `pmflag` `gaia2`. The match to
   DR3 is sound (one neighbour, 19.8 mas away, position check 14 mas). The later DR4 step is weaker for this star. The
   position fallback uses the TIC's proper motion for it, and that proper motion is not Gaia DR2's. It is the only row
   with `needs_judgement = yes`.
2. **The 11 stars flagged `dr3_duplicated_source`.** The archive describes the flag as "Source with multiple source
   identifiers". I did not look into what it means for each star. All 11 are one-to-one in this table. A person may
   want to look before the DR4 step. TIC IDs: 38680704, 105507572, 139885709, 159884708, 202664116, 256122096,
   322806500, 343942488, 364027765, 402047931, 462737661.
3. **The 13 ambiguous stars.** Whether to treat them as one-to-one downstream. The reasoning above says yes. Each has
   a faint neighbour 1.3 to 1.9 arcsec away, which may matter for the blend question B.
4. **The spot check by hand** that the issue asks for (the 10 links above). Six of the ten are not confirmed by
   SIMBAD through all three names, so the by-hand check carries the weight there.
5. **Before 25 November:** re-run on eumemic's current list and on the planet-host list once it exists. Then a person
   reviews and commits this folder. Nothing here has been committed or posted.

## What changes on release day

Details and the commands are in [release_day/README.md](release_day/README.md). In short:

- The DR3 to DR4 link comes from the new table `dr3_neighbourhood`, which is not published yet. The query in
  `release_day/dr3_to_dr4_neighbourhood.adql` is written from ESA's draft data model and is **untested**.
- The fallback is a search by position in DR4's `gaia_source` at epoch J2017.5 (DR4's reference epoch, from
  [ESA's DR4 page](https://www.cosmos.esa.int/web/gaia/dr4), last updated 14 Sep 2026), starting from each DR3
  position moved with its proper motion. Its code is tested on DR3 as a stand-in. DR4's `gaia_source` holds only
  the sources with good astrometry and photometry. A target missing there is searched for again on the complete
  tables (`--all-sources`, untested).
- ESA says DR4 source IDs "should be treated as independent from Gaia DR3". Do not match by equal ID.
- Nothing more needs to be downloaded from the Gaia archive for this step. `snapshots/` holds all it needs. The TIC
  comes from MAST, and I did not check whether MAST stays online during the Gaia outage.

## Files

| Path | What |
|---|---|
| `tic_to_gaia_dr3.csv` | The output table, one row per TIC ID (651 rows). |
| `tic_to_gaia_dr3.meta.json` | Settings, query texts, download times and the counts above. |
| `targets_eumemic.csv` | The 665 candidate rows made from `candidates.json`. |
| `ticmap.py` | The pipeline: `targets`, `fetch`, `build`, `run`, `summary`. |
| `tap.py`, `httpcache.py`, `astrometry.py` | Query helpers, a polite cached downloader (with retries), and position maths. |
| `simbad_check.py`, `check_inputs.py` | The two cross-checks. |
| `snapshots/` | Small CSV copies of every answer the table is built from, plus the check results. |
| `release_day/` | DR3 to DR4 procedure, ADQL template and the code to run it. |
| `tests/` | 111 unit tests. |
| `.gitignore` | Keeps `data/` (raw answers, about 10 MB), `data_rerun/` (the second download) and `work/` (release-day answers) out of git. |

## Acknowledgements

This work has made use of data from the European Space Agency (ESA) mission Gaia
(https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis Consortium (DPAC,
https://www.cosmos.esa.int/web/gaia/dpac/consortium). The TESS Input Catalog was read from the Mikulski Archive for
Space Telescopes (MAST), STScI. This work has made use of the SIMBAD database, operated at CDS, Strasbourg, France.
This research has made use of the VizieR catalogue access tool, CDS, Strasbourg, France (DOI: 10.26093/cds/vizier). This
research has made use of the NASA Exoplanet Archive, which is operated by the California Institute of Technology, under
contract with the National Aeronautics and Space Administration under the Exoplanet Exploration Program. The target list is by eumemic ([eumemic/exoplanets](https://github.com/eumemic/exoplanets), data CC BY 4.0).
