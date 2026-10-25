"""Registered 2019 confirmation: audit -> commit/push input adapter and hashes -> score once.

No forecast-model fitting or tuning is available in this script. All predictions use cc12a0e's verified model bytes.
"""
from __future__ import annotations
import argparse
import inspect
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import joblib
import numpy as np
import pandas as pd
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis import s22b_data as D
from analysis import s22_data as F
from analysis import s22_metrics as M
from analysis.common import log_test_scoring
import importlib
P=importlib.import_module('analysis.22_regional')
ROOT=D.ROOT; LOCAL=D.LOCAL; TABLES=D.TABLES


def verify_frozen():
    raw=subprocess.check_output(['git','show','cc12a0e:outputs/tables/s22_model_manifest.csv'],cwd=ROOT)
    manifest=pd.read_csv(io.BytesIO(raw))
    for row in manifest.itertuples(index=False):
        assert F.sha(ROOT/row.path)==row.sha256,row.path
    return manifest


def freeze_inputs():
    """Audit first; save input/adapter hashes with no 2019 label or score construction."""
    verify_frozen(); audit=D.audit()
    paths=[ROOT/'analysis/22b_backward.py',ROOT/'analysis/s22b_data.py',ROOT/'analysis/s22b_fetch_weather.py']
    paths += sorted((ROOT/'data/static/phase3/s22b').glob('*'))
    paths += sorted(TABLES.glob('s22b_audit_*.csv'))
    paths += sorted(p for folder in ['taxi','rain','forecast','logs'] for p in (ROOT/'data/raw'/folder).glob('2019-*'))
    manifest=pd.DataFrame([dict(path=str(p.relative_to(ROOT)),sha256=F.sha(p),bytes=p.stat().st_size) for p in paths])
    manifest.to_csv(TABLES/'s22b_input_manifest.csv',index=False)
    (LOCAL/'freeze.json').write_text(json.dumps(dict(manifest_sha256=F.sha(TABLES/'s22b_input_manifest.csv'),
                        frozen_model_commit='cc12a0e',audit_only=True),indent=2))
    rows=['\n153. **2019 audit and adapter freeze, before any scoring.**',
      '    No step-22 model or transform was fitted or changed. All 72 cc12a0e hashes match.',
      '    November weather retrieval was resumed without repeating its already-saved taxi requests:',
      '    the original process was waiting through repeated missing-archive errors. The separate',
      '    s22b_fetch_weather.py client returns immediately on non-retriable 400/404/410 responses;',
      '    transient 429/5xx retries, parsing and file formats are unchanged. The original pipeline',
      '    source stays hash-frozen. The November log identifies weather-only request counts.',
      '    The date/availability weather adapter executes the frozen feature function with its raw start date',
      '    changed from March 2022 to January 2019. Entirely unobserved archive days supply NaN depths',
      '    rather than fabricated zeros. Scheduled 2019 calendar bits are supplied separately;',
      '    all other feature mathematics, trailing levels, weather gates and transformations are unchanged.',
      '    Public holidays follow the MOM release archived by NAS; the school vacations follow the MOE',
      '    15 August 2018 release reproduced under its author byline, with official URL and retrieval',
      '    limitations documented in data/static/phase3/s22b/calendar_sources.md. No extra school-only',
      '    dates are added, matching the frozen four-vacation convention. Audit metrics follow:']
    for k,v in audit.items():rows.append(f'    - {k}: {v}')
    rows+=['    Regime/glitch diagnostics are not new exclusions or fitted forecast levels. Only invalid',
      '    snapshot statuses/offsets are excluded, as registered. The input and executable adapter',
      '    SHA-256 hashes are frozen in s22b_input_manifest.csv; its own SHA-256 is',
      f'    `{F.sha(TABLES/"s22b_input_manifest.csv")}`. Commit and push before opening labels or scores.']
    with (ROOT/'outputs/decisions.md').open('a') as f:f.write('\n'.join(rows)+'\n')
    print('Audit/input freeze ready. Commit and push before score.',flush=True)


def draw_figure(gains,nstorms):
    source=inspect.getsource(M.figure)
    source=source.replace('s22_weather_gain','s22b_weather_gain').replace('Step 22:','Step 22b:')
    source=source.replace('fresh October holdout','backward 2019 holdout').replace('1–24 Oct 2026','1 Jan–31 Dec 2019')
    namespace=vars(M).copy()
    exec(compile(source,'<step22b figure labels only>','exec'),namespace)
    namespace['figure'](gains,nstorms)


def report(stats,gains,onsets,commit,predictions):
    q=gains[gains.model.eq('lightgbm')&gains.unit.eq('Pooled')&gains.subset.eq('storm')&gains.target.isin(['T1','T2_15'])].copy()
    q['numerical_rule']=np.where(q.target.eq('T1'),q.gain>=5,q.gain>=.02)&q.lo.gt(0)
    q['adequate_storm_count']=len(onsets)>=8
    q['primary_outcome']=q.horizon.eq(60)&q.target.eq('T2_15')
    q['materiality_confirmed']=q.numerical_rule&q.adequate_storm_count
    q.to_csv(TABLES/'s22b_materiality.csv',index=False)
    primary=q[q.primary_outcome].iloc[0]
    primary_pass=bool(primary.materiality_confirmed);omnibus=bool(q.materiality_confirmed.any())
    support=stats[stats.model.eq('persistence')&stats.weather.eq(0)]
    support.to_csv(TABLES/'s22b_support.csv',index=False)
    rates=pd.read_csv(TABLES/'s22b_audit_summary.csv').set_index('metric').value
    s=['\n## Step 22b: confirmatory backward holdout in 2019 (decisions 152-153)\n',
       f'- Model source: cc12a0e. Adapter/input freeze `{commit}` was pushed before scoring.',
       '- Registration f8dfda4 was pushed before downloading. No refitting, tuning or 2019-based',
       '  imputation, probability calibration, residual CDF, alert workload or seasonal pattern changes.',
       f'- 2019 storm onsets: **{len(onsets)}**. Power rule >=8: **{len(onsets)>=8}**.',
       f'- Primary confirmation (60-minute pooled storm T2, 15% shortfall): **{primary_pass}**.',
       f'  PR-AUC without/with weather: {primary.no_weather:.6f}/{primary.with_weather:.6f};',
       f'  gain {primary.gain:+.6f}, day-block 95% CI [{primary.lo:+.6f}, {primary.hi:+.6f}].',
       f'- Original step-22 omnibus materiality rule: **{omnibus}**. All primary-label storm contrasts:']
    for row in q.itertuples():
        s.append(f'  - {row.horizon} min {row.target}: gain {row.gain:+.6f}, CI [{row.lo:+.6f},{row.hi:+.6f}]; n={row.n}, defined draws={row.defined_bootstraps}.')
    s+=['- Audit before scores (full tables s22b_audit_*.csv):']
    for k in ['requested','expected','usable','invalid_status','bad_offsets','glitch_flags','regimes','short_spells',
              'unique_gauges','min_daily_gauges','max_daily_gauges','complete_gauge_days','gauge_days',
              'days_without_rain_readings','days_without_complete_gauges','days_without_forecast_records',
              'forecast_issues','forecast_area_records_issued_at_or_after_end','issued_at_or_after_end','naive_future_issue_rejections','strict_forecast_slots','unavailable_forecast_slots']:
        s.append(f'  - {k}: {rates.loc[k]}')
    s+=['- Forecast issue times are never replaced by validity times. Naive validity-only candidates with',
        '  issue>=t are rejected. The latest actually issued forecast must also be valid at t; otherwise',
        '  saved training imputation supplies missing weather. Eleven entirely unobserved rain days supply',
        '  unknown five-minute depths, not dry zeros, before the unchanged frozen rolling windows.',
        '  All raw issue and slot counts and the four',
        '  prespecified sample days are reported. Missing archive forecasts can limit this era comparison.',
        '- Counts and labels use the unchanged seasonal pattern with the trailing seven-day level frozen',
        '  at issue time. The first January observations provide wash-in (minimum 48 past snapshots);',
        '  unavailable issue/target observations and exact lags are not filled using future data.',
        '- Six units overlap (Central Area within Central Region); day resampling keeps them together.',
        '  The 1,000 draws and undefined-draw handling are exactly step 22. CIs are pointwise; multi-day',
        '  dependence and this single historical year limit inference.',
        '- 2019 had a different fleet and market, and different archive coverage. A failed confirmation',
        '  may reflect an era shift; it does not revise frozen 2022-26 associations or earlier forecasts.',
        '  Vacant taxis measure supply only. The optional heavy-rain regression was not undertaken.',
        '- All 896 model/weather/horizon/target/unit/subset rows and 448 paired gains are in s22b_metrics.csv',
        '  and s22b_weather_gains.csv; s22b_support.csv includes observed/expected counts, base rates,',
        '  alert counts and sample days. One figure: s22b_weather_gain.png/.svg.']
    with (ROOT/'outputs/phase2_progress.md').open('a') as f:f.write('\n'.join(s)+'\n')
    sample=support[support.target.eq('T1')&support.horizon.eq(60)&support.unit.eq('Pooled')&support.subset.eq('all')].iloc[0]
    text=['### Regional storm forecasting: backward holdout 2019 (step 22b)\n',
      'The unchanged step-22 models (cc12a0e) are scored once on 2019, after a separate registration,',
      f'audit and pushed input freeze. There are {len(onsets)} qualifying storm onsets (minimum eight required).',
      f'Primary 60-minute storm PR-AUC is {primary.no_weather:.4f} without and {primary.with_weather:.4f} with weather:',
      f'gain {primary.gain:+.4f}, 95% day-block CI [{primary.lo:+.4f},{primary.hi:+.4f}].',
      f'Primary confirmation: **{primary_pass}**; original omnibus materiality: **{omnibus}**.',
      f'The pooled all-time target averages {sample.mean_vacant:.1f} observed/{sample.mean_expected:.1f} expected vacant taxis (overlapping units).',
      f'Archive audit: {rates.loc["naive_future_issue_rejections"]} validity-only forecast candidates have not yet been issued;',
      f'{rates.loc["unavailable_forecast_slots"]} half-hours have no eligible issued, still-valid forecast and use frozen imputation.',
      '2019 had a different fleet and market, so a failed confirmation may reflect an era shift.',
      'All combinations and audit problems are reported in `s22b_*.csv`; no frozen result or model changes.\n']
    p=ROOT/'outputs/summary.md';old=p.read_text();assert '### Regional storm forecasting: backward holdout 2019' not in old
    p.write_text(old.replace('## 4. Caveats','\n'.join(text)+'\n## 4. Caveats'))


def score():
    verify_frozen()
    assert (LOCAL/'freeze.json').exists() and not (LOCAL/'SCORED.json').exists()
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()
    subprocess.run(['git','fetch','origin','main'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert commit==subprocess.check_output(['git','rev-parse','origin/main'],cwd=ROOT,text=True).strip()
    frozen=json.loads((LOCAL/'freeze.json').read_text())
    assert F.sha(TABLES/'s22b_input_manifest.csv')==frozen['manifest_sha256']
    for row in pd.read_csv(TABLES/'s22b_input_manifest.csv').itertuples(index=False):assert F.sha(ROOT/row.path)==row.sha256,row.path
    record=dict(commit=commit,description='backward holdout 2019, scored once',started=pd.Timestamp.now(tz='Asia/Singapore').isoformat())
    fd=os.open(LOCAL/'SCORED.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    with os.fdopen(fd,'w') as f:json.dump(record,f,indent=2)
    log_test_scoring('22b_backward.py --part score','backward holdout 2019, scored once',analysis='step 22b',
                     note=f'Frozen step-22 models cc12a0e; no refitting/tuning; pushed adapter/input freeze {commit}')
    c=D.raw_counts();w=D.historical_weather()
    ws=w[w.unit.eq('Central')]
    candidates=ws[(ws.onset_share>=.25)&(ws.onset_gauges>=20)].ts.tolist()
    onsets=[]
    for t in candidates:
        if not onsets or (t-onsets[-1])>=pd.Timedelta('180min'):onsets.append(t)
    pd.DataFrame({'onset':onsets}).to_csv(TABLES/'s22b_storm_onsets.csv',index=False)
    pattern=joblib.load(F.LOCAL/'pattern.joblib');rows=[];availability=[]
    for h in (30,60):
        d=D.features(c,w,pattern,h);d['storm']=False
        for t in onsets:d.loc[d.ts.between(t-pd.Timedelta('60min'),t+pd.Timedelta('120min')),'storm']=True
        availability.append(dict(horizon=h,usable_issue_unit_pairs=len(d),first_issue=str(d.ts.min()),last_issue=str(d.ts.max()),
             floor_count=int(d.target_count.lt(1).sum()),storm_issue_unit_pairs=int(d.storm.sum()),
             onsets_with_usable_pairs=sum(d.ts.between(t-pd.Timedelta('60min'),t+pd.Timedelta('120min')).any() for t in onsets)))
        for target in P.TARGETS:
            a=d[['ts','unit','storm','Y','expected_now','target_count','target_expected']].copy()
            a['horizon']=h;a['target_name']=target;a['truth']=P.label(d,target)
            for weather in (False,True):
                for kind in ('persistence','seasonal','linear','lightgbm'):
                    name=f'{h}_{int(weather)}_{kind}' if kind in ('persistence','seasonal') else f'{h}_{target}_{int(weather)}_{kind}'
                    model=joblib.load(F.LOCAL/f'{name}.joblib')
                    a[f'{kind}_{int(weather)}']=P.baseline_predict(model,d,target) if kind in ('persistence','seasonal') else P.predict(model,d)
            rows.append(a)
        print('Predicted horizon',h,'pairs',len(d),flush=True)
    predictions=pd.concat(rows,ignore_index=True);predictions.to_parquet(LOCAL/'predictions.parquet',index=False)
    pd.DataFrame(availability).to_csv(TABLES/'s22b_scoring_support.csv',index=False)
    stats,gains=M.evaluate(predictions)
    stats.to_csv(TABLES/'s22b_metrics.csv',index=False);gains.to_csv(TABLES/'s22b_weather_gains.csv',index=False)
    draw_figure(gains,len(onsets));report(stats,gains,onsets,commit,predictions)
    record.update(completed=pd.Timestamp.now(tz='Asia/Singapore').isoformat(),storms=len(onsets),prediction_sha256=F.sha(LOCAL/'predictions.parquet'))
    (LOCAL/'SCORED.json').write_text(json.dumps(record,indent=2))
    pd.DataFrame([record]).to_csv(TABLES/'s22b_scoring_record.csv',index=False)
    print(json.dumps(record,indent=2),flush=True)


def main():
    a=argparse.ArgumentParser();a.add_argument('--part',choices=['audit','score'],required=True);choice=a.parse_args().part
    freeze_inputs() if choice=='audit' else score()

if __name__=='__main__':main()
