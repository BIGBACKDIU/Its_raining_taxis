"""Build an offline HTML research story from saved results only. No estimation or scoring."""
from pathlib import Path
import base64,hashlib,json,re
import pandas as pd
import numpy as np
from pipeline.grid import to_xy
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/story';SOURCE=ROOT/'story';HASHES={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(name):
 p=ROOT/'outputs/tables'/f'{name}.csv';HASHES[str(p.relative_to(ROOT))]=sha(p);return pd.read_csv(p)
def records(t):return json.loads(t.to_json(orient='records',double_precision=15))
def main():
 OUT.mkdir(exist_ok=True)
 data={}
 for relative in ['outputs/tables/audit_summary.json','outputs/summary.md','outputs/presentations/graph_coverage.json']:
  HASHES[relative]=sha(ROOT/relative)
 data['effects']=records(read('effects_main').query("model in ['abs','share'] and term in ['light','moderate','heavy']"))
 data['radar']=records(read('radar_effects').query("model=='abs' and dry_threshold_mmh==0 and term in ['light','moderate','heavy']"))
 data['radarCentral']=records(read('radar_central').query("group=='Central Area' and dry_threshold_mmh==0"))
 data['event']=records(read('effects_event_study').query("model=='event_abs'"))
 data['approach']=records(read('effects_approach').query("model=='abs' and term=='ring_heavier_owndry'"))
 data['dose']=records(read('dose_spline_curve').query("model=='abs'"))
 data['duration']=records(read('dose_duration_hangover').query("model=='abs' and part=='duration' and term.str.startswith('heavy_wet')"))
 data['after']=records(read('dose_duration_hangover').query("model=='abs' and term.str.startswith('dry_')"))
 data['absolute']=records(read('rain_hit_absolute_all'))
 data['share']=records(read('rain_hit_share_all'))
 data['places']=records(read('rain_hit_top30_absolute').head(12))
 assert all(r['expected_vacant_heavy']>=4 and r['abs_q']<.10 for r in data['places'])
 assert all(len(data[key])==374 and len({r['cell'] for r in data[key]})==374 for key in ['absolute','share'])
 names=read('names_cells');data['cells']=records(names[['cell','land','eligible']])
 coast=ROOT/'data/static/sg_map.json';HASHES[str(coast.relative_to(ROOT))]=sha(coast)
 data['land']=[np.round(np.array(to_xy(np.array(r)[:,0],np.array(r)[:,1])).T/1000,4).tolist() for r in json.loads(coast.read_text())['land']]
 storm=ROOT/'outputs/figures/deck/data/deck_storm_peak.csv';HASHES[str(storm.relative_to(ROOT))]=sha(storm);data['storm']=records(pd.read_csv(storm))
 playback=ROOT/'outputs/story/data/storm_2023-07-20.csv'
 metadata=playback.with_suffix('.json')
 for path in [playback,metadata]:HASHES[str(path.relative_to(ROOT))]=sha(path)
 replay=pd.read_csv(playback)
 assert sha(playback)==json.loads(metadata.read_text())['export_sha256']
 assert len(replay)==5610 and not replay.duplicated(['ts','cell']).any()
 data['stormFrames']=[{'time':str(ts),'rows':records(group.drop(columns='ts'))} for ts,group in replay.groupby('ts',sort=True)]
 data['island']=records(read('spillover_islandwide_share'))
 plan=read('planning_rain_losses');plan=plan[plan.condition.str.startswith('NEA') & (plan.day=='weekday')]
 order=plan.groupby('planning_area').abs_loss_taxis_per_half_hour.max().sort_values(ascending=False).head(10).index
 data['planning']=records(plan[plan.planning_area.isin(order)]);data['planningOrder']=list(order)
 data['factors']=records(read('factors_panel_interactions').query("model=='abs'"))
 data['forecast']=records(read('forecast_eval_both_labels').query("analysis=='primary' and scale=='1km' and label_version=='issue-time' and subset=='all' and h in [30,60]"))
 hp=ROOT/'outputs/figures/deck/data/deck_holdout_gain.csv';HASHES[str(hp.relative_to(ROOT))]=sha(hp);data['holdout']=records(pd.read_csv(hp))
 data['morning']=records(read('morning_forecast_value'))
 data['lead']=records(read('forecast_eval_lead_both_labels').query("analysis=='primary' and scale=='1km' and label_version=='issue-time' and model=='lgb_no_weather'"))
 data['policy']=records(read('policy_diagnosis').query("split=='test'"))
 data['conformal']=records(read('forecast_conformal').query("h==30 and model=='lgb_no_weather' and subset=='test all'"))
 data['simulation']=[{'name':'Simulator v1','passed':int(read('sim_plausibility').storms_passed.max())},{'name':'Simulator v2 · roads','passed':int(read('sim2_plausibility').storms_passed.max())},{'name':'Rain-effect benchmark','passed':int(read('sim2_diagnosis_summary').query("period=='test'").stat_passes.iloc[0])}]
 labels={
 'audit_unusual_days':('Feed outages and unusual days','Data checks'),'feed_regimes':('Feed coverage over time','Data checks'),
 'desc_profile_rain_bands':('Supply by time of day and rain','Supply'),'desc_maps_dry_heavy':('Dry and heavy-rain supply maps','Supply'),
 'desc_rain_band_frequency':('How often each rain band occurs','Data checks'),'desc_storm_2023-07-20_peak':('The 20 July 2023 storm snapshot','Supply'),
 'desc_trend_vs_fleet':('Supply, fleet size and street-hail trips','Supply'),'effects_main':('Rain across three specifications','Rain effects'),
 'effects_event_study':('Supply around rain onset','Rain effects'),'effects_approach_forecast':('Approaching rain and issued forecasts','Rain effects'),
 'effects_interactions':('Rush hours, weekends and years','Rain effects'),'effects_by_regime':('Results across feed regimes','Rain effects'),
 'effects_robustness':('Specification checks','Rain effects'),'inference_permutation':('Permutation checks','Data checks'),
 'inference_hotspots':('FDR hotspots: ratio statistic','Places'),'risk_odds':('Odds of low or zero supply','Places'),
 'risk_vulnerability':('Low-availability risk map','Places'),'risk_types':('Descriptive rain-response groups','Places'),
 'forecast_pr_auc':('Forecast PR-AUC by model','Forecasting'),'forecast_topk_both_labels':('Precision under both labels','Forecasting'),
 's1_weather_gain':('Weather gain across scales and labels','Forecasting'),'planning_forecast_rain':('Weekday planning gaps','Planning'),
 'policy_diagnosis':('Constraints on repositioning','Planning'),'policy_targeting':('Targeting sensitivity','Planning'),
 'sim_heldout_storms':('Simulation v1 on held-out storms','Simulation'),'names_rain_hit_map':('Named heavy-rain losses','Places'),
 'minutes_to_taxi_maps':('Road access to vacant supply','Places'),'dry_supply_by_band':('Dry-weather supply geography','Supply'),
 'taxi_deserts_map':('Dry-weather supply per resident','Places'),'factors_contrasts':('Place characteristics: panel model','Places'),
 'factors_shap':('Place characteristics: random forest','Places'),'dose_intensity_hangover':('Intensity and after-rain associations','Rain effects'),
 'mrt_did_event_study':('New MRT stations: failed pre-trends','Places'),'fleet_trend':('Fleet size and monthly associations','Supply'),
 'spillover_islandwide_map':('Island-wide rain and share changes','Places'),'stands_predicted_sensitivity':('Predicted rain sensitivity','Places'),
 'sim2_diagnosis':('Why the simulator fails the realism rule','Simulation'),'sim2_heldout_storms':('Simulation v2 on held-out storms','Simulation'),
 'radar_measurement_check':('Gauge and radar comparison','Data checks'),'s22_weather_gain':('October 2026: two storm onsets','Forecasting'),
 's22b_weather_gain':('2019 backward holdout: 49 onsets','Forecasting'),'s23_flows':('Minute flows: no matched controls','Simulation'),
 's23_speed':('Synthetic taxi-matching diagnostics','Simulation'),'s23_geography':('Pickup and drop-off estimates unavailable','Simulation')}
 manifest=json.loads((ROOT/'outputs/presentations/graph_coverage.json').read_text());gallery={}
 for row in manifest['coverage']:
  name=row['sourceGraph'];p=ROOT/'outputs/figures/deck/all'/f"{name}_part{row['part']}.png";HASHES[str(p.relative_to(ROOT))]=sha(p)
  if name not in gallery:gallery[name]={'id':name,'title':labels[name][0],'category':labels[name][1],'source':row['sourceFile'],'parts':[]}
  gallery[name]['parts'].append('data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode())
 assert len(gallery)==44 and sum(len(v['parts']) for v in gallery.values())==67
 notes_path=SOURCE/'evidence_notes.json';HASHES[str(notes_path.relative_to(ROOT))]=sha(notes_path)
 evidence_notes=json.loads(notes_path.read_text());assert set(evidence_notes)==set(gallery)
 for name,note in evidence_notes.items():gallery[name].update(note)
 data['gallery']=list(gallery.values())
 data['aliases']={48022:'Changi T3',48023:'Changi T1 / Jewel',33014:'Lau Pa Sat',34014:'Marina Bay Sands',32016:'Dhoby Ghaut',34017:'Lavender',33016:'Victoria',34016:'Nicoll',33015:'City Hall'}
 data['sources']=HASHES
 fonts=[]
 for family,folder,weights in [('Poppins','poppins',[('Regular',400),('Medium',500),('SemiBold',600)]),('Anton','anton',[('Regular',400)])]:
  for filename,weight in weights:
   p=ROOT/f'assets/fonts/{folder}/{family}-{filename}.ttf';HASHES[str(p.relative_to(ROOT))]=sha(p)
   fonts.append(f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};font-display:swap;src:url(data:font/ttf;base64,{base64.b64encode(p.read_bytes()).decode()}) format('truetype')}}")
 template=(SOURCE/'template.html').read_text();css=(SOURCE/'story.css').read_text()+'\n'+(SOURCE/'presentation.css').read_text();js=(SOURCE/'story.js').read_text()+'\n'+(SOURCE/'motion.js').read_text()
 html=template.replace('/*__FONTS__*/','\n'.join(fonts)).replace('/*__CSS__*/',css).replace('/*__DATA__*/','const DATA = '+json.dumps(data,separators=(',',':'),ensure_ascii=False).replace('</','<\\/')+';').replace('/*__JS__*/',js)
 assert len(re.findall(r'<figure[^>]*data-main-graph=',html))==15
 assert len(re.findall(r'data-scene=',html))==26
 assert len(re.findall(r'class="analysis-notes"',html))==15
 (OUT/'index.html').write_text(html)
 for relative,expected in HASHES.items():assert sha(ROOT/relative)==expected,relative
 (OUT/'provenance.json').write_text(json.dumps({'presentation_only':True,'main_graphs':15,'presentation_scenes':26,'storm_frames':len(data['stormFrames']),'appendix_graphs':44,'appendix_panels':97,'appendix_cards':67,'source_hashes':HASHES,'html_sha256':sha(OUT/'index.html'),'bytes':(OUT/'index.html').stat().st_size},indent=2)+'\n')
 print('Built',OUT/'index.html',f'({(OUT/"index.html").stat().st_size:,} bytes); 15 main graphs, 44 appendix graphs; frozen inputs unchanged.')
if __name__=='__main__':main()
