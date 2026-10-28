# DataLink acceptance

Status: preparation for review. No observational result is claimed.

The fetcher issues one blocking request at a time and queues no asynchronous jobs. Three attempts use waits of two and four seconds. This bounds this process; other processes sharing the account still count toward archive limits.

The current Astroquery source names DATAMODEL_STANDARD and DATAMODEL_GAIA: https://github.com/astropy/astroquery/blob/main/astroquery/gaia/core.py. Stable documentation still shows older names, so the installed version needs a DR3 smoke test before use. The stated account-wide limits of five running and fifty queued jobs still require verification on ESA's current release notes.

Run `python3 tools/fetch_epoch.py source_ids.txt /outside-git/epoch-cache fetch.jsonl` with a current Astroquery. No credentials are embedded. Before acceptance, fetch six selected DR3 sources, inspect ZIP contents and source IDs, and have a second person repeat with their own account. This branch has no live archive acceptance evidence.
