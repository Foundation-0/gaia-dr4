"""Join cached TIC/DR2 and neighbourhood CSVs without dropping unmatched targets."""
import csv,json,argparse
from collections import defaultdict

def join(targets,neighbours):
    matches=defaultdict(list)
    for r in neighbours:
        matches[r['dr2_source_id']].append(r)
    out=[]
    for t in targets:
        ms=matches.get(t['dr2_source_id'],[])
        for m in ms or [{}]:
            out.append(dict(t,**{k:v for k,v in m.items() if k!='dr2_source_id'},match_count=len(ms),match_status='ambiguous' if len(ms)>1 else 'matched' if ms else 'unmatched'))
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('targets');p.add_argument('neighbourhood');p.add_argument('output');a=p.parse_args()
    with open(a.targets) as f: ts=list(csv.DictReader(f))
    with open(a.neighbourhood) as f: ns=list(csv.DictReader(f))
    rows=join(ts,ns)
    with open(a.output,'w') as f: json.dump(rows,f,indent=2)
