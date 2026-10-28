"""Serial Gaia epoch retrieval. Network runs require an installed current astroquery."""
import argparse,datetime,json,pathlib,time

def fetch(ids,client,cache,log,sleep=time.sleep):
    cache=pathlib.Path(cache);cache.mkdir(parents=True,exist_ok=True)
    for sid in dict.fromkeys(ids):
        if not str(sid).isdigit(): raise ValueError('source IDs must be decimal integers')
        dest=cache/(str(sid)+'.zip')
        if dest.exists(): continue
        for attempt in range(3):
            status='error'
            try:
                client.load_data(ids=[int(sid)],data_release='Gaia DR3',data_structure='DATAMODEL_STANDARD',retrieval_type='EPOCH_PHOTOMETRY',dump_to_file=True,output_file=str(dest),overwrite_output_file=False)
                if not dest.is_file() or dest.stat().st_size==0: raise RuntimeError('empty or missing download')
                status='downloaded'
            except Exception as exc:
                dest.unlink(missing_ok=True)
                error=type(exc).__name__
            with open(log,'a') as f:
                f.write(json.dumps(dict(source_id=str(sid),structure='DATAMODEL_STANDARD',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),attempt=attempt+1,status=status,error=None if status=='downloaded' else error))+'\n')
            if status=='downloaded': break
            if attempt==2: raise RuntimeError('DataLink failed after three attempts')
            sleep(2**(attempt+1))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('ids');p.add_argument('cache');p.add_argument('log');a=p.parse_args()
    from astroquery.gaia import Gaia
    fetch(pathlib.Path(a.ids).read_text().split(),Gaia,a.cache,a.log)
