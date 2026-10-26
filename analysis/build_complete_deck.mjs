/** Complete project deck using the supplied editable reference and frozen chart geometry. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const ROOT=process.cwd(),BUILD=path.join(ROOT,'.deck-build'),OUT=path.join(ROOT,'outputs/presentations');
const SKILL='/Users/User/.codex/plugins/cache/openai-primary-runtime/presentations/26.1022.11436/skills/presentations';
const RUNTIME_NODE_MODULES=process.env.RUNTIME_NODE_MODULES||'/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
process.env.RUNTIME_NODE_MODULES=RUNTIME_NODE_MODULES;
const {importRuntimeModule}=await import(pathToFileURL(path.join(SKILL,'container_tools/runtime_helpers.mjs')));
const {PresentationFile,FileBlob}=await importRuntimeModule('@oai/artifact-tool');
const {GlobalFonts,createCanvas}=await importRuntimeModule('@napi-rs/canvas');
for(const name of ['Regular','Medium','SemiBold'])if(!GlobalFonts.registerFromPath(path.join(ROOT,`assets/fonts/poppins/Poppins-${name}.ttf`)))throw Error('Poppins registration failed');
if(!GlobalFonts.registerFromPath(path.join(ROOT,'assets/fonts/anton/Anton-Regular.ttf')))throw Error('Anton registration failed');
const ctx=createCanvas(1,1).getContext('2d');
const reference=process.argv[2]||"/Users/User/Downloads/It's Raining Taxis.pptx";
const p=await PresentationFile.importPptx(await FileBlob.load(reference));
const main=[...p.slides.items];
if(main.length!==23)throw Error('Expected the supplied 23-slide reference');
const graphics=JSON.parse(await fs.readFile(path.join(BUILD,'graphics.json'),'utf8'));
const C={navy:'#14295B',blue:'#2C5EAA',light:'#8FB8F2',pale:'#DCE6F4',red:'#C0453C',ink:'#14203A',muted:'#5A6683',grid:'#E4EAF4',bg:'#FBFCFE'};
const meta={
 audit_unusual_days:['Feed outages and unusual days','Excluded days follow the saved audit. No new exclusions or model fitting.'],
 feed_regimes:['The public feed changes coverage','Coverage regimes need explicit controls in comparisons over time.'],
 desc_profile_rain_bands:['Supply patterns by time and rain','Ratios use each cell’s expected supply. Shaded bands are saved day-bootstrap intervals.'],
 desc_maps_dry_heavy:['Dry and heavy-rain supply geography','Count maps retain taxi units. Percentage changes use the common ±40% scale.'],
 desc_rain_band_frequency:['Rain exposure in the analysed sample','Rain categories use the registered 30-minute gauge window.'],
 desc_storm_2023_07_20_peak:['A storm snapshot on 20 July 2023','09:30 Singapore time. Count ratios are descriptive comparisons to saved expected supply.'],
 desc_trend_vs_fleet:['Observed supply and fleet size over time','The feed measures public vacant supply and its coverage can change.'],
 effects_main:['Rain associations across specifications','Absolute, share and citywide-offset specifications retain their saved estimates and CIs.'],
 effects_event_study:['Supply around local rain onset','Reference: 30 minutes before onset. Recovery means intervals include zero, not exact restoration.'],
 effects_approach_forecast:['Nearby rain and issued forecasts','The local cell remains dry in the approaching-rain comparison. Association does not identify the mechanism.'],
 effects_interactions:['Rain associations differ across conditions','Differences between groups use the saved interaction models.'],
 effects_by_regime:['Associations across feed regimes','Regime results differ in magnitude. A pooled result does not establish stability in every regime.'],
 effects_robustness:['Specification and measurement checks','Use the saved point estimates and confidence intervals to judge each check.'],
 inference_permutation:['The permutation check','Exchangeability is an assumption of the supporting permutation scheme.'],
 inference_hotspots:['The FDR hotspot check','Ratio-statistic estimates and BH q-values. This is a different design from the cell Poisson map.'],
 risk_odds:['Risk of low or zero vacant supply','Odds ratios describe relative odds, not percentage changes in vacant taxi counts.'],
 risk_vulnerability:['Where low-availability risk increases','Percentage-point changes in low-availability risk are not percentage changes in taxi counts.'],
 risk_types:['Descriptive rain-response groups','The groups summarise saved response patterns, not taxi-driver behaviour.'],
 forecast_pr_auc:['Forecast discrimination by model','Saved test-year scores. Additional uses and label checks are disclosed in the scoring log.'],
 forecast_topk_both_labels:['Forecast precision under both labels','Nineteen alerts per half-hour. Label versions have different information sets.'],
 s1_weather_gain:['Weather gain across scales and labels','All registered secondary comparisons appear. None reaches the saved materiality rule.'],
 planning_forecast_rain:['Weekday planning gaps by area and time','Top 15 areas from the original planning figure. Negative gaps mean more taxis than expected.'],
 policy_diagnosis:['What the repositioning constraints cost','Targeting success measures selected cells, not passengers served or operational benefits.'],
 policy_targeting:['The saved repositioning targeting check','Travel times, staging and available CDG share are assumptions in the plan.'],
 sim_heldout_storms:['Simulation v1 on held-out storms','Simulation only. No setting passes the unchanged overall plausibility rule.'],
 names_rain_hit_map:['Named heavy-rain losses','Names meet the expected-count and q-value filters. Percentage map scales are capped at ±40%.'],
 minutes_to_taxi_maps:['Road access to vacant supply','Modelled minutes to a vacant taxi are not observed passenger waiting times.'],
 dry_supply_by_band:['Dry-weather supply by time band','These are dry snapshots. Supply geography does not establish passenger demand.'],
 taxi_deserts_map:['Dry-weather supply relative to residents','Residents use the saved areal allocation. The feed has no passenger-demand measure.'],
 factors_contrasts:['Place characteristics in the panel model','Central Area is the consistent finding. Other designs do not agree on all traits.'],
 factors_shap:['Place characteristics in the random forest','Spatial-block performance is weak. SHAP explains this fitted model, not causal mechanisms.'],
 dose_intensity_hangover:['Intensity and the after-rain association','The after-rain reference is cells dry for at least six hours.'],
 mrt_did_event_study:['New MRT openings and vacant supply','Pre-trends fail. The result cannot support a causal MRT-opening interpretation.'],
 fleet_trend:['Fleet size and monthly rain associations','Meta-regression has the registered coverage control and HAC errors. No extrapolation.'],
 stands_predicted_sensitivity:['Predicted sensitivity across analysed cells','Random-forest predictions reuse the saved training transform. Unanalysed cells use the no-data colour.'],
 spillover_islandwide_map:['Island-wide rain and relative share','Gaining share can coexist with losing taxis. Counts and percentages need separate interpretation.'],
 sim2_diagnosis:['Why the simulator fails the realism rule','Level, timing and spatial diagnostics use saved outputs. The plausibility rule stays unchanged.'],
 sim2_heldout_storms:['Simulation v2 on held-out storms','Illustration only. Best v2 setting passes three of ten storms, below the registered rule.'],
 radar_measurement_check:['Gauge and radar measurement check','Same-sample comparisons use saved radar tables. Gauge results remain the headline.'],
 s22_weather_gain:['Regional forecasting on October 2026','Two storm onsets fail the minimum-eight-onset power rule. Storm gains remain descriptive.'],
 s22b_weather_gain:['Backward holdout on 2019','Forty-nine onsets. The primary 60-minute PR-AUC gain is positive but below +0.02.'],
 s23_flows:['Minute-level flows have no matched comparison','The fixed sampling rule produces two storm days and zero matched dry days. No flow effect is estimated.'],
 s23_speed:['Anonymous matching cannot recover taxi identity','Synthetic matching diagnostics do not measure real traffic speeds.'],
 s23_geography:['Pickup and drop-off effects are unavailable','No matched dry controls means no estimated return ratio, relocation effect or place ranking.'],
};
meta['desc_storm_2023-07-20_peak']=meta.desc_storm_2023_07_20_peak;
function replace(slide,from,to){for(const sh of slide.shapes.items){const text=String(sh.text);if(text.includes(from))sh.text.replace(from,to);}}
function text(slide,value,box,size=20,color=C.ink,family='Poppins',bold=false){
 const sh=slide.shapes.add({geometry:'textbox',position:box,fill:'none',line:{fill:'none',width:0}});
 sh.text=value;sh.text.style={typeface:family,fontSize:size,color,bold,wrap:'none',insets:0,verticalAlignment:'top'};return sh;
}
function fitTitle(sh){ctx.font='53.33px Anton';const v=String(sh.text);const w=ctx.measureText(v).width;sh.text.style={typeface:'Anton',fontSize:Math.min(53.33,1100/w*53.33),color:C.navy,wrap:'none',insets:0};}
function chartFill(color,alpha=1){if(color==='none'||!color)return 'none';if(alpha>=.999)return color;const a=color.replace('#','');return `rgba(${parseInt(a.slice(0,2),16)},${parseInt(a.slice(2,4),16)},${parseInt(a.slice(4,6),16)},${alpha})`;}
function itemBounds(items,fontFloor=0){
 const boxes=items.flatMap(v=>{
  if(v.kind==='path'||v.kind==='image')return[v.box];
  if(v.kind==='text'){
   const font=Math.max(v.fontSize,fontFloor);ctx.font=`${v.bold?'600 ':''}${font}px Poppins`;const w=ctx.measureText(v.text).width;
   const shift=v.anchor==='middle'?w/2:v.anchor==='end'?w:0;
   if(Math.abs(v.rotation)>10)return [[v.x-font,v.y-w/2,v.x+font,v.y+w/2]];
   return[[v.x-shift,v.y-font*1.15,v.x-shift+w,v.y+font*.5]];
  }return[];
 });
 if(!boxes.length)return[0,0,1,1];return[Math.min(...boxes.map(b=>b[0])),Math.min(...boxes.map(b=>b[1])),Math.max(...boxes.map(b=>b[2])),Math.max(...boxes.map(b=>b[3]))];
}
async function draw(slide,items,frame,{bounds,minFont=0}={}){
 let b=bounds||itemBounds(items),scale=Math.min(frame.width/(b[2]-b[0]),frame.height/(b[3]-b[1]));
 if(!bounds&&minFont)for(let k=0;k<4;k++){b=itemBounds(items,minFont/scale);scale=Math.min(frame.width/(b[2]-b[0]),frame.height/(b[3]-b[1]));}
 const ox=frame.left+(frame.width-(b[2]-b[0])*scale)/2-b[0]*scale,oy=frame.top+(frame.height-(b[3]-b[1])*scale)/2-b[1]*scale;
 const mapMarkers=[];
 for(const it of items){
  if(it.kind==='path'){
   const[x0,y0,x1,y1]=it.box,w=x1-x0,h=y1-y0;if(w<.001&&h<.001)continue;
   const cmds=it.commands.map(c=>Object.fromEntries(Object.entries(c).map(([k,v])=>[k,Object.fromEntries(Object.entries(v).map(([key,value])=>[key,value-(key.startsWith('x')?x0:y0)]))])));
   slide.shapes.add({geometry:'custom',name:'Editable chart path',position:{left:ox+x0*scale,top:oy+y0*scale,width:Math.max(.01,w*scale),height:Math.max(.01,h*scale)},
    fill:chartFill(it.fill,it.alpha),line:{fill:it.stroke,width:it.stroke==='none'?0:Math.max(.2,it.strokeWidth*scale),style:it.dash?'dashed':'solid'},
    customPaths:[{width:Math.max(.01,w),height:Math.max(.01,h),commands:cmds}]});
  }else if(it.kind==='text'){
   const f=Math.max(minFont,it.fontSize*scale);ctx.font=`${it.bold?'600 ':''}${f}px Poppins`;const width=ctx.measureText(it.text).width+.5,height=f*1.8;
   let x=ox+it.x*scale,y=oy+it.y*scale;const left=it.anchor==='middle'?-width/2:it.anchor==='end'?-width:0;
   const top=-f*1.05,angle=it.rotation*Math.PI/180,cx=left+width/2,cy=top+height/2;
   const gx=x+cx*Math.cos(angle)-cy*Math.sin(angle),gy=y+cx*Math.sin(angle)+cy*Math.cos(angle);
   text(slide,it.text,{left:gx-width/2,top:gy-height/2,width,height,rotation:it.rotation},f,it.color,'Poppins',it.bold);
  }else if(it.kind==='mapMarker')mapMarkers.push({...it,x:ox+it.x*scale,y:oy+it.y*scale});
  else if(it.kind==='image'){
   const b=it.box;const image=slide.images.add({blob:Uint8Array.from(Buffer.from(it.data,'base64')).buffer,contentType:'image/png',alt:'Saved chart colour scale',position:{left:ox+b[0]*scale,top:oy+b[1]*scale,width:(b[2]-b[0])*scale,height:(b[3]-b[1])*scale},fit:'contain'});
   image.flipVertical=it.flipY;image.flipHorizontal=it.flipX;
  }
 }
 const placed=[];
 for(const it of mapMarkers){
  let x=it.x,y=it.y;
  for(let attempt=0;attempt<50;attempt++){
   if(placed.every(p=>Math.hypot(x-p.x,y-p.y)>=17))break;
   const angle=attempt*2.4,r=10+Math.floor(attempt/6)*5;x=it.x+Math.cos(angle)*r;y=it.y+Math.sin(angle)*r;
  }
  if(Math.hypot(x-it.x,y-it.y)>4)slide.shapes.add({geometry:'line',position:{left:Math.min(x,it.x),top:Math.min(y,it.y),width:Math.max(.1,Math.abs(x-it.x)),height:Math.max(.1,Math.abs(y-it.y))},line:{fill:C.navy,width:.6},flipVertical:(x-it.x)*(y-it.y)<0});
  slide.shapes.add({geometry:'ellipse',position:{left:x-8,top:y-8,width:16,height:16},fill:C.navy,line:{fill:C.bg,width:.5}});
  text(slide,it.text,{left:x-8,top:y-7,width:16,height:18},10,'#FFFFFF').text.alignment='center';placed.push({x,y});
 }
 return {scale,bounds:b};
}
function background(slide){slide.shapes.add({geometry:'roundRect',position:{left:85.33,top:202.4,width:1109.33,height:427},fill:C.bg,line:{fill:'none',width:0},borderRadius:18});}
function clean(slide,title,kicker='FULL GRAPH APPENDIX',foot=''){
 for(const im of [...slide.images.items])slide.images.deleteById(im.id);
 for(const sh of [...slide.shapes.items]){const top=sh.position.top;if(top>=190&&top<640)slide.shapes.deleteById(sh.id);}
 for(const sh of slide.shapes.items){
  const top=sh.position.top;
  if(top>120&&top<190){sh.text=title.toUpperCase();fitTitle(sh);}
  else if(top<120&&String(sh.text).trim())sh.text=kicker;
  else if(top>640&&String(sh.text).length>4){sh.text=foot;sh.text.style={typeface:'Poppins',fontSize:15,color:C.muted,wrap:'square',insets:0};sh.position={left:85.33,top:649,width:1030,height:56};}
 }
 background(slide);
}
const chunks=[];
for(const graph of graphics.charts){
 const perSlide=graph.components.some(c=>c.placeList?.length)||['effects_robustness','factors_shap','forecast_pr_auc'].includes(graph.name)?1:2;
 const sharedLegend=graph.components.find(c=>c.legendItems?.length)?.legendItems;
 if(sharedLegend)for(const c of graph.components)if(!c.legendItems?.length)c.legendItems=sharedLegend;
 if(graph.name==='policy_targeting')for(const c of graph.components)for(const item of c.items)if(item.kind==='text'&&item.text==='congestion')item.text='Traffic';
 if(graph.name==='factors_shap')for(const c of graph.components){
  const red=c.items.filter(i=>i.kind==='path'&&i.fill===C.red).sort((a,b)=>(b.box[2]-b.box[0])-(a.box[2]-a.box[0]));
  for(const it of red.slice(1))it.fill=C.navy;
 }
 for(let i=0;i<graph.components.length;i+=perSlide)chunks.push({graph,parts:graph.components.slice(i,i+perSlide),part:Math.floor(i/perSlide)+1,total:Math.ceil(graph.components.length/perSlide)});
}
// Make copies while the reference chart slide is still lightweight and unchanged.
const holdout=main[5].duplicate();holdout.moveTo(16);
const divider=main[22].duplicate();divider.moveTo(p.slides.items.length-1);
const appendix=[];
for(const chunk of chunks){const s=main[5].duplicate();s.moveTo(p.slides.items.length-1);appendix.push({slide:s,...chunk});}
// Targeted copy changes preserve the reference's editable elements and hierarchy.
replace(main[3],'Follow each square from 2 h before rain starts to 3 h after.','Follow each square from 60 min before rain starts to 180 min after.');
replace(main[3],'scored once on unseen data','evaluated on held-out data');
replace(main[3],'Data split once: fit Apr 2022 – Mar 2025 · tune Apr – Sep 2025 · test Oct 2025 – Sep 2026','Fixed windows: fit Apr 2022–Mar 2025; tune Apr–Sep 2025; test Oct 2025–Sep 2026. Repeated scoring is logged.');
replace(main[4],'RAIN TAKES TAXIS OFF THE STREET','RAIN IS ASSOCIATED WITH LOWER TAXI SUPPLY');
replace(main[5],'WE TRIED HARD TO BREAK IT','CHECKS SUPPORT THE MAIN ASSOCIATION');
replace(main[5],'Same answer with:','Checks include:');replace(main[5],'Each year','Across years');
replace(main[6],'orange = fewer','red = fewer');
replace(main[7],'IT STARTS BEFORE THE RAIN ARRIVES','LOWER SUPPLY CAN PRECEDE LOCAL RAIN');
replace(main[8],'ANY RAIN COUNTS. LONG RAIN HURTS MORE','LOWER SUPPLY WITH LIGHT AND LONG RAIN');
replace(main[8],'The first millimetre matters most.','A sharp association at low intensity.');
replace(main[9],'299 OF 374 SQUARES LOSE TAXIS IN HEAVY RAIN','HEAVY-RAIN LOSSES CLUSTER BY PLACE');
replace(main[10],'About 7 taxis per half-hour at each terminal, but only −8% to −16% because it holds so many.','About 7 fewer taxis per half-hour at each terminal: −8.5% and −15.9% of expected supply.');
replace(main[10],'Bayfront −36%, Dhoby Ghaut −35%, Raffles Place −31%.','Share changes: Bayfront −26.4%, Dhoby Ghaut −25.5%, Raffles Place −21.1%.');
replace(main[10],'orange bars','red bars');
replace(main[11],'NO SAFE HARBOUR IN ISLAND-WIDE RAIN','BROAD LOSSES IN ISLAND-WIDE RAIN');
replace(main[11],'There is no surplus area to pull drivers from. The lever is more drivers on the road, not moving them around.','Few cells gain taxis in absolute counts. Broad losses limit the headroom for repositioning.');
replace(main[12],'run about ','are about ');
replace(main[14],'OUR FORECASTS WORK. WEATHER ADDS NOTHING','FORECASTS IMPROVE; WEATHER ADDS LITTLE');
replace(main[14],'53% right','54.2% right');replace(main[14],'46% assuming','47.2% assuming');replace(main[14],'still 53%','still 54.2%');
replace(main[14],'Test year Oct 2025 – Sep 2026, scored once','Test year Oct 2025–Sep 2026; issue-time labels; repeated scoring disclosed');
replace(main[15],'Rain moves a square’s count by 5–15%, but counts already swing more than that every half hour. Current taxi numbers carry most of what rain would tell you.','Current taxi counts carry most forecasting skill in the tested models. Weather gains remain below the materiality rule at cell scale.');
for(const t of main[15].tables.items){t.cells.set(1,1,'max +0.0024 PR-AUC');t.cells.set(4,1,'+0.0087 [0.0008, 0.0171]');}
replace(main[16],'Weather can’t warn a dispatcher in minutes, but it can plan the day. Uses only what is known by 09:00.','The flexible model improves planning predictions using information known by 09:00. Regression is flat or worse.');
replace(main[16],'Flexible model, test year · 10.1% [9.4, 10.8] and 6.3% [4.9, 7.5] under two label definitions','Flexible model: 10.1% [9.4,10.8] and 6.3% [4.9,7.5]. Corrective refit and second test scoring disclosed.');
replace(main[17],'A RAIN-DAY PLAYBOOK FOR CDG','A CANDIDATE RAIN-DAY PLAYBOOK');
replace(main[17],'Plans improve 6–10%','Prediction deviance improves 6–10%');
replace(main[17],'Plan picks right 43% vs 28%','Selected cells: 44.2% vs 27.7%');
replace(main[17],'Get more drivers on the road. Don’t drain one area to fill another.','Broad losses limit repositioning. Extra supply would require an operational trial.');
replace(main[17],'Keep incentives running for 1–2 more hours.','Monitor supply after rain. Any incentive duration needs an operational trial.');
replace(main[17],'Each step rests on a result in this deck · supply associations, not demand','Candidate actions based on supply associations. Operational benefits have not been evaluated.');
replace(main[13],'So new taxi stands are not a rain fix.','Taxi-stand findings are not robust enough to justify a rain response.');
replace(main[18],'there’s no surplus','broad losses limit surplus');
replace(main[19],'A STORM SIMULATOR TO EXPLAIN, NOT PREDICT','A STORM SIMULATOR FOR EXPLORING ASSUMPTIONS');
replace(main[19],'rain that raises bookings, takes drivers off the road, or both','scenario-set bookings and off-duty rates');
replace(main[19],'4 of 10','3 of 10');replace(main[19],'held-out storms pass the realism check we set in advance. Our own rain effects score 3 of 10.','held-out storms pass for the best v2 setting. V1 reaches 4 of 10. Neither passes the overall rule.');
for(const t of main[20].tables.items){
 t.cells.set(1,1,'A disappearance can be a hire, booking or driver leaving service.');
 t.cells.set(2,1,'Observed traffic speeds are unavailable. Model road times are assumptions.');
 t.cells.set(3,1,'The feed has no duty-status field. Hires and duty exits remain mixed.');
 t.cells.set(4,1,'Spatial supply associations do not identify individual relocation.');
}
replace(main[20],'accuracy when we tracked taxis minute by minute: without taxi IDs it can’t be done.','synthetic link precision at 15–30 km/h. The strict sample also has zero matched dry days.');
replace(main[20],'Matching accuracy on synthetic test data at 15–30 km/h','Synthetic matching precision at 15–30 km/h');
replace(main[21],'test year scored once','repeated test scoring disclosed');
for(const t of main[21].tables.items)t.cells.set(1,0,'Heavy rain is associated with about 13% fewer vacant taxis');
replace(main[21],'Every threshold and pass rule was committed before the results it judges','Confirmatory rules were registered. Post-hoc checks and corrective re-scorings are disclosed.');
replace(main[22],'Rain reliably takes vacant taxis off the street, most in the CBD.','Heavy rain is associated with lower vacant supply, most in the Central Area.');
main[17].speakerNotes.text='Source: policy_diagnosis.csv, test split, policy with forecast-risk weights: issue-time precision 0.4416; all eligible candidate cells: 0.2770. Different numbers of selected cells; not a fixed-workload forecast comparison or evidence of passenger benefits.';
// Fit updated reference headings to their original title frames.
for(const [i,s] of main.entries())if(![0,16,22].includes(i))for(const sh of s.shapes.items)if(sh.position.top>120&&sh.position.top<190&&String(sh.text).length>5)fitTitle(sh);
for(const sh of main[16].shapes.items)if(sh.position.top>640&&sh.position.left<100)sh.position={...sh.position,width:1050};
const swaps={4:'deck_effects_main',5:'deck_radar_check',6:'deck_storm_peak',7:'deck_event_timeline',8:'deck_dose',9:'deck_where_map',10:'deck_places_bar',11:'deck_islandwide_map',12:'deck_planning_heatmap',14:'deck_forecast_bars'};
for(const [key,name] of Object.entries(swaps)){
 const s=main[Number(key)],image=s.images.items[0];if(!image)throw Error('Missing reference chart image');
 const frame={left:image.frame.left,top:image.frame.top,width:image.frame.width,height:image.frame.height};s.images.deleteById(image.id);
 const g=graphics.modern[name];await draw(s,g.items,frame,{bounds:[0,0,g.width,g.height]});
 s.speakerNotes.text=`Results: outputs/figures/deck/README.md and outputs/figures/deck/data/${name}.csv. Supply associations. ${name==='deck_holdout_gain'?'October has two onsets and is descriptive.':''}`;
}
clean(holdout,'Weather gain stays small or uncertain','Q3 · WEATHER GAIN ACROSS HOLDOUTS','PR-AUC gain. October has two onsets and remains descriptive under the registered power rule.');
await draw(holdout,graphics.modern.deck_holdout_gain.items,{left:100,top:213,width:1080,height:412},{bounds:[0,0,graphics.modern.deck_holdout_gain.width,graphics.modern.deck_holdout_gain.height]});
holdout.speakerNotes.text='Sources: forecast_eval_both_labels.csv; s22_materiality.csv; s22b_materiality.csv; s22_storm_onsets.csv. The 1 km maximum is a descriptive maximum across saved combinations.';
replace(divider,'THANK YOU','FULL GRAPH APPENDIX');replace(divider,'THREE THINGS TO REMEMBER','ALL SAVED PROJECT GRAPHS');
replace(divider,'−13%, −25% CBD','44 source graphs');replace(divider,'Rain reliably takes vacant taxis off the street, most in the CBD.','All unique saved analysis figures appear in the following slides.');
replace(divider,'Act early','Methods and caveats');replace(divider,'The drop starts before rain arrives. Plan from the morning forecast.','Extra panels retain diagnostics, weak results and failed designs.');
replace(divider,'Next: CDG data','Read as evidence');replace(divider,'Booking and driver data would show why taxis vanish.','Sources and interpretation notes accompany every graph.');replace(divider,'Questions?','The main project presentation ends before this appendix.');
function standardBar(slide,frame){
 const w=frame.width/80;
 for(let i=0;i<80;i++){
  const value=-40+(i+.5),target=value<0?C.red:C.blue,f=Math.min(1,Math.abs(value)/40),white=[255,255,255],b=target.slice(1).match(/../g).map(s=>parseInt(s,16));
  const fill='#'+white.map((v,k)=>Math.round(v*(1-f)+b[k]*f).toString(16).padStart(2,'0')).join('');
  slide.shapes.add({geometry:'rect',position:{left:frame.left+i*w,top:frame.top,width:w+.05,height:10},fill,line:{fill:'none',width:0}});
 }
 for(const value of [-40,-20,0,20,40])text(slide,String(value).replace('-','−'),{left:frame.left+(value+40)/80*frame.width-25,top:frame.top+14,width:50,height:27},15,C.muted).text.alignment='center';
 text(slide,'% vacant taxis vs normal',{left:frame.left-15,top:frame.top+43,width:frame.width+30,height:32},15,C.ink).text.alignment='center';
}
function legend(slide,items,frame){
 let x=frame.left,y=frame.top,last=null;
 for(const it of items){
  if(it.kind==='path'){const color=it.fill!=='none'?it.fill:it.stroke;if(color!=='none'&&color!==C.bg)last=color;}
  if(it.kind!=='text')continue;
  ctx.font='15px Poppins';const width=ctx.measureText(it.text).width;
  if(x>frame.left&&x+width+30>frame.left+frame.width){x=frame.left;y+=23;}
  if(last)slide.shapes.add({geometry:'rect',position:{left:x,top:y+7,width:17,height:5},fill:last,line:{fill:'none',width:0}});
  text(slide,it.text,{left:x+(last?24:0),top:y,width:width+2,height:24},15,C.ink);x+=width+(last?48:24);last=null;
 }
}
function linesFor(value,width,font=14.67){
 ctx.font=`${font}px Poppins`;const lines=[];let line='';
 for(const word of value.split(' ')){if(line&&ctx.measureText(line+' '+word).width>width){lines.push(line);line=word;}else line+=(line?' ':'')+word;}if(line)lines.push(line);return lines;
}
function placeList(slide,labels,start=224){
 let y=start;
 for(const label of labels){
  const match=label.match(/^(\d+)\s+(.*)$/),body=match[2];ctx.font='15px Poppins';const lines=[];let line='';
  for(const word of body.split(' ')){if(line&&ctx.measureText(line+' '+word).width>485){lines.push(line);line=word;}else line+=(line?' ':'')+word;}if(line)lines.push(line);
  const c=slide.shapes.add({geometry:'ellipse',position:{left:646,top:y,width:21,height:21},fill:C.navy,line:{fill:'none',width:0}});
  text(slide,match[1],{left:646,top:y+1,width:21,height:22},13,'#FFFFFF').text.alignment='center';
  text(slide,lines.join('\n'),{left:678,top:y,width:490,height:Math.max(25,lines.length*19)},15,C.ink);
  y+=Math.max(29,lines.length*19+5);
 }
}
function planningHeatmap(slide){
 const g=graphics.planning,max=Math.max(...g.values.flat()),x=460,y=219,w=110,h=24;
 for(let i=0;i<g.areas.length;i++){
  text(slide,g.areas[i],{left:240,top:y+i*h+1,width:205,height:25},15,C.ink).text.alignment='right';
  for(let j=0;j<5;j++){
   const value=g.values[i][j],f=Math.max(0,value)/max,stops=[C.pale,C.light,C.blue,C.navy],t=Math.min(2.999,f*3),k=Math.floor(t),mix=t-k,a=stops[k].slice(1).match(/../g).map(v=>parseInt(v,16)),b=stops[k+1].slice(1).match(/../g).map(v=>parseInt(v,16)),fill='#'+a.map((v,k)=>Math.round(v*(1-mix)+b[k]*mix).toString(16).padStart(2,'0')).join('');
   slide.shapes.add({geometry:'rect',position:{left:x+j*w,top:y+i*h,width:w,height:h},fill,line:{fill:C.bg,width:.3}});
   text(slide,(Math.abs(value)<.05?'0.0':value.toFixed(1).replace('-','−')),{left:x+j*w,top:y+i*h+1,width:w,height:h},15,f>.5?'#FFFFFF':C.ink).text.alignment='center';
  }
 }
 for(let j=0;j<5;j++)text(slide,g.bands[j].replace('-','–'),{left:x+j*w,top:y+15*h+8,width:w,height:27},15,C.muted).text.alignment='center';
 text(slide,'Fewer vacant taxis per half-hour · weekday · NEA rain forecast',{left:330,top:608,width:760,height:25},15,C.ink).text.alignment='center';
}
const coverage=[];
for(const entry of appendix){
 const{slide,graph,parts,part,total}=entry;const [title,note]=meta[graph.name]||[graph.name.replaceAll('_',' '),'Saved project figure. No new fitting or scoring.'];
 clean(slide,title+(total>1?` (${part}/${total})`:''),'PROJECT EVIDENCE · FULL GRAPH APPENDIX',note);
 if(graph.name==='planning_forecast_rain')planningHeatmap(slide);
 const n=parts.length,panelWidth=n===1?1050:525;
 for(let j=0;j<n;j++){
  const component=parts[j],left=n===1?115:105+j*545;
  const panelTitle=graph.name==='planning_forecast_rain'?'':component.titles.join(' / ');
  let titleLines=0;
  if(panelTitle){
   ctx.font='600 17px Poppins';const words=panelTitle.split(' '),lines=[];let line='';
   for(const word of words){if(line&&ctx.measureText(line+' '+word).width>panelWidth-10){lines.push(line);line=word;}else line+=(line?' ':'')+word;}
   if(line)lines.push(line);titleLines=lines.length;
   text(slide,lines.join('\n'),{left,top:211,width:panelWidth,height:Math.max(45,lines.length*25)},17,C.navy,'Poppins',true);
  }
  const hasBar=graph.colorbars.length>0;
  const hasList=component.placeList?.length>0;
  const hasLegend=component.legendItems?.length>0;
  let chartTop=titleLines>1?270:panelTitle?250:222;
  const yLabels=component.items.filter(it=>it.role==='ylabel'),plotItems=component.items.filter(it=>it.role!=='ylabel');
  if(yLabels.length){
   const lines=linesFor(yLabels.map(it=>it.text).join(' '),panelWidth-10);
   text(slide,lines.join('\n'),{left,top:chartTop-3,width:panelWidth,height:lines.length*21+5},14.67,C.muted);chartTop+=lines.length*21+7;
  }
  const chartBottom=hasBar?(hasLegend?470:531):hasLegend?555:603;
  if(graph.name!=='planning_forecast_rain')await draw(slide,plotItems,{left:hasList?100:left,top:chartTop,width:hasList?520:panelWidth,height:chartBottom-chartTop},{minFont:14.67});
  if(hasList)placeList(slide,component.placeList,Math.max(224,chartTop));
  if(hasLegend)legend(slide,component.legendItems,{left:left+15,top:hasBar?480:560,width:panelWidth-30});
  if(hasBar&&graph.name!=='planning_forecast_rain'){
   let bar=graph.colorbars.length===1?graph.colorbars[0]:graph.colorbars[Math.min(graph.components.indexOf(component),graph.colorbars.length-1)];
   if(bar.standardChange)standardBar(slide,{left:hasList?125:left+60,top:548,width:hasList?470:panelWidth-120});
   else {
    const unit=bar.items.filter(it=>it.role==='xlabel'||it.role==='ylabel'),items=bar.items.filter(it=>it.role!=='xlabel'&&it.role!=='ylabel');
    const bx=hasList?115:left+45,bw=hasList?490:panelWidth-90;
    await draw(slide,items,{left:bx,top:540,width:bw,height:40},{minFont:14.67});
    const lines=linesFor(unit.map(it=>it.text).join(' '),hasList?520:panelWidth-20);
    text(slide,lines.join('\n'),{left:hasList?100:left,top:585,width:hasList?520:panelWidth,height:Math.max(25,lines.length*20)},14.67,C.muted).text.alignment='center';
   }
  }
 }
 if(graph.legends?.length)legend(slide,graph.legends.flat(),{left:420,top:592,width:730});
 slide.speakerNotes.text=`Figure: ${graph.source}. ${note} Original numeric labels and curve/interval geometry are retained. The chart text and paths are editable. Percentage map fills use saved cell-ID joins and a common ±40% colour scale.`;
 coverage.push({sourceGraph:graph.name,sourceFile:graph.source,sourceSha256:graph.sourceSha256,part,total,panels:parts.map(c=>c.axis+1),slideId:slide.id});
}
// Correct the original footer page numbers after insertion, and retain the reference typography.
for(const [i,s] of p.slides.items.entries()){
 for(const sh of s.shapes.items)if(sh.position.top>640&&sh.position.left>1100&&/^\d{2}$/.test(String(sh.text)))sh.text=String(i+1).padStart(2,'0');
}
await fs.mkdir(OUT,{recursive:true});await fs.mkdir(path.join(BUILD,'final_previews'),{recursive:true});
await fs.mkdir(path.join(ROOT,'outputs/figures/deck/all'),{recursive:true});
const manifest={referenceSha256:crypto.createHash('sha256').update(await fs.readFile(reference)).digest('hex'),mainSlides:24,appendixDivider:25,sourceGraphCount:44,totalSlides:p.slides.items.length,coverage,sourceInputs:graphics.inputs};
for(const c of coverage)c.slide=p.slides.items.findIndex(s=>s.id===c.slideId)+1;
await fs.writeFile(path.join(OUT,'graph_coverage.json'),JSON.stringify(manifest,null,2));
await fs.writeFile(path.join(BUILD,'complete_inspect.ndjson'),(await p.inspect({kind:'slide,textbox,shape,image,table,chart',maxChars:10000000})).ndjson);
for(let i=0;i<p.slides.items.length;i++){
 const blob=await p.export({slide:p.slides.items[i],format:'png',scale:2});
 const name=`slide-${String(i+1).padStart(3,'0')}.png`;
 await fs.writeFile(path.join(BUILD,'final_previews',name),new Uint8Array(await blob.arrayBuffer()));
 if((i+1)%10===0)console.log('Rendered',i+1,'of',p.slides.items.length);
}
const candidate=path.join(BUILD,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
console.log('Candidate',candidate,'slides',p.slides.items.length);
const finalPath=path.join(OUT,'Its_Raining_Taxis_complete.pptx');
const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')));
await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath,
 pythonExecutable:'/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',
 integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
 explicitTotalSlideCount:p.slides.items.length,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
 fontPolicy:{basis:'reference',families:['Poppins','Anton'],referencePath:reference,referenceSha256:manifest.referenceSha256},
 verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation-final.json')});
console.log('Final',finalPath);
