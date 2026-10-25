"""Resume November weather without repeating taxi requests or retrying non-retriable 4xx archives.

The original pipeline files stay hash-frozen. Requests, parsing, output schema and retries for transient
errors are otherwise the existing pipeline. This is download handling only, before input audit/scoring.
"""
from __future__ import annotations
import json
import random
import time
from pathlib import Path
import sys
import requests
import pandas as pd
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.sources import Client
from pipeline.fetch_month import fetch_weather,ERRORS


class ArchiveClient(Client):
    def get_json(self,url,params=None):
        for attempt in range(self.tries):
            self._bump('calls')
            try:
                r=self._session().get(url,params=params,timeout=self.timeout)
                if r.status_code in (400,404,410):
                    self._bump('failed')
                    return None
                if r.status_code==429 or r.status_code>=500:
                    self._bump('rate_limited' if r.status_code==429 else 'retries')
                    time.sleep(min(60,2**attempt)+random.random())
                    continue
                r.raise_for_status();self._bump('ok');return r.json()
            except (requests.RequestException,ValueError):
                self._bump('retries');time.sleep(min(60,2**attempt)+random.random())
        self._bump('failed');return None


def main():
    month='2019-11';out=Path('data/raw');client=ArchiveClient();start=time.time()
    weather=fetch_weather(client,month,out,4)
    sn=pd.read_csv(out/'taxi'/f'{month}_snapshots.csv.gz',parse_dates=['req_ts','act_ts'])
    log=dict(month=month,end_date=None,snapshots=len(sn),snapshots_ok=int(sn.status.eq('ok').sum()),
             median_taxis=float(sn.loc[sn.status.eq('ok'),'n_points'].median()),
             median_offset_min=float(((sn.act_ts-sn.req_ts).dt.total_seconds()/60).median()),
             resumed_weather_only=True,nonretriable_4xx_fail_fast=True,
             note='Original taxi files retained. Original November month job was interrupted before completion; client counts below cover resumed weather only.',
             weather_seconds=round(time.time()-start,1),workers=4,client=client.stats,**weather,errors=ERRORS[:50])
    (out/'logs'/f'{month}.json').write_text(json.dumps(log,indent=2,default=str))
    print(json.dumps(log,indent=2,default=str),flush=True)

if __name__=='__main__':main()
