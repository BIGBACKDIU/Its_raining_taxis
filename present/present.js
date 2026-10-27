'use strict';
// Presentation runtime for outputs/story/present.html (decision 174). Draws saved data only.
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const NS='http://www.w3.org/2000/svg';
const C={taxi:'#0B3D91',sky:'#1E88E5',skyLight:'#9DCBF6',pale:'#E3EEFB',ink:'#14203A',muted:'#5A6683',grid:'#E4EAF4',red:'#C0453C',dry:'#DDE2EA',none:'#F1F4F8',white:'#FFFFFF',yellow:'#FFC72C'};
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
let motion=!reduced.matches;
reduced.addEventListener('change',()=>{motion=!reduced.matches;});
function el(tag,attrs={},text){const v=document.createElementNS(NS,tag);for(const[k,val]of Object.entries(attrs))v.setAttribute(k,val);if(text!==undefined)v.textContent=text;return v;}
function add(parent,tag,attrs,text){const v=el(tag,attrs,text);parent.append(v);return v;}
const num=(v,d=0)=>Number(v).toLocaleString('en-SG',{minimumFractionDigits:d,maximumFractionDigits:d}).replace('-','−');
function mix(a,b,f){const A=a.slice(1).match(/../g).map(x=>parseInt(x,16)),B=b.slice(1).match(/../g).map(x=>parseInt(x,16));return'#'+A.map((v,i)=>Math.round(v*(1-f)+B[i]*f).toString(16).padStart(2,'0')).join('');}
function rng(seed){return()=>{seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}

/* ---------- stage, slides, keyboard ---------- */
const stage=$('#stage'),slides=$$('.slide'),MAIN=slides.filter(s=>!s.hasAttribute('data-appendix')).length;
const presenter=$('#presenter');
let current=-1;const timers=new Set();
function later(fn,ms){const t=setTimeout(()=>{timers.delete(t);fn();},ms);timers.add(t);return t;}
function fit(){
 const h=presenter.hidden?innerHeight:Math.max(200,innerHeight-presenter.offsetHeight);
 const s=Math.min(innerWidth/1920,h/1080);
 stage.style.transform=`translate(${(innerWidth-1920*s)/2}px,${(h-1080*s)/2}px) scale(${s})`;
}
addEventListener('resize',fit);
const hooks={};
function show(index){
 index=Math.max(0,Math.min(slides.length-1,index));
 if(index===current)return;
 const old=slides[current];
 if(old){old.classList.remove('active');hooks[old.id]?.leave?.();setTimeout(()=>{if(!old.classList.contains('active'))old.classList.remove('entered');},500);}
 for(const t of timers)clearTimeout(t);timers.clear();
 current=index;const slide=slides[index];
 slide.classList.remove('entered');slide.classList.add('active');
 requestAnimationFrame(()=>requestAnimationFrame(()=>{if(slides[current]===slide)slide.classList.add('entered');}));
 hooks[slide.id]?.enter?.();
 stage.classList.toggle('dark',slide.classList.contains('dark'));
 $('#progress').style.width=Math.min(index+1,MAIN)/MAIN*100+'%';
 $('#number').innerHTML=slide.hasAttribute('data-appendix')?'<b>Appendix</b>':`<b>${index+1}</b> / ${MAIN}`;
 history.replaceState(null,'','#'+(index+1));
 updatePresenter();
}
addEventListener('keydown',e=>{
 if(e.metaKey||e.ctrlKey||e.altKey)return;
 const k=e.key;
 if(['ArrowRight','PageDown',' ','Spacebar'].includes(k)){e.preventDefault();show(current+1);}
 else if(['ArrowLeft','PageUp'].includes(k)){e.preventDefault();show(current-1);}
 else if(k==='Home')show(0);else if(k==='End')show(MAIN-1);
 else if(k==='f'||k==='F'){if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen?.().catch(()=>{});}
 else if(k==='s'||k==='S'){presenter.hidden=!presenter.hidden;fit();updatePresenter();}
});
$('#prev').addEventListener('click',()=>show(current-1));
$('#next').addEventListener('click',()=>show(current+1));

/* ---------- presenter panel ---------- */
let startedAt=Date.now();
function clock(){const s=Math.floor((Date.now()-startedAt)/1000);$('#p-timer').textContent=String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}
setInterval(clock,1000);
$('#p-reset').addEventListener('click',()=>{startedAt=Date.now();clock();});
function updatePresenter(){
 if(presenter.hidden||current<0)return;
 const slide=slides[current],next=slides[current+1];
 $('#p-title').textContent=`${slide.hasAttribute('data-appendix')?'Appendix':current+1+' / '+MAIN} · ${slide.dataset.title}`;
 $('#p-notes').textContent=slide.querySelector('.notes')?.textContent.trim()||'';
 $('#p-next').textContent=next?next.dataset.title:'End of presentation';
}

/* ---------- 1 title: rain streaks clear to a dark map with drifting radar blobs ---------- */
const tc=$('#title-canvas'),tx=tc.getContext('2d');
const MK=22,MX=v=>650+(v-5)*MK,MY=v=>235+(36-v)*MK;
const landPath=new Path2D();
for(const ring of DATA.land)ring.forEach(([x,y],i)=>i?landPath.lineTo(MX(x),MY(y)):landPath.moveTo(MX(x),MY(y))),landPath.closePath();
const gridPath=new Path2D();
for(const[cell]of DATA.cells)gridPath.rect(MX(Math.floor(cell/1000)),MY(cell%1000+1),MK,MK);
const rand=rng(2702);
const drops=Array.from({length:560},()=>({x:rand()*2300-250,y:rand()*1080,l:28+rand()*64,v:1500+rand()*1100,w:1+rand()*1.6}));
const blobs=[[2,22,8,1],[14,13,5.5,.6],[25,28,7.5,.9],[38,17,6,.55],[50,25,9,.8],[-10,12,6.5,.7]].map(([x,y,r,i])=>({x,y,r,i}));
const RADAR=[[0,'230,25,75'],[.24,'245,130,49'],[.46,'255,225,25'],[.72,'60,180,75']];
function blob(x,y,r,intensity,alpha){
 const skip=intensity>.85?0:intensity>.6?1:2,stops=RADAR.slice(skip);
 const g=tx.createRadialGradient(x,y,0,x,y,r);
 stops.forEach(([at,rgb],i)=>g.addColorStop(i/(stops.length),`rgba(${rgb},${(.78-.08*i)*alpha})`));
 g.addColorStop(1,`rgba(60,180,75,0)`);
 tx.fillStyle=g;tx.beginPath();tx.arc(x,y,r,0,Math.PI*2);tx.fill();
}
function drawTitle(t){
 tx.globalAlpha=1;tx.globalCompositeOperation='source-over';
 tx.fillStyle='#061A40';tx.fillRect(0,0,1920,1080);
 const map=Math.min(1,Math.max(0,(t-1.7)/1.5)),rain=1-Math.min(1,Math.max(0,(t-1.9)/1.3));
 if(map>0){
  tx.globalAlpha=map;tx.fillStyle='#0D2B63';tx.fill(landPath);
  tx.strokeStyle='rgba(255,255,255,.075)';tx.lineWidth=1;tx.stroke(gridPath);
  tx.strokeStyle='rgba(150,190,255,.55)';tx.lineWidth=1.6;tx.stroke(landPath);
  for(const b of blobs){
   const x=((b.x+t*.75+15)%85)-15;
   for(const[dx,dy,s]of [[0,0,1],[b.r*.55,b.r*.2,.62],[-b.r*.45,-b.r*.25,.55]])blob(MX(x+dx),MY(b.y+dy),b.r*s*MK,b.i*(s===1?1:.75),map*.85);
  }
 }
 if(rain>0){
  tx.globalAlpha=1;tx.lineCap='round';
  for(const d of drops){
   const y=(d.y+t*d.v)%1180-100,x=d.x-(y+100)*.22;
   tx.strokeStyle=`rgba(190,215,255,${.42*rain})`;tx.lineWidth=d.w;tx.beginPath();tx.moveTo(x,y);tx.lineTo(x-d.l*.22,y+d.l);tx.stroke();
  }
 }
 tx.globalAlpha=1;
 const shade=tx.createLinearGradient(0,0,1150,0);shade.addColorStop(0,'rgba(6,26,64,.92)');shade.addColorStop(.6,'rgba(6,26,64,.6)');shade.addColorStop(1,'rgba(6,26,64,0)');tx.fillStyle=shade;tx.fillRect(0,0,1150,1080);
}
let titleRAF=0;
hooks['s-title']={
 enter(){cancelAnimationFrame(titleRAF);if(!motion){drawTitle(6);return;}const start=performance.now();const loop=now=>{drawTitle((now-start)/1000);titleRAF=requestAnimationFrame(loop);};titleRAF=requestAnimationFrame(loop);},
 leave(){cancelAnimationFrame(titleRAF);}
};

/* ---------- 2 fleet: two supplied years joined by a line ---------- */
(function fleet(){
 const W=1080,H=470,x=v=>v===2015?250:830,y=v=>420-v/100000*380;
 const s=el('svg',{viewBox:`0 0 ${W} ${H}`});
 for(const v of[0,25000,50000,75000,100000]){add(s,'line',{x1:90,x2:870,y1:y(v),y2:y(v),stroke:C.grid,'stroke-width':1.2});add(s,'text',{x:76,y:y(v)+8,'text-anchor':'end','font-size':22,fill:C.muted},v?num(v/1000)+'k':'0');}
 for(const yr of[2015,2025])add(s,'text',{x:x(yr),y:458,'text-anchor':'middle','font-size':24,fill:C.muted,'font-weight':500},yr);
 const series=[{name:'Taxis',a:28259,b:12161,c:C.taxi},{name:'Private-hire cars',a:29369,b:95857,c:C.sky}];
 for(const r of series)add(s,'path',{class:'ln',d:`M${x(2015)},${y(r.a)}L${x(2025)},${y(r.b)}`,stroke:r.c,pathLength:1});
 const end=add(s,'g',{class:'end'});
 for(const[i,r]of series.entries()){
  for(const[yr,v]of[[2015,r.a],[2025,r.b]])add(end,'circle',{cx:x(yr),cy:y(v),r:9,fill:r.c,stroke:C.white,'stroke-width':3});
  add(end,'text',{x:x(2015)-20,y:y(r.a)+(i===0?36:-14),'text-anchor':'end','font-family':'Anton','font-size':34,fill:r.c},num(r.a));
  add(end,'text',{x:x(2025)+22,y:y(r.b)+8,'font-family':'Anton','font-size':44,fill:r.c},num(r.b));
  add(end,'text',{x:x(2025)+22,y:y(r.b)+42,'font-size':22,'font-weight':600,fill:r.c},r.name);
 }
 $('#fleet-chart').append(s);
})();

/* ---------- 3 steps and 10 playbook: light up in turn ---------- */
function lightUp(selector,first,step){const items=$$(selector);items.forEach(v=>v.classList.remove('lit'));if(!motion){items.forEach(v=>v.classList.add('lit'));return;}items.forEach((v,i)=>later(()=>v.classList.add('lit'),first+i*step));}
hooks['s-method']={enter:()=>lightUp('#steps .step',500,600)};
hooks['s-playbook']={enter:()=>lightUp('#playbook .tstep',500,4600/6)};

/* ---------- 4 observed storm replay ---------- */
const S=DATA.storm,MAP={k:10.9,x:v=>10+(v-5)*10.9,y:v=>4+(36-v)*10.9};
const analysed=new Map(S.cells.map((c,i)=>[c,i]));
function rainColor(v){if(!(v>0))return C.dry;if(v<=20)return mix(C.skyLight,C.sky,v/20);return mix(C.sky,C.taxi,Math.min(1,(v-20)/40));}
function changeColor(v){return mix(C.white,v<0?C.red:C.sky,Math.min(1,Math.abs(v)/40));}
function stormMap(host,legend){
 const s=add($(host),'svg',{viewBox:'0 0 620 392',role:'img'});const rects=[];
 for(const ring of DATA.land)add(s,'path',{d:ring.map(([x,y],i)=>(i?'L':'M')+MAP.x(x).toFixed(1)+','+MAP.y(y).toFixed(1)).join('')+'Z',fill:'#EDF1F6',stroke:'#D5DEEA','stroke-width':.8});
 const all=[...new Set([...DATA.cells.map(c=>c[0]),...S.cells])];
 for(const cell of all){const i=analysed.get(cell);const r=add(s,'rect',{x:MAP.x(Math.floor(cell/1000)).toFixed(1),y:MAP.y(cell%1000+1).toFixed(1),width:MAP.k-.6,height:MAP.k-.6,fill:C.none,stroke:'#FFFFFF','stroke-width':.4});if(i!==undefined)rects[i]=r;}
 const g=add(s,'g',{transform:'translate(30,350)'});legend(g,s);return rects;
}
const gradient=(s,id,stops)=>{const defs=add(s,'defs');const lg=add(defs,'linearGradient',{id});stops.forEach(([o,c])=>add(lg,'stop',{offset:o,'stop-color':c}));};
const rainRects=stormMap('#map-rain',(g,s)=>{
 gradient(s,'rain-scale',[[0,C.skyLight],[1/3,C.sky],[1,C.taxi]]);
 add(g,'rect',{x:0,y:0,width:34,height:12,fill:C.dry,rx:2});add(g,'text',{x:17,y:36,'text-anchor':'middle','font-size':16,fill:C.muted},'dry');
 add(g,'rect',{x:50,y:0,width:300,height:12,fill:'url(#rain-scale)',rx:2});
 for(const[v,l]of[[0,'>0'],[20,'20'],[60,'≥60 mm/h']])add(g,'text',{x:50+v/60*300,y:36,'text-anchor':v===0?'start':v===60?'end':'middle','font-size':16,fill:C.muted},l);
});
const changeRects=stormMap('#map-change',(g,s)=>{
 gradient(s,'change-scale',[[0,C.red],[.5,C.white],[1,C.sky]]);
 add(g,'rect',{x:0,y:0,width:350,height:12,fill:'url(#change-scale)',rx:2,stroke:'#D5DEEA','stroke-width':.6});
 for(const[v,l]of[[-40,'−40%'],[0,'0'],[40,'+40%']])add(g,'text',{x:(v+40)/80*350,y:36,'text-anchor':v<0?'start':v>0?'end':'middle','font-size':16,fill:C.muted},l);
 add(g,'text',{x:362,y:11,'font-size':16,fill:C.muted},'fewer · more');
});
const totals=S.times.map((_,f)=>({observed:S.vacant[f].reduce((a,b)=>a+b,0),expected:S.baseline[f].reduce((a,b)=>a+b,0)}));
const PEAK=S.times.findIndex(t=>t.slice(11,16)==='09:30');
const line=(()=>{
 const W=1290,H=236,x=i=>78+i*(1250-78)/(S.times.length-1),y=v=>196-(v-1200)/1500*176;
 const s=add($('#storm-line'),'svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':'Actual and expected vacant taxis, 06:30 to 13:30'});
 for(const v of[1500,2000,2500]){add(s,'line',{x1:78,x2:1250,y1:y(v),y2:y(v),stroke:C.grid});add(s,'text',{x:66,y:y(v)+6,'text-anchor':'end','font-size':18,fill:C.muted},num(v));}
 for(const i of[0,PEAK,S.times.length-1])add(s,'text',{x:x(i),y:226,'text-anchor':i===0?'start':i===PEAK?'middle':'end','font-size':18,fill:C.muted},S.times[i].slice(11,16));
 add(s,'path',{d:totals.map((r,i)=>(i?'L':'M')+x(i)+','+y(r.expected)).join(''),fill:'none',stroke:C.muted,'stroke-width':2.5,'stroke-dasharray':'7 6'});
 const obs=add(s,'path',{fill:'none',stroke:C.taxi,'stroke-width':4,'stroke-linejoin':'round'});
 const dot=add(s,'circle',{r:7,fill:C.taxi,stroke:C.white,'stroke-width':2.5});
 const cursor=add(s,'line',{y1:16,y2:202,stroke:C.yellow,'stroke-width':3});
 s.insertBefore(cursor,obs);
 const p=totals[PEAK],gap=p.expected-p.observed;
 const peak=add(s,'g',{opacity:0});
 add(peak,'line',{x1:x(PEAK),x2:x(PEAK),y1:y(p.observed),y2:y(p.expected),stroke:C.red,'stroke-width':5});
 add(peak,'text',{x:x(PEAK)+16,y:y(p.expected)-8,'font-size':22,'font-weight':600,fill:C.red},`09:30 · ${num(gap)} fewer (${num(-gap/p.expected*100,1)}%) · this storm`);
 add(s,'text',{x:1250,y:y(totals.at(-1).expected)-12,'text-anchor':'end','font-size':18,fill:C.muted},'Expected');
 const lab=add(s,'text',{'font-size':18,'font-weight':600,fill:C.taxi},'Actual');
 return f=>{
  obs.setAttribute('d',totals.slice(0,f+1).map((r,i)=>(i?'L':'M')+x(i)+','+y(r.observed)).join(''));
  dot.setAttribute('cx',x(f));dot.setAttribute('cy',y(totals[f].observed));
  cursor.setAttribute('x1',x(f));cursor.setAttribute('x2',x(f));
  lab.setAttribute('x',x(f)+12);lab.setAttribute('y',y(totals[f].observed)+26);
  peak.setAttribute('opacity',f>=PEAK?1:0);
 };
})();
let stormFrame=0;
function setStorm(f){
 stormFrame=f;
 S.cells.forEach((_,i)=>{const v=S.vacant[f][i],b=S.baseline[f][i];rainRects[i].setAttribute('fill',rainColor(S.mmh[f][i]));changeRects[i].setAttribute('fill',changeColor(100*(v/Math.max(1,b)-1)));});
 $('#storm-clock').textContent=S.times[f].slice(11,16);
 const t=totals[f],wet=S.mmh[f].filter(v=>v>0).length;
 $('#storm-tally').innerHTML=`<b>${num(t.observed)}</b> vacant taxis<br>vs <b>${num(t.expected)}</b> expected<br><span class="muted">${wet} of 374 squares with rain</span>`;
 line(f);
}
function stormStep(){const f=(stormFrame+1)%S.times.length;setStorm(f);later(stormStep,f===PEAK?4000:f===S.times.length-1?2000:1500);}
hooks['s-storm']={enter(){if(!motion){setStorm(PEAK);return;}setStorm(0);later(stormStep,1500);}};
setStorm(PEAK);

/* ---------- 5 event cursor sweeping the saved −60 to +180 minutes ---------- */
let eventRAF=0;
const eventCursor=(()=>{
 const svg=$('#event-chart svg'),M=DATA.meta.present_event_timeline,P=M.points;
 const g=add(svg,'g',{id:'event-cursor','pointer-events':'none'});
 const ln=add(g,'line',{y1:M.top,y2:M.bottom,stroke:C.yellow,'stroke-width':3});
 const dot=add(g,'circle',{r:7,fill:C.yellow,stroke:C.taxi,'stroke-width':2.5});
 const box=add(g,'rect',{height:30,rx:6,fill:C.taxi});const label=add(g,'text',{'font-size':17,'font-weight':600,fill:'#fff','font-family':'Poppins'});
 return minute=>{
  let k=P.findIndex(p=>p[2]>=minute);if(k<=0)k=1;const a=P[k-1],b=P[k],f=Math.max(0,Math.min(1,(minute-a[2])/(b[2]-a[2])));
  const sx=a[0]+(b[0]-a[0])*f,sy=a[1]+(b[1]-a[1])*f,pct=a[3]+(b[3]-a[3])*f;
  ln.setAttribute('x1',sx);ln.setAttribute('x2',sx);dot.setAttribute('cx',sx);dot.setAttribute('cy',sy);
  const near=P.find(p=>Math.abs(p[2]-minute)<1.5);
  label.textContent=`${minute>0?'+':minute<0?'−':''}${Math.abs(Math.round(minute))} min`+(near?` · ${num(near[3],1)}%`:'');
  const w=label.getComputedTextLength()+20,bx=Math.min(M.width-w-4,Math.max(4,sx-w/2));
  box.setAttribute('x',bx);box.setAttribute('y',M.top-36);box.setAttribute('width',w);label.setAttribute('x',bx+10);label.setAttribute('y',M.top-15.5);
 };
})();
hooks['s-event']={
 enter(){cancelAnimationFrame(eventRAF);if(!motion){eventCursor(30);return;}let start=null;const run=now=>{if(start===null)start=now;const t=(now-start)/1000,sweep=8,hold=2.5;const m=t<.8?-60:t<.8+sweep?-60+(t-.8)/sweep*240:180;eventCursor(m);if(t>.8+sweep+hold)start=now;eventRAF=requestAnimationFrame(run);};eventRAF=requestAnimationFrame(run);},
 leave(){cancelAnimationFrame(eventRAF);}
};
eventCursor(30);

/* ---------- 6 places: bars grow in; 7 factors; 8 heatmap callouts ---------- */
function grow(){
 if(!motion)return;
 $$('#places-chart g[id^="present_places_bar-bar-"]').forEach(g=>{const i=+g.id.split('-').pop(),path=g.querySelector('path');path.style.transformBox='fill-box';path.style.transformOrigin='0 50%';path.animate([{transform:'scaleX(0)'},{transform:'scaleX(1)'}],{duration:900,delay:350+i*90,easing:'cubic-bezier(.2,.75,.2,1)',fill:'backwards'});});
 $$('#places-chart g[id^="present_places_bar-barlabel-"]').forEach(g=>{const i=+g.id.split('-').pop();g.animate([{opacity:0},{opacity:1}],{duration:500,delay:1000+i*90,fill:'backwards'});});
}
hooks['s-places']={enter:grow};
function factorsIn(){if(!motion)return;$$('#factors-chart g[id^="present_factors-factor"]').forEach(g=>{const i=+g.id.split('-').pop();g.animate([{opacity:0},{opacity:1}],{duration:500,delay:500+i*140,fill:'backwards'});});}
hooks['s-factors']={enter:factorsIn};
function callouts(){if(!motion)return;$$('#planning-chart g[id*="-callout-"]').forEach(g=>{const k=+g.id.split('-').pop();g.animate([{opacity:0},{opacity:1}],{duration:600,delay:900+k*500,fill:'backwards'});});}
hooks['s-planning']={enter:callouts};

/* ---------- 9 Storm Builder and 11 dashboard: load on entry, unload on exit ---------- */
function embed(hostId,src,title,onReady){
 const host=$('#'+hostId);let timer=0;
 return{
  enter(){
   host.querySelector('.fallback').hidden=true;host.querySelector('.loading').hidden=false;
   const frame=document.createElement('iframe');frame.title=title;frame.loading='eager';frame.referrerPolicy='no-referrer';frame.allow='fullscreen';
   let loaded=false;frame.addEventListener('load',()=>{loaded=true;host.querySelector('.loading').hidden=true;onReady?.(frame);});
   timer=setTimeout(()=>{if(!loaded){frame.remove();host.querySelector('.loading').hidden=true;host.querySelector('.fallback').hidden=false;}},8000);
   frame.src=src;host.append(frame);
  },
  leave(){clearTimeout(timer);host.querySelector('iframe')?.remove();host.querySelector('.loading').hidden=false;}
 };
}
const BUILDER='https://storm-builder-sg.vercel.app';
hooks['s-builder']=embed('builder-frame',BUILDER+'/?presentation=1','Storm Builder live scenario tool');
addEventListener('message',e=>{const frame=$('#builder-frame iframe');if(e.origin!==BUILDER||!frame||e.source!==frame.contentWindow||e.data?.type!=='storm-builder:ready')return;frame.contentWindow.postMessage({type:'storm-builder:presentation',action:motion?'play':'pause'},BUILDER);});
hooks['s-dashboard']=embed('dash-frame','https://golden-beijinho-83f174.netlify.app','Dispatcher dashboard prototype with sample data');

/* ---------- start ---------- */
fit();
window.PRESENT={show,current:()=>current,stormFrame:()=>stormFrame,slides:slides.length,main:MAIN};
show(Math.max(0,(parseInt(location.hash.slice(1),10)||1)-1));
