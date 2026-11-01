import io
import json
import pathlib
import random
import runpy
import sys
import tempfile
import unittest
import urllib.parse
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "datalink"))
import gaia_datalink as g  # noqa: E402

m = runpy.run_path(str(ROOT / "tools/fetch_epoch.py"))


def _csv_bytes(sid, n=12):
    buf = io.StringIO()
    w = __import__("csv").writer(buf, lineterminator="\n")
    w.writerow(g._DR3_COLUMNS)
    for i in range(n):
        t = 1700.0 + 10.0 * i
        row = {c: "" for c in g._DR3_COLUMNS}
        row.update(
            solution_id="375316653866487564",
            source_id=sid,
            transit_id=str(1000 + i),
            g_transit_time=repr(t),
            g_transit_flux="5000.5",
            g_transit_flux_error="3.2",
            g_transit_flux_over_error="1500.0",
            g_transit_mag="15.1",
            bp_obs_time=repr(t + 0.0003),
            bp_flux="2000.0",
            bp_mag="15.6",
            rp_obs_time=repr(t + 0.0004),
            rp_flux="3000.0",
            rp_mag="14.5",
            variability_flag_g_reject="false",
            rejected_by_photometry="false",
        )
        w.writerow([row[c] for c in g._DR3_COLUMNS])
    return buf.getvalue().encode()


def _zip_for(sid):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("EPOCH_PHOTOMETRY_Gaia_DR3_%s.csv" % sid, _csv_bytes(sid))
    return buf.getvalue()


class RetryTransport:
    """Fails the first request, then returns a valid zip (exercises bounded retry + wait)."""

    def __init__(self):
        self.calls = 0

    def get(self, url):
        self.calls += 1
        sid = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["ID"][0]
        if sid == "1" and self.calls == 1:
            return g.Response(503, {"content-type": "text/html"}, b"temporary outage")
        return g.Response(200, {"content-type": "application/zip"}, _zip_for(sid))


class OfflineTests(unittest.TestCase):
    def test_serial_fetch_retries_and_dedupes(self):
        transport = RetryTransport()
        waits = []
        with tempfile.TemporaryDirectory() as d:
            cache = pathlib.Path(d) / "cache"
            log = pathlib.Path(d) / "log.jsonl"
            summary = m["fetch"](
                ["1", "2", "2"],
                cache,
                log,
                transport=transport,
                sleep=waits.append,
                rng=random.Random(42),
            )
            self.assertEqual(summary["ok"], 2)
            self.assertEqual(summary["failed"], 0)
            self.assertEqual(transport.calls, 3)
            self.assertGreaterEqual(len(waits), 1)
            self.assertLessEqual(summary["peak_open_requests"], 1)
            lines = log.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 3)
            last_req = json.loads(lines[-1])
            self.assertEqual(last_req["source_id"], "2")
            self.assertEqual(last_req["status"], "downloaded")
            csv_path = cache / "Gaia_DR3" / "DATAMODEL_STANDARD" / "1.csv"
            self.assertTrue(csv_path.is_file() and csv_path.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
