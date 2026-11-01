# DataLink acceptance

Status: preparation for review. No observational result is claimed.

The serial entry point is `tools/fetch_epoch.py`. It calls the HTTP DataLink client in
[`datalink/gaia_datalink.py`](../datalink/gaia_datalink.py) (shared with branch `prep/gaia-dr4-tasks`), not
Astroquery's `load_data` / `output_file` API. Astroquery 0.4.11 ignores `output_file` and writes
`datalink_output_<timestamp>.zip` in the current working directory, which broke the earlier prototype.

This wrapper keeps one request in flight (`jobs=1`), at most three attempts per source, and exponential
backoff between attempts (2 s and 4 s caps). That bounds this process; other processes sharing the account
still count toward the archive limit of five jobs in execution per user (see [`datalink/README.md`](../datalink/README.md)).

Structure name `DATAMODEL_STANDARD` matches the archive rename documented in astroquery and in ESA's October 2026
news item: https://github.com/astropy/astroquery/blob/main/astroquery/gaia/core.py

## Commands

Offline unit test (no network):

```bash
python3 tests/test_task2.py
python3 -m unittest -v datalink.test_gaia_datalink
```

Live DR3 smoke test (one HTTP request per source; optional second request if the archive returns empty once):

```bash
GAIA_LIVE_TESTS=1 python3 -m unittest -v tests.test_task2_live
python3 tools/fetch_epoch.py datalink/sources/ids25.txt /outside-git/epoch-cache fetch.jsonl
```

The full fetcher (batched requests, resume, checksums, five-job slot pool) lives under `datalink/`:

```bash
cd datalink && GAIA_LIVE_TESTS=1 python3 -m unittest -v test_live
```

No credentials are embedded. Before acceptance, fetch six selected DR3 sources, inspect CSV contents and source IDs,
and have a second person repeat with their own account. A run with `--jobs` greater than 1 must show at most five
open requests; the slot-pool tests in `datalink/test_gaia_datalink.py` check that rule against a local fake archive.
