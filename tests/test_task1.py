import unittest,runpy,pathlib,tempfile,datetime
ROOT=pathlib.Path(__file__).resolve().parents[1]
m=runpy.run_path(str(ROOT/'tools/map_ids.py'))
class OfflineTests(unittest.TestCase):
    def test_behaviour(self):

        rows=m['join']([{'tic_id':'1','dr2_source_id':'999999999999999999'},{'tic_id':'2','dr2_source_id':'2'}],[{'dr2_source_id':'999999999999999999','dr3_source_id':'111111111111111111'},{'dr2_source_id':'999999999999999999','dr3_source_id':'222222222222222222'}])
        self.assertEqual([r['match_status'] for r in rows],['ambiguous','ambiguous','unmatched'])
        self.assertEqual(rows[0]['dr2_source_id'],'999999999999999999')

if __name__=="__main__":unittest.main()
