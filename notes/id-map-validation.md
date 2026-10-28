# ID map validation

Status: preparation for review. No observational result is claimed.

Keep source IDs as decimal strings in CSV/JSON; a float cannot represent every Gaia ID. The join retains every neighbourhood candidate and emits an unmatched row when none exists. Angular distance retains the archive's unit (milliarcseconds); it must not be treated as arcseconds.

Run `python3 tools/map_ids.py targets.csv neighbourhood.csv map.json` on cached exports. Store both query texts, UTC retrieval times, archive release and SHA-256 checksums beside the exports. Actual target lists and a successful DR3 archive run remain prerequisites. No nearest-match selection is inferred from distance alone.

Before acceptance, sample ten matches using a recorded random seed, compare positions at a common epoch and inspect ambiguous cases. Report unmatched and ambiguous counts separately. DR4 release-day mapping requires a separately validated DR3-to-DR4 table.
