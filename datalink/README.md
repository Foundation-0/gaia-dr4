# DataLink fetcher for Gaia epoch photometry

**What this is.** A script, `gaia_datalink.py`, that takes a file of Gaia source IDs and downloads each star's
epoch photometry from the Gaia archive. Epoch photometry is a star's brightness at each time Gaia observed it.
The archive serves it through DataLink, its file service, and in Gaia DR4 it will be served only that way.
This folder holds the script, its tests, and a test report made on Gaia DR3 on 27 October 2026.
It answers [issue #2](https://github.com/Foundation-0/gaia-dr4/issues/2).

**Status: claimed.** The script was tested on the live DR3 archive with anonymous access only (no account).
It has never run against DR4, which is not released. It has never run signed in. See
[What was not checked](#what-was-not-checked).

Gaia is a spacecraft of the European Space Agency (ESA). DR3 is its third data release. DR4 is the fourth,
due 2 December 2026. The archive goes offline on 25 November 2026 at 12:00 CET and reopens with DR4 on
2 December 2026 at 12:00 CET
([ESA news page](https://www.cosmos.esa.int/web/gaia/news), item of 8 Oct 2026).

Words used here:

- **Source ID**: Gaia's number for one star.
- **Request**: one call to the archive over the web. **HTTP status** is the archive's reply code. 200 means success,
  429 means "too many requests", 500 to 599 mean a fault on the archive's side.
- **Job**: the archive's name for work it runs for one user. Each request counts as one job.
- **Batch**: the star IDs sent together in one request.
- **Structure**: the layout of the file the archive sends back.
- **Backoff**: waiting longer after each failure before trying again.
- **Time-out**: giving up on a reply that takes too long.
- **Checksum** (SHA-256): a fingerprint of a file. The same file always gives the same fingerprint.

## Run it

All commands run from this folder. Python 3.10 or newer (tested on 3.13), standard library only.

```sh
python3 -m unittest                                     # 68 tests, no network (2 live tests skip)
GAIA_LIVE_TESTS=1 python3 -m unittest -v test_live      # the live test: sends 3 requests to the archive

# Fetch the 25 stand-in sources (sends 9 requests, about 20 seconds)
python3 -I gaia_datalink.py fetch sources/ids25.txt --out data/mine --batch-size 5 --jobs 2 --slots-dir data/slots
python3 -I compare_runs.py data/mine results/expected_sha256.csv    # same files as on 27 Oct 2026?
python3 -I gaia_datalink.py check data/mine                          # re-check every saved file

# The same sources in the other structure, and a check that both hold the same numbers
python3 -I gaia_datalink.py fetch sources/ids25.txt --out data/mine_gaia --structure DATAMODEL_GAIA \
    --batch-size 5 --jobs 2 --slots-dir data/slots
python3 -I cross_check_structures.py data/mine data/mine_gaia
```

`python3 -I` is used for every script that reads downloaded files. It stops Python from loading code from the
current folder or from environment variables. Never run these from inside `data/`.

Your own list: one source ID per line (a CSV with a `source_id` column also works).
Use `--dry-run` to see the plan without sending anything. A first trial on a new list: add `--max-requests 2`.

With your own archive account (**never run, untested**). The script asks for the password if `GAIA_PASSWORD` is not
set, and keeps the login cookie in memory only. Use the account of the person you work for, and never share it:

```sh
GAIA_USER=<name> python3 -I gaia_datalink.py fetch ids.txt --out data/run1 --login --batch-size 50 --jobs 5 \
    --slots-dir data/slots
```

| Option | Default | Meaning |
|---|---|---|
| `--release` | `Gaia DR3` | `Gaia DR4` exists but is a guess (see the release-day list) |
| `--structure` | `DATAMODEL_STANDARD` | or `DATAMODEL_GAIA`. The old names `INDIVIDUAL` and `RAW` are refused |
| `--batch-size` | 20 | stars per request. The archive allows at most 50 anonymously |
| `--jobs` | 2 | requests open at once. The script refuses anything above 5 |
| `--min-interval` | 1 s | pause between the starts of two requests |
| `--max-attempts` | 6 | tries per request before giving up on it |
| `--max-requests` | 0 (no limit) | stop after this many requests. Use a small number for a first trial |
| `--no-second-look` | off | skip the second request that confirms "no data" |
| `--slots-dir` | `~/.cache/f0-gaia-datalink/slots` | folder of lock files. Runs that share it share the job limit |
| `--login` | off | sign in (reads `GAIA_USER`, `GAIA_PASSWORD`). Never run, see below |

Files written to `--out`: `Gaia_DR3/<structure>/<source_id>.csv`, `events.jsonl` (one line per request and per
source), `fetch.log`, `summary.json`, and `rejected/` for any answer that failed a check.
Run the same command again and it carries on where it stopped.

## What the archive says

Read on 27 October 2026 (UTC). The pages are saved under `data/pages/`, which is not committed.

**News item of 14 Oct 2026**, [Gaia news page](https://www.cosmos.esa.int/web/gaia/news), headline "New release of
the Gaia ESA Archive with breaking changes":

> The DataLink data structures formerly known as RAW and INDIVIDUAL have been renamed to DATAMODEL_GAIA and
> DATAMODEL_STANDARD, respectively.
>
> To support a fair and equitable distribution of resources, users cannot have more than 5 jobs in execution in
> parallel. Each user has a queue that holds 50 jobs. Jobs submitted in excess of this queue length will be
> rejected. At the same time, both the synchronous and asynchronous query time-out, maximum number of rows
> returned per query, and maximum number of sources returned per query for DataLink products have been updated
> (see the Archive user guide).

Both changes in the issue are confirmed by the archive's own page. The news item does not give the new
time-outs or source limits. The user guide does (next). Its table has no date, so it is not certain that it
reflects the 14 Oct update. Its limit of 50 sources per DataLink query for anonymous users is what the live
archive enforced.

**Release notes, version 3.15 of 14 Oct 2026**,
[Release notes](https://www.cosmos.esa.int/web/gaia-users/archive/release-notes). Under "DataLink service":
the two renames, "Improved file-naming rules when retrieving products in the DATAMODEL_GAIA (previous RAW) data
structure", "Improved performance (resulting in reduced data retrieval time)", and "Empty data products are no
longer retrieved". It also asks users to update Astroquery (the Python package for the archive).

**User quotas**, [user guide, "Gaia archive user quotas"](https://www.cosmos.esa.int/web/gaia-users/archive/collaborate)
(the page shows no update date):

| Item | Anonymous | Signed in |
|---|---|---|
| Synchronous query time-out | 60 s | 60 s |
| Asynchronous query time-out | 1 min | 120 min |
| Queued queries | 50 | 50 |
| Active queries | 100 | 5 |
| Rows per query | 50,000 | unlimited |
| **Sources per DataLink query** | **50** | **5,000** |

The page adds that the active and queued numbers for anonymous users are for the whole pool of anonymous users at
any given time, not per person. So the 100 active queries are shared with everyone who is not signed in. The signed-in
row (5 active, 50 queued) matches the "5 jobs and a queue of 50" of the news item.

**Not updated by ESA yet.** The command-line page
([programmatic access](https://www.cosmos.esa.int/web/gaia-users/archive/programmatic-access), last update
2024-12-10) still lists `INDIVIDUAL | RAW` as the accepted `DATA_STRUCTURE` values. ESA's DR3 tutorial notebooks
(version 1.2 of 30 May 2025, in
[esa/gaia-jupyter-notebooks](https://github.com/esa/gaia-jupyter-notebooks/tree/main/data-release-3-tutorials))
also still use `INDIVIDUAL` and `RAW` (the copies read on 27 Oct 2026). Code that sends those names to the archive
fails with the error shown below. Not tested through Astroquery.

The same page says several sources come back as a `.gzip` file. The live archive sent a `.zip` (below).

## How DR3 epoch photometry is fetched today

The URL pattern, from the
[programmatic access page](https://www.cosmos.esa.int/web/gaia-users/archive/programmatic-access) and tested live:

```
https://gea.esac.esa.int/data-server/data?RETRIEVAL_TYPE=EPOCH_PHOTOMETRY&ID=<id>,<id>,...&RELEASE=Gaia+DR3&FORMAT=CSV&DATA_STRUCTURE=DATAMODEL_STANDARD
```

A plain GET request, no login needed. `https://gea.esac.esa.int/data-server/datalink/links?ID=Gaia+DR3+<id>` lists
the products of one star and gives a data URL of the same form (tested on one star). The archive treats each request
as a job: the links answer is named "Datalink job for user anonymous". So a request in flight probably counts
toward the 5-job limit. That is my reading. ESA does not say it.

| Parameter | What it does | What I saw on 27 Oct 2026 |
|---|---|---|
| `RETRIEVAL_TYPE` | which product. `EPOCH_PHOTOMETRY` here | required. Missing: HTTP 500, "Parameter not found: retrieval_type" |
| `ID` | source IDs, comma separated. Documented also: designations such as `Gaia DR3 123`, ID ranges, a column of a TAP job | a list of 1 to 50 IDs works. A designation worked for one star. Ranges and TAP job columns were not tried. Letters in an ID: HTTP 500, "Linking parameter is null" |
| `RELEASE` | `Gaia DR3` | optional for DR3 IDs (same file without it). `Gaia DR2` with a DR3 ID: empty answer. `Gaia DR4`: HTTP 500, "No services found for ... SOURCE_ID and Gaia DR4" |
| `FORMAT` | file format | `CSV`, `VOTABLE`, `VOTABLE_PLAIN`, `FITS`, `ECSV` worked. `XYZ`: HTTP 500, "no formatter has been found for the given MIME type" |
| `DATA_STRUCTURE` | file layout | see the next table |
| `VALID_DATA`, `BAND` | documented options | `VALID_DATA=TRUE` and `BAND=G` gave a file identical to the default one for the one star tested. ESA says `BAND` has had no effect since Dec 2024 |

**Structure names.** One star, `FORMAT=CSV`, one request each, at about 00:21 UTC. Full answers are in
[results/probe-structure_single.jsonl](results/probe-structure_single.jsonl) and
[results/probe-structure_multi.jsonl](results/probe-structure_multi.jsonl).

| `DATA_STRUCTURE` | HTTP | Answer |
|---|---|---|
| `DATAMODEL_STANDARD` | 200 | CSV, 25 columns, one row per observation (23 rows for this star), 8,156 bytes |
| omitted | 200 | the same bytes as `DATAMODEL_STANDARD` (same SHA-256) |
| `datamodel_standard` | 200 | the same bytes. The name is not case sensitive |
| `DATAMODEL_GAIA` | 200 | CSV, 48 columns, one row per star, each observation column holds a list such as `(1708.9, 1821.7, ...)` |
| `INDIVIDUAL` | 500 | `The 'INDIVIDUAL' data structure has been deprecated - use 'DATAMODEL_STANDARD' instead` |
| `RAW` | 500 | `The 'RAW' data structure has been deprecated - use 'DATAMODEL_GAIA' instead` |
| `COMBINED`, `FOO` | 500 | `Invalid Data Structure parameter: 'FOO', valid ones are: DATAMODEL_GAIA, DATAMODEL_STANDARD` |

The old names fail with HTTP 500 and a readable message. They are not silently mapped to the new names.
The same holds for three stars in one request ([results/probe-structure_multi.jsonl](results/probe-structure_multi.jsonl)).

**What comes back.**

- One star, `DATAMODEL_STANDARD`: a plain CSV file (`text/csv`).
- Two to 50 stars, `DATAMODEL_STANDARD`: a zip file (`application/zip`), one CSV per star, named
  `EPOCH_PHOTOMETRY_Gaia_DR3_<source_id>.csv`. (Seen when 2 to 50 stars had data. A request where only one of
  several stars has data never came up. The script accepts a plain CSV or a zip either way.)
- `DATAMODEL_GAIA`: always one CSV, one row per star.
- A star with no epoch photometry is left out. If none of the stars has any, the answer is HTTP 200 with no
  content at all. There is no error and no message. A source ID that is not in DR3 behaves the same way.
- Times are in days. The values (1,706 to 2,686 in these stars) fit "days since JD 2455197.5" (Barycentric Julian
  Date in TCB, a time scale tied to the solar system's centre of mass), the scale the draft DR4 data model gives
  for DR4. The DR3 documentation was not read for this. Empty cells mean "not measured".

Answers for the 25 stand-in stars, in [`results/expected_sha256.csv`](results/expected_sha256.csv) and
[`results/expected_sha256_datamodel_gaia.csv`](results/expected_sha256_datamodel_gaia.csv).

## The fetcher

| What the issue asks | What the script does | How it is tested |
|---|---|---|
| Never more than 5 jobs open | `--jobs` is refused above 5. A pool of slots (in memory, plus lock files shared between runs on one computer) blocks a sixth request | Offline tests against a small pretend archive on 127.0.0.1 that counts open requests: peak never above the limit for 1, 2, 3 and 5 jobs, and 30 batches with 5 jobs. Live: peak 2 |
| Wait before retrying | Exponential backoff: 2, 4, 8, 16, 32 s, capped at 120 s, each times a random factor between 0.5 and 1. A pause applies to all workers, not only the one that failed. `Retry-After` is obeyed. A queue message waits at least 30 s | Offline tests with a scripted fake archive: doubling, cap, `Retry-After: 37`, HTTP 429, 502, 503, network error |
| Batches | Up to 50 IDs per request (20 by default). If the archive replies "Maximum number of Source Ids reached (max: N ...)", the script splits the batch and remembers N | Offline test (limit 3); live (51, 100 and 200 IDs refused with "max: 50") |
| 429 and 5xx | Retried with backoff. After 2 failures a batch is split in half to find a bad star. After 12 failures in a row the run stops, and the same command resumes later | Offline tests |
| Queue awareness | It never sends more than `--jobs` requests, so it never builds a queue. An answer that mentions a full queue or job limit is treated as "wait at least 30 s". The archive's real wording for this is **not known**: it never came up in 27 Oct testing, so the match is on guessed phrases | Offline test with a made-up message |
| Cache and resume | Every accepted file is saved at once. The log decides what is done. A file that is missing or has a different size is fetched again. `check` also compares checksums | Offline tests; live: second run sent 0 requests |
| Validation | A file is kept only if: it is UTF-8 and ends with a newline, all expected columns are present, every row has the right source ID and the same number of fields, `transit_id` does not repeat, times are inside the range of the release (1,650 to 2,720 days for DR3), magnitudes are between 0 and 35, no more than 3,000 rows for one star. Every kept file gets a SHA-256 checksum (a fingerprint of the file) in the log. A failed file is kept in `rejected/` and fetched again | Offline tests for each failure; `check` command re-validates a finished run |
| No data | A star missing from an answer, or an empty answer, is asked for once more ("second look") before it is logged as `no_data`. Without this a dropped answer would look like a star with no data | Offline tests; live: all 7 `no_data` stars were empty on the second look |
| Log | Each source gets one line in `events.jsonl`: source ID, structure, release, UTC time, HTTP status, content type, status, rows, bytes, SHA-256, or the archive's message. Each request gets one line too. Messages have the caller's address and session removed | Offline test |
| Old names | `Config` refuses `INDIVIDUAL` and `RAW` and names the new one. If the archive says a name is deprecated or invalid, the run stops at once | Offline and live tests |

Other protections: a zip or gzip answer that would unpack to more than 400 MB is refused. Nothing from an answer is
ever written to a path it names. Downloaded files are never executed. The answer may be a zip, a gzip or a gzip
of a tar file. Only the zip was seen live.

## Test on 25 DR3 stars

Chosen by [select_sources.py](select_sources.py) with fixed queries on the archive's query service (TAP) on
27 Oct 2026. The lists are in [sources/](sources/). Running the script again in an empty folder gave identical files.

| Group | Stars | How chosen | Result |
|---|---|---|---|
| regular | 10 | `gaiadr3.gaia_source`, `has_epoch_photometry = 'True'`, not in the eclipsing-binary table (all 10 have `phot_variable_flag = VARIABLE`) | 10 `ok`, 439 rows, 23 to 67 rows each |
| eclipsing | 8 | in `gaiadr3.vari_eclipsing_binary`, `has_epoch_photometry = 'True'` | 8 `ok`, 247 rows, 20 to 48 rows each |
| no epoch | 5 | real DR3 stars with `has_epoch_photometry = 'False'` | 5 `no_data` |
| not found | 2 | valid numbers that are not DR3 sources (`1000000000000000`, `4611686018427387904`) | 2 `no_data` |

**Final run** (`data/final_std`, script as committed): 25 stars asked, 18 `ok`, 7 `no_data`, 0 failed, 686 rows,
9 requests (5 batches of 5 and 4 second looks), at most 2 requests open at once, 19.9 s.
All 18 files have the same SHA-256 as in `results/expected_sha256.csv`. The same 25 stars were fetched twice earlier
that day (one job, then two jobs, batches of 5) with identical files. 40 other stars (`sources/ids40.txt`) in batches of
10 and 20, with one and two jobs, gave identical files in all three runs.

**Both structures agree.** For the 18 stars with data, `DATAMODEL_STANDARD` and `DATAMODEL_GAIA` have the same number
of epochs and the same `transit_id`, G time, G flux, G magnitude, BP time and RP time at every epoch (tolerance
1e-9, [cross_check_structures.py](cross_check_structures.py)). The DATAMODEL_GAIA run also matched its own earlier run.

**The failure path.** A mixed request (two good stars, one with no epoch photometry or one that does not exist)
gave a zip of the two good stars and nothing for the third. A request with only stars that have no data gave HTTP 200
and no content, in 0.5 to 0.9 s. The script logged each as `no_data` with the reason.
The script was also pointed at `Gaia DR4`: HTTP 500 "No services found", logged and stopped at once as a fatal error
(`data/run_dr4_probe`). A run with `--timeout 0.3 --max-attempts 3` (the secure connection cannot be set up in 0.3 s) tried three times,
waited 1.4 s and then 3.1 s (first run) or 2.5 s (second run), and logged the star as `failed`
(`data/run_timeout_probe`, `data/run_timeout_probe2`). The waits are 2 s and 4 s times a random factor from 0.5 to 1.

## How big a request can be

One request each, anonymous, `DATAMODEL_STANDARD`, 27 Oct 2026. Details in
[results/probe-batch.jsonl](results/probe-batch.jsonl).

| IDs in one request | HTTP | Seconds | Rows | Bytes |
|---|---|---|---|---|
| 1 | 200 | 2.1 | 23 | 8,156 |
| 10 | 200 | 11.5 and 14.3 | 260 and 524 | 39,849 and 75,076 |
| 50 | 200 | 59.4 and 75.3 | 1,726 and 2,262 | 256,395 and 326,929 |
| 51 | 500 | 1.3 | | `Maximum number of Source Ids reached (max: 50, found: 51)` |
| 100 | 500 | 1.5 | | `... (max: 50, found: 100)` |
| 200 | 500 | 2.8 | | `... (max: 50, found: 200)` |

The service accepts up to 50 IDs anonymously and refuses the whole request above that. One 50-ID request took 75 s,
longer than the 60 s synchronous time-out in the user guide, and still succeeded. The time-out may not apply to
DataLink. The signed-in limit of 5,000 was **not** tested.

## Speed

From [results/timing-summary.txt](results/timing-summary.txt), made by [summarize_timing.py](summarize_timing.py)
from 41 answers with data and 12 empty ones. All taken between 00:21 and 00:52 UTC on a Tuesday night
(about 01:20 to 01:55 CET), when few people use the archive.

| IDs per request | Requests | Median seconds | Range | Rows per second |
|---|---|---|---|---|
| 1 | 8 | 2.0 | 1.7 to 2.2 | 11.8 |
| 3 | 4 | 3.0 | 2.5 to 4.5 | 26.4 |
| 5 | 15 | 4.9 | 3.9 to 9.2 | 24.0 |
| 10 | 10 | 14.3 | 11.5 to 24.6 | 26.4 |
| 20 | 2 | 34.9 | 27.0 to 42.8 | 24.6 |
| 50 | 2 | 67.4 | 59.4 to 75.3 | 29.6 |

- Time per request follows the number of rows: seconds = 1.25 + 0.0342 x rows (R squared 0.98, where 1.0 would be a perfect straight line), about 29 rows per
  second. It follows the number of IDs less well (R squared 0.93, about 1.4 s per ID).
- The stars here have 37 rows each on average (12,505 rows for 335 stars). So a 50-star request takes about a minute.
  A bigger batch saves only the fixed 1 to 2 s per request. It does not make the archive faster per star.
- A request for stars without data comes back in about 0.65 s (12 requests, 0.54 to 0.90 s).
- Two jobs at once did not slow each request. The same 40 stars took 64.1 s with one job (37 stars per minute)
  and 39.9 s with two (60 per minute): 1.6 times faster, not 2 times. For the 25 stars it was 28.4 s and 18.9 s (1.5 times).
  More than 2 jobs were **not** measured.
- Size on disk: 12.9 KB per star as CSV (231,887 bytes for 18 stars).

**Estimates for DR3-type stars (37 rows each), not measurements:**

| Stars | 1 job | 2 jobs | 5 jobs |
|---|---|---|---|
| 1,000 | 22 to 27 minutes | 14 to 17 minutes | not measured |
| 100,000 | 35 to 45 hours | 22 to 28 hours | not measured. 7 to 9 hours only if five jobs ran as fast as one |

1,000 stars are 20 requests of 50 and about 13 MB as CSV. 100,000 stars are 2,000 requests and about 1.3 GB as CSV.

**Caveat for release day.** These numbers come from a quiet night, DR3 data, anonymous access and 2 jobs at most.
DR4 covers 66 months of observations and DR3 covered 34 ([DR4 content page](https://www.cosmos.esa.int/web/gaia/dr4)),
so each star may have about twice the rows, and time follows rows.
On 2 December many people will ask for DR4 at once. Expect slower and refused requests. Plan for lists of hundreds or a
few thousand stars on release day, not 100,000. Measure again on the day with 1, 10 and 50 IDs before a large run.

## What was checked, and what was not

Checked:

- 68 offline tests pass (`python3 -m unittest`). The 2 live tests pass (3 requests).
- The live archive on 27 Oct 2026: new names accepted, old names refused, 50-ID limit, formats, failure answers, the
  quotas and the 14 Oct changes as quoted above.
- The same files came back across runs, job counts and batch sizes (above).
- The saved files in the `results/` folder contain no address, session or login. Error pages are cleaned before they
  are saved or logged.

What was not checked:

- **Any signed-in access.** No account was used. `--login` follows ESA's documented login
  (`https://gea.esac.esa.int/data-server/login`, form fields `username` and `password`, session cookie kept in memory).
  It refuses to send a password to any host other than `https://*.esa.int`. It has never run against the real archive.
  The 5,000-ID limit and the 5-job limit were never exercised. The issue's check "someone else runs the test with their own
  archive account and gets the same light curves" is still open.
- **More than 2 requests at once** against the live archive. The 5-job limit is enforced and tested against a
  pretend archive only.
- **What the archive does at the limits.** No 429, no `Retry-After` and no queue message was ever
  returned in testing, and no request timed out except in the forced test above. Those code paths are tested against
  invented answers only. If the script gives up on a slow request, the archive may keep running that job and the script
  cannot see it. Not tested.
- **Other formats.** VOTable, FITS and ECSV answers were fetched for one star and saved, but the script only
  validates CSV.
- **Other products.** XP spectra, RVS and the rest are out of scope.
- **Speed at busy times.** All timing was taken at night.
- **Whether `ID` ranges, TAP job columns and designations work in batches.** Only plain source IDs were tested.

## Release day: what is expected to differ in DR4

Each line says where it comes from. "Draft" means ESA's
[draft DR4 data model](https://anonftp.cosmos.esa.int/pub/GAIA_PUBLIC_DATA/Gaia_DR4/dr4-prerelease/gaia-dr4-prerelease-draft-data-model_2026-06-26.zip)
(pre-released June 2026 on the [pre-release page](https://www.cosmos.esa.int/web/gaia/dr4-prerelease), file dated 2026-06-26) and the [DR4 content page](https://www.cosmos.esa.int/web/gaia/dr4) (table last updated 14 Sep 2026).
ESA says both can change. **Nothing below was tested on DR4 data: ESA's pre-release has no epoch photometry (only
epoch astrometry for 12 stars, according to the pre-release page), so there is nothing to test on before 2 December.**

- [ ] **Archive up?** From 25 Nov 12:00 CET to 2 Dec 12:00 CET nothing can be fetched. Today a request with
  `RELEASE=Gaia DR4` gives HTTP 500, "No services found ... SOURCE_ID and Gaia DR4". A different answer means DR4 is live.
  *(observed 27 Oct 2026)*
- [ ] **Release name.** The script assumes `Gaia DR4`, by analogy with `Gaia DR3`. *(guess)*
- [ ] **Structure names.** The draft names `DATAMODEL_STANDARD` and `DATAMODEL_GAIA` as the two choices for
  epoch photometry (section 11.1). *(draft)* The script does not support `DATAMODEL_GAIA` for DR4: its layout was not checked.
- [ ] **Source selection.** In the draft, the flag `has_epoch_photometry` is a boolean in the table `all_source_flags`, not in
  `gaia_source` as in DR3. The queries from the DR3 test (`WHERE has_epoch_photometry = 'True'`) must change (the draft's wording is `= 'true'`). *(draft)*
- [ ] **Product names.** The draft lists three: `EPOCH_PHOTOMETRY` (one row per field-of-view transit, G, BP and RP,
  121,845,163,512 rows, 7.2 TB), `EPOCH_PHOTOMETRY_CCD` (G band at CCD level, 23 TB, listed with the same row count) and
  `EPOCH_PHOTOMETRY_CROWDED_FIELD`. The script fetches only `EPOCH_PHOTOMETRY`. *(draft)*
- [ ] **TAP.** The draft says the table "is not available through the main archive TAP interface". DataLink is the only way.
  *(draft, and the project README)*
- [ ] **Column names.** The draft table `epoch_photometry` has: `solution_id`, `source_id`, `transit_id`, `g_n_obs`,
  `g_obs_time`, `g_flux`, `g_flux_error`, `g_flux_over_error`, `g_mag`, `bp_obs_time`, `bp_flux`, `bp_flux_error`,
  `bp_flux_over_error`, `bp_mag`, `rp_*` likewise, `transit_acq_flags`, `transit_proc_flags`, `phot_ccd_proc_flags`
  (a list of 12 numbers) and `xp_ccd_info_flags` (a list of 2). *(draft)*
  The DR3 file has `g_transit_time`, `g_transit_flux` and `g_transit_mag` for G, plus `variability_flag_*_reject`,
  `g_other_flags`, `bp_other_flags`, `rp_other_flags` and `rejected_by_photometry`, which the draft does not list.
  The script's DR4 check requires `source_id`, `transit_id`, `g_obs_time`, `g_flux`, `g_mag` and the BP and RP time,
  flux and magnitude columns. If the real DATAMODEL_STANDARD file uses other names, every file is rejected with
  "missing columns" and kept in `rejected/`. That is the signal to edit `_DR4_COLUMNS` in `gaia_datalink.py`. *(guess)*
- [ ] **Time scale.** The draft keeps "Barycentric JD in TCB minus 2455197.5 days". DR4 covers 25 Jul 2014 to 20 Jan 2020,
  so times up to about 3,671. The script accepts 1,650 to 3,700 for DR4. *(draft for the scale, own sum for the range)*
- [ ] **Rows per star.** Unknown. The script accepts up to 20,000 for DR4 (3,000 for DR3). *(guess)*
- [ ] **Answer packing.** DR3 sends a zip for several stars. ESA's user guide says gzip. The script reads both. For DR4
  the file names will probably say `Gaia_DR4`. The script uses the digits at the end of the name and compares them with the
  source ID inside the file. *(DR3 observed, DR4 guess)*
- [ ] **Limits.** The quotas page may change for DR4. Use a signed-in account on the day: the anonymous pool is shared by
  everyone, 100 active jobs at most. Keep `--jobs` at 5 or less. *(user guide, 27 Oct 2026)*
- [ ] **Batch size.** Anonymous: 50. Signed in: 5,000 per the user guide. At about 1.3 s per star, a 5,000-star request
  would run for about two hours, far past the 60 s synchronous time-out in the user guide. Start with 20 to 50. *(untested)*
- [ ] **Fallback.** ESA's news of 17 Dec 2025 says that when DataLink was slow, products could be taken from the
  bulk-download repository. Whether that exists for DR4 epoch photometry is not known.
- [ ] **Astroquery.** Release 3.15 asks users to update it. ESA's DR3 notebooks still use the old names. Not tested
  whether `Gaia.load_data` takes the new ones.
- [ ] **Star IDs.** DR4 source IDs are independent of DR3. A DR3 ID list cannot be reused (project README).

## What still needs a person

- Run the test with their own archive account (the issue's check), including `--login`. Credentials must stay
  with the person.
- Choose `--jobs` and `--batch-size` for the release-day account, and who runs step 6 of the
  [runbook](../RUNBOOK.md) with this script.
- Any message to ESA or the Gaia helpdesk, for example to ask about DR4 DataLink limits, the answer format, or a
  bulk download for epoch photometry. The project rules say that needs a person.
- Review this folder and commit it. The pull request must say an AI agent did the work and name the person who
  signs for it.

## Files

| Path | What |
|---|---|
| `gaia_datalink.py` | the fetcher |
| `test_gaia_datalink.py` | 68 offline tests |
| `test_live.py` | 2 live tests, off unless `GAIA_LIVE_TESTS=1` |
| `probe.py` | sends the fixed list of test requests of the structure, format, parameter, batch-size and failure groups (40 requests) and saves each answer |
| `select_sources.py` | chooses the test stars with 3 TAP queries |
| `compare_runs.py` | compares two runs, or a run and a checksum list |
| `cross_check_structures.py` | compares `DATAMODEL_STANDARD` and `DATAMODEL_GAIA` numbers |
| `summarize_timing.py` | makes the timing tables |
| `sources/` | the test star lists |
| `results/` | what the archive answered (`probe-*.jsonl`), the checksums, timing tables and run summaries |
| `data/` | raw answers, saved pages and run folders. Not committed (`.gitignore`) |

About 118 requests were sent in the whole test (96 to the DataLink service, 7 TAP queries, about 15 page and file
downloads from ESA and GitHub), under the 150 aimed for.
At most 2 DataLink requests were open at once, with an identifying `User-Agent`
(`Foundation0-gaia-dr4/0.1 (+https://github.com/Foundation-0/gaia-dr4)`).

## Acknowledgement

This work has made use of data from the European Space Agency (ESA) mission Gaia (https://www.cosmos.esa.int/gaia),
processed by the Gaia Data Processing and Analysis Consortium (DPAC,
https://www.cosmos.esa.int/web/gaia/dpac/consortium).
