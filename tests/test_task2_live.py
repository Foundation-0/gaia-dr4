"""Live archive check for issue #2 / PR #10 (skipped unless GAIA_LIVE_TESTS=1).

    GAIA_LIVE_TESTS=1 python3 -m unittest -v tests.test_task2_live

Uses the serial wrapper in tools/fetch_epoch.py (HTTP DataLink via datalink/gaia_datalink.py).
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE_SOURCE = "1814404639814272"


@unittest.skipUnless(os.environ.get("GAIA_LIVE_TESTS") == "1", "set GAIA_LIVE_TESTS=1 for live archive access")
class LiveFetchEpoch(unittest.TestCase):
    def test_dr3_epoch_photometry_for_review_source(self):
        with tempfile.TemporaryDirectory() as d:
            ids = pathlib.Path(d) / "ids.txt"
            ids.write_text(LIVE_SOURCE + "\n", encoding="utf-8")
            cache = pathlib.Path(d) / "cache"
            log = pathlib.Path(d) / "log.jsonl"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tools/fetch_epoch.py"), str(ids), str(cache), str(log)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                proc.returncode,
                0,
                msg=(proc.stdout or "") + (proc.stderr or ""),
            )
            csv_path = cache / "Gaia_DR3" / "DATAMODEL_STANDARD" / (LIVE_SOURCE + ".csv")
            self.assertTrue(csv_path.is_file(), "expected CSV at %s" % csv_path)
            self.assertGreater(csv_path.stat().st_size, 1000)
            self.assertIn(LIVE_SOURCE, log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
