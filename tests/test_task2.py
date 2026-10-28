import unittest,runpy,pathlib,tempfile,datetime
ROOT=pathlib.Path(__file__).resolve().parents[1]
m=runpy.run_path(str(ROOT/'tools/fetch_epoch.py'))
class OfflineTests(unittest.TestCase):
    def test_behaviour(self):

        class Client:
            attempts=0
            def load_data(self,**kw):
                self.attempts+=1
                if self.attempts==1:raise OSError('temporary')
                pathlib.Path(kw['output_file']).write_bytes(b'fixture')
                self.last=kw
        with tempfile.TemporaryDirectory() as d:
            c=Client();wait=[]
            m['fetch'](['1','2','2'],c,pathlib.Path(d)/'cache',str(pathlib.Path(d)/'log'),sleep=wait.append)
            self.assertEqual(c.attempts,3);self.assertEqual(wait,[2])
            self.assertEqual(c.last['data_structure'],'DATAMODEL_STANDARD')
            self.assertEqual(len((pathlib.Path(d)/'log').read_text().splitlines()),3)

if __name__=="__main__":unittest.main()
