"""Serial Gaia epoch photometry fetcher (one HTTP request at a time, bounded retries).

Uses the HTTP DataLink client in ``datalink/gaia_datalink.py`` (direct archive GET), not
Astroquery's ``load_data`` / ``output_file`` path, which drops zips in the cwd on astroquery 0.4.11.
"""
import argparse
import datetime
import json
import logging
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "datalink"))

import gaia_datalink as g  # noqa: E402


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _append_log(log_path, **fields):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(fields, sort_keys=True) + "\n")


class SerialEpochFetcher(g.Fetcher):
    """``gaia_datalink.Fetcher`` with ``jobs=1`` and per-attempt lines in the task log file."""

    def __init__(self, cfg, log_path, transport=None, sleep=None, rng=None):
        super().__init__(
            cfg,
            transport=transport,
            sleep=sleep,
            rng=rng,
            log=logging.getLogger("fetch_epoch"),
        )
        self.log_path = pathlib.Path(log_path)

    def _log_attempt(self, source_ids, attempt, outcome, resp):
        for sid in source_ids:
            if outcome.kind == "data":
                status, error = "downloaded", None
            else:
                status = "error"
                error = outcome.message or outcome.kind
            _append_log(
                self.log_path,
                source_id=str(sid),
                structure=self.cfg.structure,
                utc=_utc_now(),
                attempt=attempt,
                status=status,
                error=error,
                http_status=resp.status if resp else None,
            )

    def _send(self, ids, attempt, second_look=False):
        resp, outcome = super()._send(ids, attempt, second_look)
        self._log_attempt(ids, attempt, outcome, resp)
        return resp, outcome


def fetch(ids, cache, log, transport=None, sleep=None, rng=None):
    """Fetch epoch photometry for ``ids`` into ``cache``; append JSON lines to ``log``."""
    ordered = list(dict.fromkeys(str(i).strip() for i in ids if str(i).strip()))
    for sid in ordered:
        if not sid.isdigit():
            raise ValueError("source IDs must be decimal integers")
    cache = pathlib.Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    pathlib.Path(log).parent.mkdir(parents=True, exist_ok=True)
    cfg = g.Config(
        str(cache),
        release="Gaia DR3",
        structure="DATAMODEL_STANDARD",
        batch_size=1,
        jobs=1,
        max_attempts=3,
        min_interval=0.0,
        backoff_base=2.0,
        backoff_cap=4.0,
        split_after=999,
        confirm_empty=True,
        confirm_missing=False,
        retry_no_data=False,
    )
    summary = SerialEpochFetcher(
        cfg, log, transport=transport, sleep=sleep, rng=rng
    ).run(ordered)
    if summary["failed"]:
        raise RuntimeError("DataLink failed after three attempts")
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("ids", help="text file with one Gaia source_id per line")
    p.add_argument("cache", help="output directory (CSV files under Gaia_DR3/DATAMODEL_STANDARD/)")
    p.add_argument("log", help="append-only JSONL log (source_id, structure, utc, attempt, status)")
    a = p.parse_args()
    ids = pathlib.Path(a.ids).read_text(encoding="utf-8").split()
    try:
        fetch(ids, a.cache, a.log)
    except (g.FatalError, g.Aborted, RuntimeError, ValueError):
        sys.exit(1)
