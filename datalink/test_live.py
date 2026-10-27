"""Live test: a few DR3 sources from the real Gaia archive. Sends 3 requests.

Skipped unless you ask for it, because it uses the archive:

    GAIA_LIVE_TESTS=1 python3 -m unittest -v test_live

It checks four things, using anonymous access:
  1. the archive refuses the old structure name INDIVIDUAL and says to use DATAMODEL_STANDARD (1 request);
  2. the archive accepts the new name (the requests of check 3 use it);
  3. four stand-in sources come back with the same files as on 27 Oct 2026
     (results/expected_sha256.csv), so a changed answer shows up;
  4. a source without epoch photometry is recorded as no_data.

To use your own archive account for a bigger run, see README.md. This test does not sign in.
"""
import csv
import os
import tempfile
import unittest

import gaia_datalink as g

HERE = os.path.dirname(os.path.abspath(__file__))


def expected():
    with open(os.path.join(HERE, "results", "expected_sha256.csv"), newline="") as f:
        return {r["source_id"]: r for r in csv.DictReader(f)}


@unittest.skipUnless(os.environ.get("GAIA_LIVE_TESTS") == "1", "set GAIA_LIVE_TESTS=1 to send 3 requests to the live archive")
class LiveTest(unittest.TestCase):
    def test_old_name_is_refused_and_the_message_names_the_new_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = g.Config(tmp, jobs=1, batch_size=1)
            f = g.Fetcher(cfg)
            sid = next(s for s, r in expected().items() if r["status"] == "ok")
            old = f.build_url([sid]).replace("DATAMODEL_STANDARD", "INDIVIDUAL")
            out = g.classify(f.transport.get(old))
            self.assertEqual(out.kind, "fatal")
            self.assertIn("DATAMODEL_STANDARD", out.message)

    def test_four_stand_in_sources(self):
        exp = expected()
        ok_ids = [s for s, r in exp.items() if r["status"] == "ok"][:3]
        no_data_id = next(s for s, r in exp.items() if r["role"] == "no_epoch")
        ids = ok_ids + [no_data_id]
        with tempfile.TemporaryDirectory() as tmp:
            cfg = g.Config(tmp, jobs=1, batch_size=4, slots_dir=os.path.join(tmp, "slots"))
            summary = g.Fetcher(cfg).run(ids)
            # One request for the four sources, and one second look at the source that came back missing.
            self.assertEqual((summary["ok"], summary["no_data"], summary["failed"], summary["requests"]), (3, 1, 0, 2))
            self.assertLessEqual(summary["peak_open_requests"], 1)
            state = g.Store(tmp).state("Gaia DR3", "DATAMODEL_STANDARD")
            for sid in ok_ids:
                self.assertEqual(state[sid]["sha256"], exp[sid]["sha256"], "file for %s changed" % sid)
                self.assertEqual(state[sid]["rows"], int(exp[sid]["rows"]))
            self.assertEqual(state[no_data_id]["status"], "no_data")


if __name__ == "__main__":
    unittest.main()
