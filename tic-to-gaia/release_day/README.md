# Release day: from Gaia DR3 to Gaia DR4

This is the procedure for the last link of the chain, DR3 source ID to DR4 source ID, for the stars in
`../tic_to_gaia_dr3.csv`. It is step 2 of [RUNBOOK.md](../RUNBOOK.md).

**Nothing here has run against DR4.** The table that links DR3 to DR4, `dr3_neighbourhood`, does not exist until the
archive reopens on Wednesday 2 December 2026 at about 12:00 CET (Central European Time) ([ESA news, the European Space Agency](https://www.cosmos.esa.int/web/gaia/news),
read 27 Oct 2026). The code is tested on DR3 and on made-up rows. The ADQL query (ADQL is the archive's query
language, a form of SQL) is written from a draft and is marked untested.

## Why DR3 IDs cannot be reused

ESA's [DR4 page](https://www.cosmos.esa.int/web/gaia/dr4) (last updated 14 Sep 2026) says the DR4 source list "should
be treated as independent from Gaia DR3" and that a record must not be fetched by the same source ID. ESA's draft DR4
data model says something a little softer. It says most sources associated with the same object "can be identified by
sharing the same source_id in both releases", and that different identifiers are assigned in other cases. So an equal
ID is not proof, and a different ID is not a mismatch. On our own data the same thing already happens one step
earlier. For 21 of 651 stars the DR2 ID does not exist in DR3 (see [../README.md](../README.md)).

The new table was designed for this. It lists DR3 and DR4 sources that lie within 2 arcsec of each other. A position is
right for one date only, because stars move. That date is the position's epoch. Epochs are written like J2016.0, where
the J means Julian years, so J2016.0 is the start of 2016 and J2017.5 is the middle of 2017. The DR4 position is first
moved back to J2016.0, the DR3 epoch, with the DR4 proper motion. Proper motion is a star's slow drift across the
sky. The same table also gives the G magnitude difference (G is Gaia's main brightness band) and a `probable_match`
flag. The draft's rule for that flag is: closer than 60 mas and G(DR4) minus G(DR3) between -0.25 and 0.35. A mas is a
thousandth of an arcsecond.

## Before you start

- You need your own Gaia archive account (see RUNBOOK.md). The limits are 5 jobs running at once and 50 queued, for
  each user ([ESA news, 14 Oct 2026](https://www.cosmos.esa.int/web/gaia/news)). Expect the archive to be slow.
- Everything the TIC targets need from the old archive is already in `../snapshots/`. Nothing more has to be
  downloaded from the Gaia archive before 25 November for this step. (The TIC comes from MAST, the Mikulski Archive for Space Telescopes, and I did not check
  whether MAST stays up during the Gaia outage.)
- Use `python3 -I` for every script, as elsewhere in this project. Answers downloaded from the archive are data, not
  code. Do not run anything from them.
- Save every answer in `work/` inside this folder. `.gitignore` keeps `work/` out of git, so downloaded answers
  cannot be committed by accident. Commit only the queries and the final tables, copied out of `work/`.

## Step 1. Check the data model

Do this before any other query. The draft data model is "subject to change ... without any public notification"
(its own words, draft dated 2026-05-20 on its front page, in the zip named 2026-06-26).

```sql
SELECT table_name, description FROM tap_schema.tables WHERE table_name LIKE '%dr3_neighbourhood%'
SELECT column_name, datatype, unit, description FROM tap_schema.columns WHERE table_name = '<name found above>'
SELECT column_name FROM tap_schema.columns WHERE table_name = 'gaiadr4.gaia_source'
SELECT column_name FROM tap_schema.columns WHERE table_name IN ('gaiadr4.all_source_astrometry', 'gaiadr4.all_source_photometry')
```

The same kind of query worked on DR3 on 27 Oct 2026. Expect:

| Table | Columns the code uses |
|---|---|
| `gaiadr4.dr3_neighbourhood` | `source_id` (the DR4 ID, not `dr4_source_id`), `dr3_source_id`, `angular_distance` (mas), `magnitude_difference`, `proper_motion_propagation`, `probable_match` |
| `gaiadr4.gaia_source` | `source_id`, `ra`, `dec`, `pmra`, `pmdec`, `phot_g_mean_mag`, `ruwe`, `ref_epoch` |
| `gaiadr4.all_source_astrometry` (only for `--all-sources`) | `source_id`, `ra`, `dec`, `pmra`, `pmdec`, `ruwe`, `ref_epoch` |
| `gaiadr4.all_source_photometry` (only for `--all-sources`) | `source_id`, `phot_g_mean_mag` |

All the `gaia_source` names were found in the draft's `gaia_source` section, and the `all_source_*` names in its
sections 2.1 and 2.4. The schema name `gaiadr4` for `dr3_neighbourhood` and for the two `all_source_*` tables is an
assumption: the draft's own example reads `gaiadr4.gaia_source` and `gaiadr3.gaia_source` but does not name the
neighbourhood table's schema.

If a name or a unit differs, stop. Edit the query in `dr4_link.py` (`NEIGHBOURHOOD_QUERY`, `cone_query`,
`cone_query_all_sources`), re-run
`python3 -m unittest discover ../tests`, and tell the others. `match-neighbourhood` also stops with a message if an
answer file lacks a column.

One known change: the draft has no `astrometric_params_solved` column. The DR3 table used it to flag stars with only
a position (the flag `dr3_two_parameter_solution`). Find out what DR4 offers in its place before reusing that check.

## Step 2. Route 1, through `dr3_neighbourhood`

```sh
python3 -I release_day/dr4_link.py neighbourhood-queries --out-dir work/route1
```

This writes 7 query files, six with 100 DR3 IDs and one with 51, already filled in (651 IDs in all). The query is in
[dr3_to_dr4_neighbourhood.adql](dr3_to_dr4_neighbourhood.adql), which also has a second query for the reverse check.

1. Run the 7 files one after the other in the archive. A synchronous query worked for 100 IDs on DR3. (Synchronous
   means the archive answers on the same connection and does not queue a job.)
2. Save each answer as CSV (a plain text table with commas between values): `work/route1/answer_000.csv`, `answer_001.csv`, and so on. The number must match the
   query file. `match-neighbourhood` stops with a message if a query file in the folder has no answer, so that a
   forgotten batch is not read as "no match".
3. Build the table:

```sh
python3 -I release_day/dr4_link.py match-neighbourhood --dir work/route1 --out work/route1_table.csv
```

The rule: among the neighbours with `probable_match` true, take the one with the smallest `angular_distance`. If the
answer has no `probable_match` column, the code recomputes it from the draft's rule above. The status is
`one-to-one` only if the table lists exactly one DR4 neighbour for the DR3 star and no other target picked the same
DR4 star. Otherwise it is `ambiguous`. If no neighbour is probable it is `no match`.

A person looks at every row with `needs_judgement = yes`: no match, several probable matches, one DR4 star chosen by
two targets, or a DR4 star without a proper motion.

The reverse check is by hand. For each chosen DR4 ID, run the second query in the `.adql` file to see whether other
DR3 sources point at it. On DR3 this found 9 of the 13 ambiguous stars.

## Step 3. Route 2, by position (the fallback and a second opinion)

Use it for every target that has no row or no probable match in route 1. Run it for all of them if the archive allows,
because two routes that agree are stronger than one.

```sh
python3 -I release_day/dr4_link.py position-queries --out-dir work/route2
```

This writes 27 query files of up to 25 targets each, and `expected_positions.csv`. Each target's DR3 position is
moved to epoch J2017.5 (DR4's reference epoch) with its DR3 proper motion. For the one target without a DR3 proper
motion, TIC 370244729, the TIC's proper motion is used and the file says so in `pm_from`. Each query asks
`gaiadr4.gaia_source` for every source within 2 arcsec of those positions. That kind of query is a cone search: it
asks for every source inside a circle on the sky, here one circle of 2 arcsec radius around each target.

1. Run the files one after the other (route 1 plus route 2 is 34 queries, under the queue limit of 50, but only 5
   run at once).
2. Save each answer as CSV: `work/route2/answer_000.csv`, and so on.
3. Match and compare. `match-positions` also stops if a query file has no answer:

```sh
python3 -I release_day/dr4_link.py match-positions --dir work/route2 --out work/route2_table.csv
python3 -I release_day/dr4_link.py compare-routes --neighbourhood work/route1_table.csv \
    --positions work/route2_table.csv --out work/compare.csv
```

The rule: keep sources within 2 arcsec whose G minus the star's DR3 G is between -0.25 and 0.35, and take the closest.
The status is `one-to-one` if exactly one source lies within the radius, `ambiguous` if several do, `no match` if
none is left. The radius is the one Gaia used for `dr2_neighbourhood`, and the window is the draft's
`probable_match` window. Neither was tuned on DR4.

`match-positions` writes the `ref_epoch` of each chosen source. The draft data model says a small number of sources
have astrometry from other processing modules or from earlier, shorter data sets. We infer that their `ref_epoch` can
differ from 2017.5, which is not a stated rule. The command prints a note when a chosen source has another
`ref_epoch`, because its position is then for another date. A person looks at those rows.

**`gaia_source` may not hold every target.** The draft data model says DR4's `gaia_source` has only the sources with
both good astrometry and good photometry. The complete lists are the tables `all_source_astrometry` and
`all_source_photometry` (draft data model, sections 1.1, 2.1 and 2.4, read 27 Oct 2026). A target outside
`gaia_source` would come back as `no match` although it exists. So repeat the search on the complete tables for every
target with status `no match` in `work/route2_table.csv`, and for every `neither` row of the comparison:

```sh
awk -F, '$4=="no match"{print $1}' work/route2_table.csv > work/no_match.txt
python3 -I release_day/dr4_link.py position-queries --all-sources --tic-list work/no_match.txt --out-dir work/route2_all
```

Run those files, save the answers as `work/route2_all/answer_000.csv` and so on, then run
`match-positions --dir work/route2_all --out work/route2_all_table.csv`. This is untested against DR4. The query joins
the two tables on `source_id` and asks for the same columns as before. These are a few rows. Read them by hand.
`compare-routes` takes one position table, so they are not folded into it.

How far the targets move (650 of the 651 have a DR3 proper motion): the median is 27 mas per year, 17 stars move faster than 200 mas per year, and the fastest
moves 576.5 mas per year (0.86 arcsec in 1.5 years). That is inside the 2 arcsec radius even without the move, so a bad
proper motion does not lose a star. The targets span G = 8.5 to 14.8.

## Step 4. Read the comparison

`work/compare.csv` has one row per target. A route can find a star that the other misses. For route 2 one possible reason is that the star is not in `gaia_source`, the subset of DR4 described in Step 3.

| `agreement` | What to do |
|---|---|
| `agree` | Accept the DR4 ID. |
| `disagree` | A person looks. Keep both IDs. |
| `only neighbourhood`, `only position` | A person looks. |
| `neither` | No DR4 counterpart was found in `gaia_source`. Run the `--all-sources` search for it (Step 3) if you have not. Then a person looks. |

Do not use "same ID as DR3" as a test. The column `same_id_as_dr3` is there to count how many kept their ID, for
information.

## What was tested, and what was not

| Part | Tested on | Result |
|---|---|---|
| Position route (queries, matching) | DR3 as a stand-in. The "old" positions are the TIC's Gaia DR2 positions at J2015.5, moved to J2016.0. 100 targets, 4 queries. | 100 of 100 gave the same DR3 star as the table, including all 13 ambiguous ones. |
| `match-neighbourhood` | Relabelled `dr2_neighbourhood` answers for all 651 stars, as if they were DR3 to DR4 answers. | Same chosen ID and the same status for all 651. This tests the code. It says nothing about the DR4 table. |
| `compare-routes`, answer parsing, `probable_match` rule, `pm_from` | Unit tests on made-up rows (`../tests/test_dr4_link.py`). | Pass. |
| The check that every query file has an answer, the `ref_epoch` column, `--tic-list` | Unit tests on made-up files. | Pass. |
| `position-queries --all-sources` | Unit tests on the query text and the files written. Nothing on DR4. | **Untested** against the real tables. |
| The ADQL against `dr3_neighbourhood` | Nothing. | **Untested.** |
| The cone queries against `gaiadr4.gaia_source` | Nothing on DR4. The same cone query shape ran on `gaiadr3.gaia_source` in the stand-in test. | Untested on DR4. |

The stand-in test is easier than the real step. The gap between DR2 and DR3 positions is 0.5 years and the gap between
DR3 and DR4 is 1.5, and the TIC's DR2 positions are the same stars' own measurements.

## Files

| Path | What |
|---|---|
| `dr3_to_dr4_neighbourhood.adql` | The route 1 query and the reverse-check query. Untested. |
| `dr4_link.py` | Commands: `neighbourhood-queries`, `match-neighbourhood`, `position-queries` (options `--all-sources`, `--tic-list`), `match-positions`, `compare-routes`, `standin-test`. |
