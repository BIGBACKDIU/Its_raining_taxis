(()=>{
'use strict';
const $=id=>document.getElementById(id), reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
const project=(lon,lat)=>[(lon-DATA.projection.lon0)*DATA.projection.metresLon,(lat-DATA.projection.lat0)*DATA.projection.metresLat];
const cbd=project(103.852,1.286),west=project(103.70,1.34),centre=project(103.82,1.35);
const defaults={size:'medium',strength:25,duration:60,direction:'east',driftSpeed:10,weekend:false,hour:13,
  mechanism:'mix',demand:1,policy:false,dest:'characteristics',dispatch:'nearest',seed:2702,x:cbd[0],y:cbd[1]};
let config={...defaults},result=null,worker=null,playing=false,time=-.001,speed=4,split=false,lastFrame=performance.now();
let generation=0,dirty=true,frameKey='',buildTimer=null,stress=null;
const views=[0,1].map(i=>({canvas:$('map'+i),context:$('map'+i).getContext('2d'),base:document.createElement('canvas'),w:0,h:0}));
const perf={frames:0,drawMs:[],times:[],drawnDots:0,drawnVacant:0};
const colors=['#0e8fa8','#c97f12','#7a5cd6','#22344a','#8796a7','#8796a7'];   // vacant, hired, repositioning, to pickup, leaving, returning
const sprites=colors.map(color=>{const c=document.createElement('canvas');c.width=c.height=24;const x=c.getContext('2d');
  x.fillStyle='#ffffff';x.beginPath();x.arc(12,12,11.5,0,2*Math.PI);x.fill();          // white rim, like map pins
  x.fillStyle=color;x.beginPath();x.arc(12,12,8.5,0,2*Math.PI);x.fill();return c;});
function transform(v){
  // Fit the island into the part of the view not covered by the floating panels (desktop city view).
  const bounds=[3000,65000,3000,38000],pad=v.w<500?10:16;let L=pad,R=pad,T=pad,B=pad;
  if(innerWidth>760){const r=v.canvas.getBoundingClientRect(),mid=r.left+r.width/2;
    for(const id of ['controls','info']){const el=$(id);if(!el||el.hidden)continue;const e=el.getBoundingClientRect();if(!e.width)continue;
      if(e.right<mid)L=Math.max(L,e.right-r.left+12);else if(e.left>mid)R=Math.max(R,r.right-e.left+12);}
    const top=document.querySelector('.topbar').getBoundingClientRect();T=Math.max(T,top.bottom-r.top+8);
    const low=Math.min(...['.playbar','.toolbar'].map(q=>document.querySelector(q).getBoundingClientRect().top));B=Math.max(B,r.bottom-low+8);
    if(v.w-L-R<v.w*.45){L=R=pad;}if(v.h-T-B<v.h*.4){T=B=pad;}}
  v.scale=Math.min((v.w-L-R)/(bounds[1]-bounds[0]),(v.h-T-B)/(bounds[3]-bounds[2]));
  v.tx=L+((v.w-L-R)-(bounds[1]-bounds[0])*v.scale)/2-bounds[0]*v.scale;
  v.ty=T+(v.h-T-B)/2+(bounds[3]+bounds[2])/2*v.scale;
  v.xy=(x,y)=>[v.tx+x*v.scale,v.ty-y*v.scale];
}
function drawBase(v){
  const c=v.base.getContext('2d');c.setTransform(v.dpr,0,0,v.dpr,0,0);
  const sea=c.createLinearGradient(0,0,0,v.h);sea.addColorStop(0,'#bfe0ec');sea.addColorStop(1,'#a9d3e3');c.fillStyle=sea;c.fillRect(0,0,v.w,v.h);
  const land=new Path2D();for(const ring of DATA.land){ring.forEach((p,i)=>{const q=v.xy(p[0],p[1]);i?land.lineTo(...q):land.moveTo(...q);});land.closePath();}
  c.save();c.shadowColor='rgba(40,90,120,.25)';c.shadowBlur=10;c.fillStyle='#eef1e8';c.fill(land);c.restore();
  c.save();c.clip(land);c.strokeStyle='rgba(120,140,120,.10)';c.lineWidth=1;c.beginPath();               // faint 1 km district grid
  for(let x=3000;x<=65000;x+=1000){c.moveTo(...v.xy(x,3000));c.lineTo(...v.xy(x,38000));}
  for(let y=3000;y<=38000;y+=1000){c.moveTo(...v.xy(3000,y));c.lineTo(...v.xy(65000,y));}c.stroke();c.restore();
  c.strokeStyle='#cfd8cc';c.lineWidth=1;c.stroke(land);
  const paths=Array.from({length:5},()=>new Path2D()),nodes=DATA.road.nodes;
  for(const e of DATA.road.edges){const p=paths[e[2]];p.moveTo(...v.xy(nodes[e[0]*2],nodes[e[0]*2+1]));
    for(let j=4;j<e.length;j+=2)p.lineTo(...v.xy(e[j],e[j+1]));p.lineTo(...v.xy(nodes[e[1]*2],nodes[e[1]*2+1]));}
  const k=v.w<600?.75:1,widths=[3.2,2.4,1.8,1.4,1.1],casing=['#b9c2c9','#c4ccd2','#ccd3d8','#d3d9dd','#d8dde0'],fill=['#ffffff','#ffffff','#fbfbfa','#f7f7f5','#f4f4f2'];
  c.lineCap='round';c.lineJoin='round';
  for(let i=4;i>=0;i--){c.strokeStyle=casing[i];c.lineWidth=(widths[i]+1.4)*k;c.stroke(paths[i]);}
  for(let i=4;i>=0;i--){c.strokeStyle=fill[i];c.lineWidth=widths[i]*k;c.stroke(paths[i]);}
  c.strokeStyle='#f3d27a';c.lineWidth=1.1*k;c.stroke(paths[0]);                                             // expressway centre line
  c.font=`700 ${v.w<500?9:11.5}px ui-sans-serif,system-ui,sans-serif`;c.textAlign='center';c.lineJoin='round';
  const labels=[['TUAS',103.645,1.305],['JURONG',103.715,1.33],['WOODLANDS',103.79,1.445],['ANG MO KIO',103.85,1.375],['TAMPINES',103.945,1.355],['CHANGI',103.985,1.36],['CBD',103.85,1.272]];
  for(const [label,lon,lat] of labels){const q=v.xy(...project(lon,lat));c.strokeStyle='rgba(255,255,255,.9)';c.lineWidth=4;c.strokeText(label,...q);c.fillStyle='#4a5d70';c.fillText(label,...q);}
}
function resize(){
  for(const v of views){const r=v.canvas.getBoundingClientRect();if(!r.width||!r.height)continue;
    v.w=r.width;v.h=r.height;v.dpr=Math.min(devicePixelRatio||1,2);
    for(const c of [v.canvas,v.base]){c.width=Math.round(v.w*v.dpr);c.height=Math.round(v.h*v.dpr);}transform(v);drawBase(v);
  }dirty=true;drawChart();
}
function sample(path,distance){
  const p=result.paths[path],d=Math.max(0,Math.min(distance,p.length));let lo=0,hi=p.cumulative.length-1;
  while(lo<hi){const k=(lo+hi+1)>>1;if(p.cumulative[k]<=d)lo=k;else hi=k-1;}
  const k=Math.min(lo,p.cumulative.length-2),span=p.cumulative[k+1]-p.cumulative[k],f=span>0?(d-p.cumulative[k])/span:0;
  return [p.xy[2*k]+(p.xy[2*k+2]-p.xy[2*k])*f,p.xy[2*k+1]+(p.xy[2*k+3]-p.xy[2*k+1])*f];
}
function legAt(actor,t){let lo=0,hi=actor.legs.length-1;if(actor.born>t)return null;
  while(lo<hi){const k=(lo+hi+1)>>1;if(actor.legs[k].from<=t)lo=k;else hi=k-1;}return actor.legs[lo];}
function position(leg,t,id=0,mobile=false){
  if(leg.kind>=4)return leg.point;
  const p=result.paths[leg.route];
  if(leg.kind===0){const ct=reduced?leg.from:mobile?Math.max(leg.from,Math.floor(t*12)/12):t;return sample(leg.route,p.length?((leg.phase+(ct-leg.from)*180)%p.length+p.length)%p.length:0);}
  const arrival=leg.arrive??leg.to, f=Math.min(1,Math.max(0,(t-leg.from)/Math.max(.001,arrival-leg.from)));
  return sample(leg.route,p.length*f);
}
function rain(v,c,t){
  if(t<0||t>=config.duration)return;
  const d={still:[0,0],east:[1,0],west:[-1,0],north:[0,1],south:[0,-1]}[config.direction];
  const velocity=config.driftSpeed*1000/60;
  const [x,y]=v.xy(config.x+d[0]*velocity*t,config.y+d[1]*velocity*t);
  const radius={small:1500,medium:4000,large:10000,island:36000}[config.size];
  const rx=(config.size==='island'?70000:radius)*v.scale,ry=(config.size==='island'?30000:radius)*v.scale;
  const amp=Math.pow(Math.sin(Math.PI*t/config.duration),.75),alpha=Math.min(.7,(.22+Math.min(config.strength,60)/110)*amp);
  c.save();c.translate(x,y);c.scale(rx,ry);
  const g=c.createRadialGradient(0,0,0,0,0,1);
  g.addColorStop(0,`rgba(12,95,168,${alpha*.85})`);g.addColorStop(.35,`rgba(21,147,209,${alpha*.6})`);
  g.addColorStop(.75,`rgba(90,180,230,${alpha*.28})`);g.addColorStop(1,'rgba(90,180,230,0)');
  c.fillStyle=g;c.beginPath();c.arc(0,0,1,0,Math.PI*2);c.fill();c.restore();
  c.save();c.strokeStyle=`rgba(12,95,168,${amp*.45})`;c.lineWidth=1.2;c.setLineDash([4,4]);
  for(const f of [.4,.75]){c.beginPath();c.ellipse(x,y,rx*f,ry*f,0,0,Math.PI*2);c.stroke();}c.restore();
}
function drawMap(v,output,t){
  const c=v.context,mobile=v.w<600;c.setTransform(1,0,0,1,0,0);c.drawImage(v.base,0,0);c.setTransform(v.dpr,0,0,v.dpr,0,0);
  rain(v,c,t);
  const cp=v.xy(config.x,config.y);c.strokeStyle='#16273acc';c.setLineDash([3,3]);c.lineWidth=1.4;c.beginPath();c.arc(cp[0],cp[1],9,0,2*Math.PI);c.stroke();c.setLineDash([]);c.fillStyle='#16273a';c.beginPath();c.arc(cp[0],cp[1],2,0,2*Math.PI);c.fill();
  let dots=0,vacant=0;
  const source=stress?stress.actors:output.actors,st=stress?(performance.now()-stress.start)/1000*5:t;
  for(const actor of source){const leg=stress?actor.legs[0]:legAt(actor,st);if(!leg)continue;
    const age=st-leg.from;let alpha=1;
    if(leg.kind>=4){alpha=Math.max(0,1-age/1.5);if(alpha<=0)continue;}
    if(leg.kind===0){vacant++;if(leg.from>=0)alpha=Math.min(1,.25+age*1.5);}
    const p=position(leg,st,actor.id,mobile),q=v.xy(p[0],p[1]);
    if(!mobile&&!reduced&&leg.kind>0&&leg.kind<4&&(actor.id%3===0||leg.kind===2)){
      const before=position(leg,Math.max(leg.from,st-.3),actor.id,false),r=v.xy(before[0],before[1]);
      c.globalAlpha=.35;c.strokeStyle=colors[leg.kind];c.lineWidth=leg.kind===2?1.3:.9;
      c.setLineDash(leg.kind===2?[3,3]:[]);c.beginPath();c.moveTo(...r);
      const path=result.paths[leg.route],duration=Math.max(.001,(leg.arrive??leg.to)-leg.from);
      const d0=path.length*Math.max(0,(st-.3-leg.from)/duration),d1=path.length*Math.min(1,(st-leg.from)/duration);
      for(let k=1;k<path.cumulative.length-1;k++)if(path.cumulative[k]>d0&&path.cumulative[k]<d1)c.lineTo(...v.xy(path.xy[k*2],path.xy[k*2+1]));
      c.lineTo(...q);c.stroke();c.setLineDash([]);
    }
    c.globalAlpha=alpha;const radius=(leg.kind===0?2.6:2.9)*(mobile?.8:1);
    c.drawImage(sprites[leg.kind],q[0]-radius,q[1]-radius,radius*2,radius*2);dots++;
  }
  c.globalAlpha=1;
  if(!stress){const duration=reduced?4:2;let lo=0,hi=output.pulses.length;
    while(lo<hi){const k=(lo+hi)>>1;if(output.pulses[k].m<t-duration)lo=k+1;else hi=k;}
    for(let i=lo;i<output.pulses.length&&output.pulses[i].m<=t;i++){
      const p=output.pulses[i],age=t-p.m,node=DATA.road.cellNodes[p.cell],xy=v.xy(DATA.road.nodes[node*2],DATA.road.nodes[node*2+1]);
      c.globalAlpha=Math.max(0,1-age/duration)*.8;c.strokeStyle=p.kind?'#d2563e':'#22344a';c.lineWidth=1.2;
      c.beginPath();c.arc(xy[0],xy[1],reduced?2:1+age*3,0,Math.PI*2);c.stroke();
    }}c.globalAlpha=1;
  return {dots,vacant};
}
function active(){return split?0:config.policy?1:0;}
function frame(index=active()){return time<0?result.outputs[index].initial:result.outputs[index].frames[Math.min(240,Math.floor(time))];}
function updateCounters(){if(!result)return;const f=frame(),key=`${active()}:${Math.floor(time)}:${time<0}`;
  if(key!==frameKey){frameKey=key;for(const name of ['vacant','hired','offline','waiting','abandoned'])$(name).textContent=Math.round(f[name]).toLocaleString('en-SG');drawChart();}
  const min=(config.hour*60+Math.max(0,time))%(24*60);$('clock').textContent=`${String(Math.floor(min/60)).padStart(2,'0')}:${String(Math.floor(min%60)).padStart(2,'0')}`;
  $('timeline').value=Math.max(0,time);
  if(split)for(let i=0;i<2;i++)$('compare'+i).textContent=`${frame(i).vacant.toLocaleString()} vacant · simulated`;
}
function drawChart(){
  const canvas=$('chart'),r=canvas.getBoundingClientRect();if(!r.width||!result)return;
  const dpr=Math.min(devicePixelRatio||1,2);canvas.width=r.width*dpr;canvas.height=r.height*dpr;
  const c=canvas.getContext('2d');c.scale(dpr,dpr);const w=r.width,h=r.height,frames=result.outputs[active()].frames;
  const values=frames.flatMap(f=>[f.vacant,f.expected]),hi=Math.max(...values),lo=Math.min(...values);
  const step=Math.pow(10,Math.floor(Math.log10(Math.max(1,(hi-lo)/3)))),top=Math.ceil(hi*1.04/step)*step,bottom=Math.max(0,Math.floor(lo*.96/step)*step);
  const left=46,right=22,x=t=>left+t/240*(w-left-right),y=v=>h-22-(v-bottom)/(top-bottom)*(h-34);
  c.font='11px ui-sans-serif,system-ui,sans-serif';
  c.fillStyle='rgba(21,147,209,.13)';c.fillRect(x(0),8,x(Math.min(config.duration,240))-x(0),h-30);
  c.strokeStyle='#e3e9ee';c.lineWidth=1;c.fillStyle='#6c8095';c.textAlign='right';
  for(const f of [0,1/3,2/3,1]){const value=bottom+(top-bottom)*f;c.beginPath();c.moveTo(left,Math.round(y(value))+.5);c.lineTo(w-right,Math.round(y(value))+.5);c.stroke();c.fillText(Math.round(value).toLocaleString('en-SG'),left-8,y(value)+4);}
  c.textAlign='center';for(let t=0;t<=240;t+=60)c.fillText(t?`+${t/60} h`:'start',x(t),h-5);
  c.strokeStyle='#8796a7';c.setLineDash([4,4]);c.lineWidth=1.25;c.beginPath();frames.forEach((f,i)=>{const p=[x(i),y(f.expected)];i?c.lineTo(...p):c.moveTo(...p);});c.stroke();c.setLineDash([]);
  c.strokeStyle='#0e8fa8';c.lineWidth=2.2;c.lineJoin='round';c.beginPath();const end=Math.max(0,Math.floor(time));
  frames.slice(0,end+1).forEach((f,i)=>{const p=[x(i),y(f.vacant)];i?c.lineTo(...p):c.moveTo(...p);});c.stroke();
  if(time>=0){const p=[x(end),y(frames[end].vacant)];c.fillStyle='#0e8fa8';c.beginPath();c.arc(...p,3.5,0,2*Math.PI);c.fill();
    c.strokeStyle='#16273a44';c.lineWidth=1;c.beginPath();c.moveTo(x(Math.max(0,time)),8);c.lineTo(x(Math.max(0,time)),h-22);c.stroke();}
}
function play(){if(!result)return;if(time>=240)time=-.001;playing=!playing;$('play').textContent=playing?'Ⅱ Pause':'▶ Play';$('play').setAttribute('aria-label',playing?'Pause simulation':'Play simulation');lastFrame=performance.now();dirty=true;}
// Describe the prepared scenario, never an unbuilt draft or an inferred empirical effect.
function updateDescription(){
  if(!result)return;
  const c=result.config;
  let nearest=0,distance=Infinity;
  for(let i=0;i<DATA.cells.cell.length;i++){const d=Math.hypot(c.x-DATA.cells.x[i],c.y-DATA.cells.y[i]);if(d<distance){distance=d;nearest=i;}}
  const strength={2:'Light',8:'Moderate',25:'Heavy',60:'Extreme'}[c.strength];
  const area={small:'3 km',medium:'8 km',large:'20 km',island:'Island-wide'}[c.size];
  const movement=c.direction==='still'?'stationary':`drifting ${c.direction} at ${c.driftSpeed} km/h`;
  $('storm-setup').textContent=`${strength} rain · ${area}${c.size==='island'?'':' across'} · ${c.duration} min · ${movement}. ${c.weekend?'Weekend':'Weekday'} at ${String(c.hour).padStart(2,'0')}:00${c.size==='island'?'':`, starting near ${DATA.cells.place[nearest]}`}.`;
  const mechanism={demand:'Rain raises simulated requests, so more taxis can leave the vacant pool for hires.',
    supply:'Rain moves some simulated drivers off duty, reducing the vacant pool until they return after rain clears.',
    mix:'Rain raises simulated requests and moves some drivers off duty; both can reduce the vacant pool.'}[c.mechanism];
  const clauses=[mechanism,'Wet-area travel takes 25% longer, delaying taxi arrivals.'];
  if(c.demand!==1)clauses.push(`The request setting scales new requests to ${Math.round(c.demand*100)}% of the model’s usual rate, before any rain multiplier.`);
  if(c.strength>30)clauses.push('The model’s rain response caps at 30 mm/h.');
  if(split)clauses.push('Compare the same storm and seed with and without repositioning; taxis in transit are temporarily unavailable.');
  else if(config.policy)clauses.push('Repositioning sends surplus taxis towards modelled shortages; they are unavailable while travelling.');
  $('storm-effect').textContent=clauses.join(' ');
}
function build(){
  clearTimeout(buildTimer);if(worker)worker.terminate();const token=++generation;playing=false;time=-.001;result=null;stress=null;frameKey='';
  $('play').textContent='▶ Play';$('busy').hidden=false;$('busy-text').textContent='Setting the city in motion…';
  $('storm-setup').textContent='Building your scenario…';$('storm-effect').textContent='The explanation updates when your storm is ready.';
  $('status').textContent='Building your scenario…';$('play').disabled=true;$('apply').disabled=true;
  const source=['engine','router','scenario','planner'].map(id=>$(id).textContent).join('\n')+
    '\nonmessage=e=>{try {const r=prepareSimulation(e.data.data,e.data.config,p=>postMessage({progress:p}));postMessage({result:r});}catch(error){postMessage({error:error.stack||String(error)});}};';
  const receive=e=>{if(token!==generation)return;
    if(e.data.progress){$('busy-text').textContent=`Planning ${e.data.progress.policy?'repositioning':'as usual'} · ${e.data.progress.minute}/240 min`;return;}
    if(e.data.error){console.error(e.data.error);$('busy-text').textContent='Could not build this scenario. Reset or reload to retry.';$('status').textContent='Scenario error';$('status').classList.add('error');$('apply').disabled=false;return;}
    result=e.data.result;if(worker)worker.terminate();worker=null;$('busy').hidden=true;$('play').disabled=false;$('apply').disabled=false;
    $('status').innerHTML=`<b>Ready when you are.</b><br>${config.weekend?'Weekend':'Weekday'} · ${String(config.hour).padStart(2,'0')}:00 · 4 simulated hours`;
    $('performance').textContent=reduced?'Reduced motion enabled':'Real road paths · Illustrative taxi journeys';
    window.StormBuilder.ready=true;updateDescription();resize();updateCounters();dirty=true;
  };
  window.StormBuilder.ready=false;
  const fallback=()=>{if(token!==generation)return;if(worker)worker.terminate();worker=null;
    $('busy-text').textContent='Preparing this scenario locally…';
    setTimeout(()=>{try{receive({data:{result:prepareSimulation(DATA,{...config})}});}catch(error){receive({data:{error:String(error)}});}},30);};
  try{const url=URL.createObjectURL(new Blob([source],{type:'text/javascript'}));worker=new Worker(url);URL.revokeObjectURL(url);
    worker.onmessage=receive;worker.onerror=e=>{e.preventDefault();fallback();};worker.postMessage({data:DATA,config:{...config}});
  }catch(error){fallback();}
}
function scheduleBuild(){clearTimeout(buildTimer);buildTimer=setTimeout(build,220);}
function refreshControls(){
  document.querySelectorAll('[data-control]').forEach(group=>group.querySelectorAll('button').forEach(b=>{
    const key=group.dataset.control,value=key==='speed'?speed:config[key];b.setAttribute('aria-pressed',String(b.dataset.value===String(value)));}));
  $('demand').value=config.demand;$('demand-note').textContent=config.demand.toFixed(2)+'×';$('seed').value=config.seed;
  $('policy').setAttribute('aria-pressed',String(config.policy));$('strength-note').textContent=`Peak ${config.strength} mm/h`;
  $('size-note').textContent={small:'About 3 km across',medium:'About 8 km across',large:'About 20 km across',island:'A broad band over the island'}[config.size];
  $('caption0').innerHTML=`${!split&&config.policy?'With repositioning':'As usual'} <em>same seed</em>`;
}
function setSplit(value){split=value;$('split').checked=value;$('tool-compare').setAttribute('aria-pressed',String(value));$('maps').classList.toggle('split',value);$('view1').hidden=!value;$('compare0').hidden=!value;frameKey='';refreshControls();updateDescription();resize();updateCounters();dirty=true;}
function sheet(open){$('controls').classList.toggle('open',open);$('backdrop').hidden=!open;$('open-sheet').setAttribute('aria-expanded',String(open));
  if(open)$('close-sheet').focus();else $('open-sheet').focus();}
document.querySelectorAll('[data-control]').forEach(group=>group.addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b)return;const key=group.dataset.control;
  if(key==='speed'){speed=Number(b.dataset.value);refreshControls();return;}
  config[key]=['strength','duration','driftSpeed','hour'].includes(key)?Number(b.dataset.value):key==='weekend'?b.dataset.value==='true':b.dataset.value;
  document.querySelectorAll('[data-preset]').forEach(b=>b.setAttribute('aria-pressed','false'));refreshControls();scheduleBuild();
}));
$('presets').addEventListener('click',e=>{const b=e.target.closest('[data-preset]');if(!b)return;
  const presets={cbd:{...defaults},monsoon:{...defaults,size:'island',strength:25,duration:180,direction:'still',x:centre[0],y:centre[1]},
    west:{...defaults,size:'small',strength:2,duration:30,direction:'still',x:west[0],y:west[1]},rush:{...defaults,size:'large',strength:25,duration:120,direction:'east',hour:18}};
  config=presets[b.dataset.preset];document.querySelectorAll('[data-preset]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
  $('location').textContent=`Starting centre · ${b.dataset.preset==='west'?'Jurong':b.dataset.preset==='monsoon'?'Singapore':'CBD'}`;refreshControls();scheduleBuild();
});
$('demand').addEventListener('input',()=>{config.demand=Number($('demand').value);$('demand-note').textContent=config.demand.toFixed(2)+'×';});
$('demand').addEventListener('change',scheduleBuild);
$('seed').addEventListener('change',()=>{config.seed=Math.max(1,Math.min(2147483646,Math.round(Number($('seed').value)||2702)));refreshControls();scheduleBuild();});
$('policy').addEventListener('click',()=>{config.policy=!config.policy;frameKey='';refreshControls();updateDescription();updateCounters();dirty=true;});
function togglePanel(id,tool,force){const el=$(id),show=force??el.hidden;el.hidden=!show;$(tool).setAttribute('aria-pressed',String(show));resize();}
$('tool-storm').addEventListener('click',()=>togglePanel('controls','tool-storm'));
$('tool-info').addEventListener('click',()=>togglePanel('info','tool-info'));
$('tool-compare').addEventListener('click',()=>setSplit(!split));
$('tool-help').addEventListener('click',()=>{const open=!$('help').open;togglePanel('info','tool-info',true);$('help').open=open;$('tool-help').setAttribute('aria-pressed',String(open));if(open)$('help').scrollIntoView({block:'nearest'});});
$('help').addEventListener('toggle',()=>$('tool-help').setAttribute('aria-pressed',String($('help').open)));
$('play').addEventListener('click',play);$('split').addEventListener('change',()=>setSplit($('split').checked));
$('timeline').addEventListener('input',()=>{time=Number($('timeline').value)||-.001;dirty=true;updateCounters();});
$('reset').addEventListener('click',()=>{playing=false;time=-.001;frameKey='';$('play').textContent='▶ Play';dirty=true;updateCounters();});
$('apply').addEventListener('click',()=>{if(matchMedia('(max-width:700px)').matches)sheet(false);build();});
$('open-sheet').addEventListener('click',()=>sheet(true));$('close-sheet').addEventListener('click',()=>sheet(false));$('backdrop').addEventListener('click',()=>sheet(false));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('controls').classList.contains('open'))sheet(false);
  if(e.key==='Tab'&&$('controls').classList.contains('open')){const f=[...$('controls').querySelectorAll('button,input,summary')].filter(x=>x.getClientRects().length&&!x.disabled),first=f[0],last=f.at(-1);
    if(e.shiftKey&&document.activeElement===first){last.focus();e.preventDefault();}else if(!e.shiftKey&&document.activeElement===last){first.focus();e.preventDefault();}}
});
function place(v,x,y){config.x=Math.max(4000,Math.min(64000,x));config.y=Math.max(4000,Math.min(37000,y));
  let nearest=0,distance=Infinity;for(let i=0;i<DATA.cells.cell.length;i++){const d=Math.hypot(config.x-DATA.cells.x[i],config.y-DATA.cells.y[i]);if(d<distance){nearest=i;distance=d;}}
  $('location').textContent=`Starting centre · ${DATA.cells.place[nearest]}`;dirty=true;scheduleBuild();}
for(const v of views){v.canvas.addEventListener('click',e=>{const r=v.canvas.getBoundingClientRect();place(v,(e.clientX-r.left-v.tx)/v.scale,(v.ty-(e.clientY-r.top))/v.scale);});
  v.canvas.addEventListener('keydown',e=>{const d={ArrowLeft:[-1000,0],ArrowRight:[1000,0],ArrowUp:[0,1000],ArrowDown:[0,-1000]}[e.key];if(d){e.preventDefault();place(v,config.x+d[0],config.y+d[1]);}});}
new ResizeObserver(resize).observe($('maps'));window.addEventListener('resize',resize);
function tick(now){const dt=Math.min(.1,(now-lastFrame)/1000);lastFrame=now;
  if(playing&&result){time=Math.min(240,Math.max(0,time)+dt*speed);if(time>=240){playing=false;$('play').textContent='▶ Play';}dirty=true;}
  if(result&&(playing||dirty||stress)){
    const start=performance.now();let count={dots:0,vacant:0};
    if(split){count=drawMap(views[0],result.outputs[0],time);drawMap(views[1],result.outputs[1],time);}
    else count=drawMap(views[0],result.outputs[active()],time);
    perf.drawnDots=count.dots;perf.drawnVacant=count.vacant;perf.frames++;perf.times.push(now);perf.drawMs.push(performance.now()-start);
    if(perf.times.length>600){perf.times.shift();perf.drawMs.shift();}
    updateCounters();dirty=false;
  }
  requestAnimationFrame(tick);
}
window.StormBuilder={ready:false,get config(){return {...config};},get result(){return result;},
  get time(){return time;},get playing(){return playing;},get reducedMotion(){return reduced;},
  seek(t){time=t<=0?-.001:Math.min(240,t);dirty=true;frameKey='';updateCounters();},setSpeed(s){speed=s;refreshControls();},play,
  counters(){return result?{...frame(),V:Array.from(frame().V)}:null;},
  performance(){const times=perf.times,dt=times.length>1?(times.at(-1)-times[0])/1000:0,sort=[...perf.drawMs].sort((a,b)=>a-b);
    return {fps:dt?(times.length-1)/dt:0,frames:times.length,drawP95Ms:sort[Math.floor(sort.length*.95)]||0,drawnDots:perf.drawnDots,drawnVacant:perf.drawnVacant,pathFallbacks:result?.pathFallbacks??null};},
  resetPerformance(){perf.times=[];perf.drawMs=[];perf.frames=0;},
  stressTest(n=2500){if(!result)return;const routes=result.paths.map((p,i)=>p.length>300&&Math.hypot(p.xy[0]-p.xy[p.xy.length-2],p.xy[1]-p.xy[p.xy.length-1])<1?i:-1).filter(i=>i>=0);
    stress={start:performance.now(),actors:Array.from({length:n},(_,id)=>({id,born:-1,legs:[{kind:0,from:0,to:Infinity,route:routes[id%routes.length],phase:(id*137)%result.paths[routes[id%routes.length]].length}]}))};
    this.resetPerformance();dirty=true;},stopStress(){stress=null;dirty=true;},setSplit};
refreshControls();document.querySelector('[data-preset=cbd]').setAttribute('aria-pressed','true');resize();requestAnimationFrame(tick);build();
})();
