'use strict';
// Presentation runtime for outputs/story/present.html (decisions 174-175). Charts draw saved data only;
// the title animation is illustrative (synthetic rain and taxi dots on the Storm Builder's road map).
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const NS='http://www.w3.org/2000/svg';
const C={navy:'#0B1F3A',slate:'#2E4A6B',steel:'#4F7CAC',rainLow:'#B9CDE4',ink:'#1A2433',muted:'#5B6676',grid:'#DDE3EA',red:'#B5473A',dry:'#E3E7ED',none:'#F4F6F9',white:'#FFFFFF',yellow:'#F2B705'};
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
 const tag=slide.dataset.appendix;
 $('#number').innerHTML=tag?`<b>${tag==='References'?tag:'Appendix '+tag}</b>`:`<b>${index+1}</b> / ${MAIN}`;
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
 else if(k==='a'||k==='A')goAppendix('A1');
 else if(k==='Escape'&&slides[current]?.dataset.appendix)show(returnTo??MAIN-1);
});
let returnTo=null;
function goAppendix(tag){if(!slides[current]?.dataset.appendix)returnTo=current;show(slides.findIndex(s=>s.dataset.appendix===tag));}
$$('[data-goto]').forEach(b=>b.addEventListener('click',()=>goAppendix(b.dataset.goto)));
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
 $('#p-title').textContent=`${slide.dataset.appendix||current+1+' / '+MAIN} · ${slide.dataset.title}`;
 $('#p-notes').textContent=slide.querySelector('.notes')?.textContent.trim()||'';
 $('#p-next').textContent=next?next.dataset.title:'End of presentation';
}

/* ---------- 1 title: illustrative radar-style rain and taxi dots on the Storm Builder's road map ----------
   World units are 10 m (Storm Builder projection). Everything is periodic in LOOP seconds, so the loop is seamless. */
const tc=$('#title-canvas'),tx=tc.getContext('2d'),T=DATA.title,LOOP=40;  // 40 s loop: half the earlier speed (decision 176)
const WX0=300,WX1=5600,WY0=900,WY1=3900,S0=1920/(WX1-WX0)*1.02,SB=S0*1.35;
const base=document.createElement('canvas');base.width=Math.ceil((WX1-WX0)*SB);base.height=Math.ceil((WY1-WY0)*SB);
(function drawBase(){
 const b=base.getContext('2d');b.setTransform(SB,0,0,-SB,-WX0*SB,WY1*SB);
 const poly=(rings,flat=true)=>{const p=new Path2D();for(const r of rings){p.moveTo(r[0],r[1]);for(let i=2;i<r.length;i+=2)p.lineTo(r[i],r[i+1]);p.closePath();}return p;};
 b.save();b.setTransform(1,0,0,1,0,0);b.fillStyle='#06111F';b.fillRect(0,0,base.width,base.height);b.restore();
 const land=poly(T.land);b.fillStyle='#0E2341';b.fill(land);
 b.fillStyle='#10304A';b.fill(poly(T.green),'evenodd');
 b.fillStyle='#08182C';b.fill(poly(T.water),'evenodd');
 b.lineJoin='round';b.lineCap='round';
 const style=[[1.7,'rgba(160,190,230,.62)'],[1.1,'rgba(120,150,195,.42)'],[.75,'rgba(105,135,180,.28)']];
 for(let c=2;c>=0;c--){const p=new Path2D();for(const l of T.roads[c]){p.moveTo(l[0],l[1]);for(let i=2;i<l.length;i+=2)p.lineTo(l[i],l[i+1]);}b.lineWidth=style[c][0]/SB;b.strokeStyle=style[c][1];b.stroke(p);}
 b.lineWidth=1.2/SB;b.strokeStyle='rgba(120,160,210,.38)';b.stroke(land);
})();
// rain field on a coarse world grid (160 m), recomputed every other frame
const G=10,GW=Math.ceil((WX1-WX0)/G),GH=Math.ceil((WY1-WY0)/G),field=new Float32Array(GW*GH);
const rainCanvas=document.createElement('canvas');rainCanvas.width=GW;rainCanvas.height=GH;
const rc=rainCanvas.getContext('2d'),img=rc.createImageData(GW,GH);
const BANDS=[[.16,[111,169,138],.60],[.30,[185,196,106],.63],[.46,[216,178,90],.65],[.64,[205,150,96],.62],[.84,[196,128,100],.56]];
const perm=(()=>{const r=rng(91),p=Array.from({length:256},(_,i)=>i);for(let i=255;i>0;i--){const j=Math.floor(r()*(i+1));[p[i],p[j]]=[p[j],p[i]];}return Uint8Array.from([...p,...p]);})();
function vnoise(x,y){const xi=Math.floor(x),yi=Math.floor(y),xf=x-xi,yf=y-yi,u=xf*xf*(3-2*xf),v=yf*yf*(3-2*yf);
 const h=(i,j)=>perm[(perm[(xi+i)&255]+yi+j)&255]/255;const a=h(0,0),b=h(1,0),c=h(0,1),d=h(1,1);return a+(b-a)*u+(c-a)*v+(a-b-c+d)*u*v;}
// rain cells: start/end x, latitude, peak, size, phase in the loop (different track lengths = different speeds)
const CELLS=[[500,4200,3050,1.25,170,.0],[1300,4000,2300,1.0,140,.12],[300,3100,1700,.9,160,.25],[2300,5600,2750,1.0,200,.38],[900,3600,3350,.8,120,.5],[2600,5400,1900,1.1,165,.62],[0,2700,2500,.95,135,.74],[1800,4900,2050,1.2,150,.86],[3200,5800,3200,.85,125,.94]];
function computeRain(t){
 const th=2*Math.PI*t/LOOP,ox=2.2*Math.cos(th),oy=2.2*Math.sin(th);
 field.fill(0);
 for(const[xs,xe,y0,amp,sig,ph]of CELLS){
  const u=((t/LOOP+ph)%1+1)%1,env=Math.pow(Math.sin(Math.PI*u),1.2),cx=xs+(xe-xs)*u,cy=y0+110*Math.sin(2*Math.PI*u+ph*7),A=amp*env,sy=sig*(.7+.5*env),sx=sy*1.45;
  if(A<.02)continue;
  const gx0=Math.max(0,Math.floor((cx-3*sx-WX0)/G)),gx1=Math.min(GW-1,Math.ceil((cx+3*sx-WX0)/G)),gy0=Math.max(0,Math.floor((WY1-(cy+3*sy))/G)),gy1=Math.min(GH-1,Math.ceil((WY1-(cy-3*sy))/G));
  for(let j=gy0;j<=gy1;j++){const y=WY1-j*G,dy=(y-cy)/sy;for(let i=gx0;i<=gx1;i++){const dx=(WX0+i*G-cx)/sx;field[j*GW+i]+=A*Math.exp(-.5*(dx*dx+dy*dy));}}
 }
 const d=img.data;
 for(let j=0;j<GH;j++)for(let i=0;i<GW;i++){
  const k=j*GW+i;let v=field[k];
  if(v>.04){const x=(WX0+i*G)/150,y=(WY1-j*G)/150;v*=.25+1.05*(.6*vnoise(x+ox,y+oy)+.4*vnoise(2.3*x-oy,2.3*y+ox));}
  field[k]=v;let band=-1;for(let b=0;b<BANDS.length;b++)if(v>=BANDS[b][0])band=b;
  const o=k*4;if(band<0){d[o+3]=0;continue;}const[,c,a]=BANDS[band];d[o]=c[0];d[o+1]=c[1];d[o+2]=c[2];d[o+3]=a*255;
 }
 rc.putImageData(img,0,0);
}
function rainAt(x,y){const i=Math.round((x-WX0)/G),j=Math.round((WY1-y)/G);return i<0||j<0||i>=GW||j>=GH?0:field[j*GW+i];}
const dotRand=rng(2702),DOTS=T.routes.map(r=>({r,phase:dotRand(),thr:.45+.5*dotRand()}));
function drawTitle(t,refresh=true){
 const th=2*Math.PI*t/LOOP,z=1.06+.015*Math.sin(th),s=S0*z,cx=2620+85*Math.sin(th+.6),cy=2380+35*Math.sin(2*th);
 if(refresh)computeRain(t);
 tx.setTransform(1,0,0,1,0,0);tx.globalAlpha=1;tx.fillStyle='#06111F';tx.fillRect(0,0,1920,1080);
 const k=s/SB;tx.imageSmoothingEnabled=true;tx.imageSmoothingQuality='high';
 tx.drawImage(base,960+(WX0-cx)*s,540-(WY1-cy)*s,base.width*k,base.height*k);
 tx.drawImage(rainCanvas,960+(WX0-cx)*s,540-(WY1-cy)*s,GW*G*s,GH*G*s);
 tx.fillStyle='#3FC1B0';
 for(const dot of DOTS){
  const p=dot.r,n=p.length/2,w=((dot.phase+t/LOOP)%1)*2,u=w<1?w:2-w,f=u*(n-1),a=Math.floor(f),b=Math.min(n-1,a+1),q=f-a;
  const x=p[2*a]+(p[2*b]-p[2*a])*q,y=p[2*a+1]+(p[2*b+1]-p[2*a+1])*q,rain=rainAt(x,y);
  if(rain>dot.thr)continue;
  tx.globalAlpha=1-.7*Math.min(1,Math.max(0,(rain-.15)/.35));
  tx.fillRect(960+(x-cx)*s-1.6,540-(y-cy)*s-1.6,3.2,3.2);
 }
 tx.globalAlpha=1;
 const shade=tx.createLinearGradient(0,0,1250,0);shade.addColorStop(0,'rgba(11,31,58,.94)');shade.addColorStop(.55,'rgba(11,31,58,.7)');shade.addColorStop(1,'rgba(11,31,58,0)');
 tx.fillStyle=shade;tx.fillRect(0,0,1250,1080);
}
let titleRAF=0,titleFrame=0;
hooks['s-title']={
 enter(){cancelAnimationFrame(titleRAF);if(!motion){drawTitle(7);return;}const start=performance.now();
  const loop=now=>{const t=((now-start)/1000)%LOOP;drawTitle(t,titleFrame++%2===0);titleRAF=requestAnimationFrame(loop);};titleRAF=requestAnimationFrame(loop);},
 leave(){cancelAnimationFrame(titleRAF);}
};
window.TITLE_FRAME=t=>{cancelAnimationFrame(titleRAF);drawTitle(t);};

/* ---------- 2 fleet: two supplied years joined by a line ---------- */
(function fleet(){
 const W=1080,H=470,x=v=>v===2015?250:830,y=v=>420-v/100000*380;
 const s=el('svg',{viewBox:`0 0 ${W} ${H}`});
 for(const v of[0,25000,50000,75000,100000]){add(s,'line',{x1:90,x2:870,y1:y(v),y2:y(v),stroke:C.grid,'stroke-width':1});add(s,'text',{x:76,y:y(v)+9,'text-anchor':'end','font-size':28,fill:C.muted},v?num(v/1000)+'k':'0');}
 for(const yr of[2015,2025])add(s,'text',{x:x(yr),y:462,'text-anchor':'middle','font-size':28,fill:C.muted,'font-weight':500},yr);
 const series=[{name:'Taxis',a:28259,b:12161,c:C.slate},{name:'Private-hire cars',a:29369,b:95857,c:C.steel}];
 for(const r of series)add(s,'path',{class:'ln',d:`M${x(2015)},${y(r.a)}L${x(2025)},${y(r.b)}`,stroke:r.c,pathLength:1});
 const end=add(s,'g',{class:'end'});
 for(const[i,r]of series.entries()){
  for(const[yr,v]of[[2015,r.a],[2025,r.b]])add(end,'circle',{cx:x(yr),cy:y(v),r:6,fill:r.c,stroke:C.white,'stroke-width':2});
  add(end,'text',{x:x(2015)-20,y:y(r.a)+(i===0?36:-14),'text-anchor':'end','font-size':32,'font-weight':500,fill:r.c},num(r.a));
  add(end,'text',{x:x(2025)+22,y:y(r.b)+12,'font-size':40,'font-weight':500,fill:r.c},num(r.b));
  add(end,'text',{x:x(2025)+22,y:y(r.b)+46,'font-size':28,fill:C.muted},r.name);
 }
 $('#fleet-chart').append(s);
})();

/* ---------- 3 steps and 10 playbook: light up in turn ---------- */
function lightUp(selector,first,step){const items=$$(selector);items.forEach(v=>v.classList.remove('lit','current'));const on=i=>{items.forEach(v=>v.classList.remove('current'));items[i].classList.add('lit','current');};if(!motion){items.forEach((_,i)=>on(i));return;}items.forEach((v,i)=>later(()=>on(i),first+i*step));}
hooks['s-method']={enter:()=>lightUp('#steps .step',500,600)};
hooks['s-playbook']={enter:()=>lightUp('#playbook .tstep',500,4600/6)};

/* ---------- 4 observed storm replay ---------- */
const S=DATA.storm,MAP={k:10.9,x:v=>10+(v-5)*10.9,y:v=>4+(36-v)*10.9};
const analysed=new Map(S.cells.map((c,i)=>[c,i]));
function rainColor(v){if(!(v>0))return C.dry;if(v<=20)return mix(C.rainLow,C.steel,v/20);return mix(C.steel,C.navy,Math.min(1,(v-20)/40));}
function changeColor(v){return mix(C.white,v<0?C.red:C.steel,Math.min(1,Math.abs(v)/40));}
function stormMap(host,legend){
 const s=add($(host),'svg',{viewBox:'0 0 620 412',role:'img'});const rects=[];
 for(const ring of DATA.land)add(s,'path',{d:ring.map(([x,y],i)=>(i?'L':'M')+MAP.x(x).toFixed(1)+','+MAP.y(y).toFixed(1)).join('')+'Z',fill:'#EEF1F5',stroke:C.grid,'stroke-width':.8});
 const all=[...new Set([...DATA.cells.map(c=>c[0]),...S.cells])];
 for(const cell of all){const i=analysed.get(cell);const r=add(s,'rect',{x:MAP.x(Math.floor(cell/1000)).toFixed(1),y:MAP.y(cell%1000+1).toFixed(1),width:MAP.k-.6,height:MAP.k-.6,fill:C.none,stroke:'#FFFFFF','stroke-width':.4});if(i!==undefined)rects[i]=r;}
 const g=add(s,'g',{transform:'translate(20,342)'});legend(g,s);return rects;
}
const gradient=(s,id,stops)=>{const defs=add(s,'defs');const lg=add(defs,'linearGradient',{id});stops.forEach(([o,c])=>add(lg,'stop',{offset:o,'stop-color':c}));};
const rainRects=stormMap('#map-rain',(g,s)=>{
 gradient(s,'rain-scale',[[0,C.rainLow],[1/3,C.steel],[1,C.navy]]);
 add(g,'rect',{x:0,y:0,width:46,height:14,fill:C.dry,rx:2});add(g,'text',{x:23,y:48,'text-anchor':'middle','font-size':28,fill:C.muted},'dry');
 add(g,'rect',{x:70,y:0,width:360,height:14,fill:'url(#rain-scale)',rx:2});
 for(const[v,l]of[[0,'>0'],[20,'20'],[60,'≥60 mm/h']])add(g,'text',{x:70+v/60*360,y:48,'text-anchor':v===0?'start':v===60?'end':'middle','font-size':28,fill:C.muted},l);
});
const changeRects=stormMap('#map-change',(g,s)=>{
 gradient(s,'change-scale',[[0,C.red],[.5,C.white],[1,C.steel]]);
 add(g,'rect',{x:0,y:0,width:420,height:14,fill:'url(#change-scale)',rx:2,stroke:C.grid,'stroke-width':.6});
 for(const[v,l]of[[-40,'−40%'],[0,'0'],[40,'+40%']])add(g,'text',{x:(v+40)/80*420,y:48,'text-anchor':v<0?'start':v>0?'end':'middle','font-size':28,fill:C.muted},l);
});
const totals=S.times.map((_,f)=>({observed:S.vacant[f].reduce((a,b)=>a+b,0),expected:S.baseline[f].reduce((a,b)=>a+b,0)}));
const PEAK=S.times.findIndex(t=>t.slice(11,16)==='09:30');
const line=(()=>{
 const W=1109,H=215,x=i=>92+i*(1090-92)/(S.times.length-1),y=v=>168-(v-1200)/1500*152;
 const s=add($('#storm-line'),'svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':'Actual and expected vacant taxis, 06:30 to 13:30'});
 for(const v of[1500,2000,2500]){add(s,'line',{x1:92,x2:1090,y1:y(v),y2:y(v),stroke:C.grid});add(s,'text',{x:80,y:y(v)+8,'text-anchor':'end','font-size':24,fill:C.muted},num(v));}
 for(const i of[0,PEAK,S.times.length-1])add(s,'text',{x:x(i),y:206,'text-anchor':i===0?'start':i===PEAK?'middle':'end','font-size':24,fill:C.muted},S.times[i].slice(11,16));
 add(s,'path',{d:totals.map((r,i)=>(i?'L':'M')+x(i)+','+y(r.expected)).join(''),fill:'none',stroke:C.muted,'stroke-width':2.5,'stroke-dasharray':'7 6'});
 const obs=add(s,'path',{fill:'none',stroke:C.navy,'stroke-width':3,'stroke-linejoin':'round'});
 const dot=add(s,'circle',{r:6,fill:C.navy,stroke:C.white,'stroke-width':2});
 const cursor=add(s,'line',{y1:12,y2:176,stroke:C.steel,'stroke-width':1.5,'stroke-dasharray':'4 4'});
 s.insertBefore(cursor,obs);
 const p=totals[PEAK],gap=p.expected-p.observed;
 const peak=add(s,'g',{opacity:0});
 add(peak,'line',{x1:x(PEAK),x2:x(PEAK),y1:y(p.observed),y2:y(p.expected),stroke:C.red,'stroke-width':4});
 add(peak,'text',{x:x(PEAK)+16,y:y(p.expected)-8,'font-size':24,'font-weight':500,fill:C.red},`09:30 · ${num(gap)} fewer (${num(-gap/p.expected*100,1)}%) · this storm`);
 add(s,'text',{x:1090,y:y(totals.at(-1).expected)-12,'text-anchor':'end','font-size':24,fill:C.muted},'Expected');
 const lab=add(s,'text',{'font-size':24,'font-weight':500,fill:C.navy},'Actual');
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
 $('#storm-tally').innerHTML=`<span class="num">${num(t.observed)}</span> vacant vs <span class="num">${num(t.expected)}</span> expected · <span class="muted">${wet} of 374 squares wet</span>`;
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
 const ln=add(g,'line',{y1:M.top,y2:M.bottom,stroke:C.navy,'stroke-width':1.5});
 const dot=add(g,'circle',{r:6,fill:C.white,stroke:C.navy,'stroke-width':2.5});
 const box=add(g,'rect',{height:30,rx:4,fill:C.navy});const label=add(g,'text',{'font-size':17.3,'font-weight':500,fill:'#fff','font-family':'Poppins'});
 return minute=>{
  let k=P.findIndex(p=>p[2]>=minute);if(k<=0)k=1;const a=P[k-1],b=P[k],f=Math.max(0,Math.min(1,(minute-a[2])/(b[2]-a[2])));
  const sx=a[0]+(b[0]-a[0])*f,sy=a[1]+(b[1]-a[1])*f,pct=a[3]+(b[3]-a[3])*f;
  ln.setAttribute('x1',sx);ln.setAttribute('x2',sx);dot.setAttribute('cx',sx);dot.setAttribute('cy',sy);
  const near=P.find(p=>Math.abs(p[2]-minute)<1.5);
  label.textContent=`${minute>0?'+':minute<0?'−':''}${Math.abs(Math.round(minute))} min`+(near?` · ${num(near[3],1)}%`:'');
  const w=label.getComputedTextLength()+20,bx=Math.min(M.width-w-4,Math.max(4,sx-w/2));
  box.setAttribute('x',bx);box.setAttribute('y',M.bottom-40);box.setAttribute('width',w);label.setAttribute('x',bx+10);label.setAttribute('y',M.bottom-19.5);
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
