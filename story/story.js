'use strict';
const C={navy:'#14295b',blue:'#2c5eaa',light:'#8fb8f2',pale:'#dce6f4',red:'#c0453c',ink:'#14203a',muted:'#5a6683',grid:'#e4eaf4',land:'#e4eaf4',none:'#f2f4f7',white:'#ffffff'};
const NS='http://www.w3.org/2000/svg';
let currentStormRows=DATA.storm;
const state={where:'absolute',cell:48022,horizon:30,morning:'day',category:'All',search:'',expanded:false,modal:null,part:0};
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const n=(v,d=1)=>Number(v).toFixed(d).replace('-','−');
const pct=(v,d=1)=>`${n(v,d)}%`;
const sign=(v,d=1)=>`${v>0?'+':''}${n(v,d)}`;
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function el(tag,attrs={},text){const v=document.createElementNS(NS,tag);for(const[k,val]of Object.entries(attrs))v.setAttribute(k,val);if(text!==undefined)v.textContent=text;return v;}
function add(s,tag,attrs,text){const v=el(tag,attrs,text);s.append(v);return v;}
function txt(s,x,y,value,opts={}){return add(s,'text',{x,y,fill:C.muted,'font-size':12,...opts},value);}
function line(s,x1,y1,x2,y2,color=C.grid,width=1,dash){return add(s,'line',{x1,y1,x2,y2,stroke:color,'stroke-width':width,...(dash?{'stroke-dasharray':dash}:{})});}
function textLines(s,x,y,lines,opts={}){const t=txt(s,x,y,'',opts);lines.forEach((v,i)=>t.append(el('tspan',{x,dy:i?16:0},v)));return t;}
function wrap(value,max=19){const out=[];let v='';for(const word of value.split(' ')){if(v&&v.length+word.length+1>max){out.push(v);v=word;}else v+=(v?' ':'')+word;}if(v)out.push(v);return out;}
function chart(id,height){const host=$('#'+id),w=Math.max(280,Math.round(host.clientWidth)),s=el('svg',{viewBox:`0 0 ${w} ${height}`,width:w,height,role:'group','aria-label':host.getAttribute('aria-label')||'Data chart'});host.replaceChildren(s);return{s,w,h:height,mobile:w<550};}
const scale=(domain,range)=>v=>range[0]+(v-domain[0])/(domain[1]-domain[0])*(range[1]-range[0]);
function axisX(s,x,ticks,y,format=v=>v,label='',w){line(s,x(ticks[0]),y,x(ticks.at(-1)),y,C.grid);for(const v of ticks){line(s,x(v),y,x(v),y+4,C.grid);txt(s,x(v),y+22,format(v),{'text-anchor':'middle','font-size':11});}if(label)textLines(s,w/2,y+43,wrap(label,Math.floor((w-20)/6)),{'text-anchor':'middle','font-size':11});}
function axisY(s,y,ticks,xl,xr,format=v=>v){for(const v of ticks){line(s,xl,y(v),xr,y(v),C.grid);txt(s,xl-12,y(v)+4,format(v),{'text-anchor':'end','font-size':11});}}
function ci(s,x,lo,hi,y,color,value,{hollow=false}={}){line(s,x(lo),y,x(hi),y,color,1.8);for(const v of[lo,hi])line(s,x(v),y-4,x(v),y+4,color,1.6);add(s,'circle',{cx:x(value),cy:y,r:4.5,fill:hollow?C.white:color,stroke:color,'stroke-width':1.7});}
const tooltip=$('#tooltip');
function showTip(event,html){tooltip.innerHTML=html;tooltip.hidden=false;const box=event.currentTarget.getBoundingClientRect(),px=event.clientX??(box.left+box.width/2),py=event.clientY??(box.top+box.height/2);tooltip.style.left=Math.max(9,Math.min(window.innerWidth-tooltip.offsetWidth-10,px+14))+'px';tooltip.style.top=Math.max(10,Math.min(window.innerHeight-tooltip.offsetHeight-10,py+14))+'px';}
function bindTip(node,content){const html=()=>typeof content==='function'?content():content;node.addEventListener('pointerenter',e=>showTip(e,html()));node.addEventListener('pointermove',e=>showTip(e,html()));node.addEventListener('pointerleave',()=>tooltip.hidden=true);node.addEventListener('focus',e=>showTip(e,html()));node.addEventListener('blur',()=>tooltip.hidden=true);}
function pointTarget(s,x,y,label,html){const p=add(s,'circle',{cx:x,cy:y,r:13,fill:'transparent',tabindex:0,role:'img','aria-label':label});bindTip(p,html);}
function drawEffects(){
 const{s,w}=chart('chart-effects',370),x=scale([-18,0],[w<550?93:145,w-82]);
 for(const[i,term]of['light','moderate','heavy'].entries()){
  const yy=65+i*94;if(i===2)add(s,'rect',{x:0,y:yy-25,width:w,height:77,rx:6,fill:'#fbf2f1'});
  txt(s,4,yy+9,term[0].toUpperCase()+term.slice(1),{fill:C.ink,'font-size':13,'font-weight':500});
  for(const[model,off,color]of[['abs',0,i===2?C.red:C.navy],['share',27,C.blue]]){
   const r=DATA.effects.find(r=>r.term===term&&r.model===model);ci(s,x,r.pct_lo,r.pct_hi,yy+off,color,r.pct);
   txt(s,w-3,yy+off+5,pct(r.pct),{fill:color,'font-size':14,'font-weight':600,'text-anchor':'end'});
   pointTarget(s,x(r.pct),yy+off,`${term}, ${model}, ${pct(r.pct)}`,`<strong>${term[0].toUpperCase()+term.slice(1)} · ${model==='abs'?'vacant count':'citywide share'}</strong>${pct(r.pct,2)}<br>95% CI: ${pct(r.pct_lo,2)} to ${pct(r.pct_hi,2)}`);
  }
 }
 axisX(s,x,[-15,-10,-5,0],316,v=>v+'%','Change versus dry weather',w);
}
function drawRadar(){
 const{s,w}=chart('chart-radar',370),x=scale([-40,0],[w<500?100:150,w-90]);
 const terms=['light','moderate','heavy','Central Area heavy'];
 for(const[i,term]of terms.entries()){
  const y=40+i*75,rows=i===3?DATA.radarCentral:DATA.radar.filter(r=>r.term===term);
  textLines(s,2,y+8,wrap(term[0].toUpperCase()+term.slice(1),13),{fill:C.ink,'font-size':12});
  const gauge=rows.find(r=>r.source==='gauge'),radar=rows.find(r=>r.source==='radar');
  line(s,x(gauge.pct),y,x(radar.pct),y+20,C.pale,4);
  for(const[source,off,color,abbr]of[['gauge',0,C.navy,'G'],['radar',20,i===3?C.red:C.blue,'R']]){
   const r=rows.find(v=>v.source===source);ci(s,x,r.pct_lo,r.pct_hi,y+off,color,r.pct);txt(s,w-3,y+off+4,`${abbr} ${pct(r.pct)}`,{fill:color,'font-size':11,'font-weight':500,'text-anchor':'end'});
   pointTarget(s,x(r.pct),y+off,`${term}, ${source}, ${pct(r.pct)}`,`<strong>${esc(term)} · ${source}</strong>${pct(r.pct,2)}<br>95% CI ${pct(r.pct_lo,2)} to ${pct(r.pct_hi,2)}`);
  }
 }
 axisX(s,x,[-40,-20,0],308,v=>v+'%','Vacant count versus dry',w);
}
function drawCurve(id,rows,xkey,domainX,domainY,xticks,yticks,{band=true,event=false}={}){
 const{s,w,mobile}=chart(id,event?370:325),h=event?370:325,l=48,r=22,t=event?50:25,b=60,x=scale(domainX,[l,w-r]),y=scale(domainY,[h-b,t]);
 if(event){
  for(const[a,b,title]of[[0,60,'First hour'],[60,150,'Later'],[150,180,'Within noise']]){add(s,'rect',{x:x(a),y:t,width:x(b)-x(a),height:h-60-t,fill:a===0?'#edf1f8':'#f7f9fc'});if(!mobile||a<150)txt(s,(x(a)+x(b))/2,24,title,{'text-anchor':'middle','font-size':10});}
 }
 axisY(s,y,yticks,l,w-r,v=>v+'%');
 if(band){const upper=rows.map(r=>`${x(r[xkey])},${y(r.pct_hi??r.hi)}`),lower=[...rows].reverse().map(r=>`${x(r[xkey])},${y(r.pct_lo??r.lo)}`);add(s,'path',{d:'M'+upper.concat(lower).join('L')+'Z',fill:C.pale,opacity:.9});}
 line(s,l,y(0),w-r,y(0),C.muted,.9);
 add(s,'path',{d:rows.map((r,i)=>(i?'L':'M')+x(r[xkey])+','+y(r.pct)).join(''),fill:'none',stroke:C.navy,'stroke-width':2.4,'stroke-linecap':'round','stroke-linejoin':'round'});
 if(event){line(s,x(0),t,x(0),h-b,C.blue,1.2,'4 4');txt(s,x(0)+7,t+20,'Rain starts',{fill:C.blue,'font-size':10});}
 for(const row of rows){
  if(event||row[xkey]===1){add(s,'circle',{cx:x(row[xkey]),cy:y(row.pct),r:row[xkey]===1?5:3.2,fill:row[xkey]===1?C.red:C.navy});}
  pointTarget(s,x(row[xkey]),y(row.pct),`${row[xkey]} ${event?'minutes':'mm/h'}: ${pct(row.pct)}`,`<strong>${row[xkey]} ${event?'minutes from onset':'mm/h'}</strong>${pct(row.pct,2)}<br>95% CI ${pct(row.pct_lo??row.lo,2)} to ${pct(row.pct_hi??row.hi,2)}`);
 }
 const cursor=add(s,'g',{'data-curve-cursor':id});line(cursor,0,t,0,h-b,C.red,1,'3 4');add(cursor,'circle',{cx:0,cy:0,r:5,fill:C.red,stroke:C.white,'stroke-width':2});
 axisX(s,x,xticks,h-b,v=>v,event?'Minutes from local rain onset':'Rain intensity (mm/h)',w);
}
function horizontalBars(id,rows,{max=25,ticks=[0,5,10,15,20,25],axis='',height,rowHeight=60}={}){
 const{s,w,mobile}=chart(id,height||rows.length*rowHeight+90),l=mobile?108:180,r=id==='chart-policy'?(mobile?105:145):(mobile?70:105),x=scale([0,max],[l,w-r]);
 for(const[i,row]of rows.entries()){
  const y=28+i*rowHeight;colorBar(s,row,y);
  function colorBar(s,row,y){
   const color=row.color||C.navy;add(s,'rect',{x:l,y:y-11,width:Math.max(.5,x(row.value)-l),height:22,rx:3,fill:color});
   textLines(s,l-13,y+4,wrap(row.label,mobile?14:25),{'text-anchor':'end',fill:C.ink,'font-size':mobile?11:12});
   if(row.lo!==undefined){line(s,x(row.lo),y,x(row.hi),y,C.ink,1.2);for(const v of[row.lo,row.hi])line(s,x(v),y-5,x(v),y+5,C.ink,1.2);}
   txt(s,w-1,y+5,row.display,{fill:color,'font-size':mobile?12:14,'font-weight':600,'text-anchor':'end'});
   if(row.tip){const target=add(s,'rect',{x:l,y:y-15,width:Math.max(20,w-r-l),height:30,fill:'transparent',tabindex:0,role:'img','aria-label':row.label+' '+row.display});bindTip(target,row.tip);}
  }
 }
 axisX(s,x,ticks,rows.length*rowHeight+10,v=>v,axis,w);
}
function drawDuration(){horizontalBars('chart-duration',DATA.duration.map((r,i)=>({label:['First 30 min','31–60 min','61–120 min','Over 120 min'][i],value:-r.pct,lo:-r.pct_hi,hi:-r.pct_lo,color:i===3?C.red:C.navy,display:pct(r.pct),tip:`<strong>${esc(r.term)}</strong>${pct(r.pct,2)}<br>95% CI ${pct(r.pct_lo,2)} to ${pct(r.pct_hi,2)}`})),{max:25,axis:'Fewer vacant taxis (%)',rowHeight:58,height:320});}
function nameOf(r){const name=DATA.aliases[r.cell]||r.subzone||`Cell ${r.cell}`;return name===name.toUpperCase()?name.toLowerCase().replace(/(^|\s)\S/g,v=>v.toUpperCase()):name;}
function drawPlaces(){horizontalBars('chart-places',DATA.places.map(r=>({label:nameOf(r),value:r.taxis_lost_per_heavy_half_hour,display:`${n(r.taxis_lost_per_heavy_half_hour)} / ${n(r.expected_vacant_heavy)}`,color:['Downtown Core','Museum','Rochor','Outram','Kallang'].includes(r.planning_area)?C.red:C.navy,tip:`<strong>${esc(nameOf(r))}</strong>${n(r.taxis_lost_per_heavy_half_hour,3)} fewer / ${n(r.expected_vacant_heavy,3)} expected<br>${pct(r.abs_pct,2)}; 95% CI ${pct(r.abs_lo,2)} to ${pct(r.abs_hi,2)}`})),{max:8,ticks:[0,2,4,6,8],axis:'Fewer taxis per heavy-rain half-hour',rowHeight:37,height:540});}
function mix(a,b,f){const A=a.slice(1).match(/../g).map(x=>parseInt(x,16)),B=b.slice(1).match(/../g).map(x=>parseInt(x,16));return'#'+A.map((v,i)=>Math.round(v*(1-f)+B[i]*f).toString(16).padStart(2,'0')).join('');}
function change(v){return mix(C.white,v<0?C.red:C.blue,Math.min(1,Math.abs(v)/40));}
function sequential(v,max=60){const stops=[C.pale,C.light,C.blue,C.navy],t=Math.min(2.999,Math.max(0,v)/max*3),k=Math.floor(t);return mix(stops[k],stops[k+1],t-k);}
function mapChart(id,rows,{value,filter=()=>true,hero=false,callback,markers=[]}={}){
 const host=$('#'+id),W=900,H=490,k=Math.min(840/55,430/30),ox=(W-55*k)/2,oy=H-30;
 const X=v=>ox+(v-5)*k,Y=v=>oy-(v-6)*k;
 const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:callback?'group':'img','aria-label':host.getAttribute('aria-label')||'Map of Singapore vacant-taxi supply'}),defs=add(svg,'defs',{}),clip=add(defs,'clipPath',{id:id+'-clip'});add(clip,'rect',{x:0,y:0,width:W,height:H});
 const g=add(svg,'g',{'clip-path':`url(#${id}-clip)`});
 for(const ring of DATA.land)add(g,'path',{d:ring.map(([x,y],i)=>(i?'L':'M')+X(x)+','+Y(y)).join('')+'Z',fill:hero?'#a6ccd0':C.land,stroke:hero?'#c7e0e4':C.land,'stroke-width':.6});
 const byCell=new Map(rows.map(r=>[r.cell,r]));
 for(const cell of DATA.cells.filter(c=>c.land)){
  const r=byCell.get(cell.cell),visible=r&&filter(r),v=visible?value(r):null,fill=v===null?(hero?'#d7e8ea':C.none):id==='map-rain'?sequential(v):change(v);
  const rect=add(g,'rect',{x:X(Math.floor(cell.cell/1000)),y:Y(cell.cell%1000+1),width:k-.5,height:k-.5,fill,stroke:hero?'#bed9df':'#fbfcfe','stroke-width':hero?.7:.4});
  if(r&&!hero){
   const named=id==='map-where'&&visible?nameOf(r):[48022,33014,33015].includes(r.cell)?(DATA.aliases[r.cell]):`Square ${r.cell}`;
   rect.dataset.cell=r.cell;
   if(callback){rect.setAttribute('tabindex',visible?0:-1);rect.setAttribute('role','button');rect.setAttribute('aria-label',`${visible?named:'Square '+r.cell}, ${visible?pct(value(r)):'no presentable estimate'}`);rect.addEventListener('pointerenter',()=>callback(r));rect.addEventListener('focus',()=>callback(r));rect.addEventListener('click',()=>callback(r));}
   else{
    rect.setAttribute('tabindex',r.cell===48022||markers.some(q=>q.cell===r.cell)?0:-1);
    const tip=id==='map-island'?`<strong>${r.presentable?esc(nameOf(r)):'Square '+r.cell}</strong>${sign(r.share_pct)}% citywide share<br>${sign(r.abs_change_per_half_hour,3)} taxis / ${n(r.expected_vacant,2)} expected`: `<strong>${esc(named)}</strong>${n(r.mmh)} mm/h in the preceding 30 min<br>${r.vacant} / ${n(r.baseline,2)} expected taxis<br>${sign(r.pct)}% vs expected`;
    bindTip(rect,()=>{const row=id==='map-rain'||id==='map-storm'?currentStormRows.find(row=>row.cell===r.cell):r;return id==='map-rain'||id==='map-storm'?`<strong>${esc(named)}</strong>${n(row.mmh)} mm/h in the preceding 30 min<br>${row.vacant} / ${n(row.baseline,2)} expected taxis<br>${sign(row.pct)}% vs expected`:tip;});
   }
  }
 }
 for(const[i,r]of markers.entries()){
  const x=X(Math.floor(r.cell/1000)+.5),y=Y(r.cell%1000+.5);add(g,'circle',{cx:x,cy:y,r:12,fill:C.navy,stroke:C.white,'stroke-width':1.5});txt(g,x,y+4,i+1,{fill:C.white,'font-size':12,'text-anchor':'middle','font-weight':600,'pointer-events':'none'});
 }
 host.replaceChildren(svg);return{svg,X,Y};
}
function updatePlace(r){
 state.cell=r.cell;const share=state.where==='share',valid=share?r.presentable_share:r.presentable_abs;
 if(!valid){$('#place-detail').innerHTML=`<p class="place-eyebrow">SQUARE ${r.cell}</p><h4>No presentable estimate</h4><p class="place-area">The expected-count or uncertainty filter is not met.</p><p class="place-count">Grey does not mean zero rain association.</p>`;return;}
 const value=share?r.share_pct:r.abs_pct,lo=share?r.share_lo:r.abs_lo,hi=share?r.share_hi:r.abs_hi,count=share?-r.abs_change_per_half_hour:r.taxis_lost_per_heavy_half_hour;
 $('#place-detail').innerHTML=`<p class="place-eyebrow">SELECTED SQUARE · ${r.cell}</p><h4>${esc(nameOf(r))}</h4><p class="place-area">${esc(r.planning_area)}</p><p class="place-value" style="color:${value<0?C.red:C.blue}">${sign(value)}%</p><p class="place-unit">${share?'citywide-share change':'vacant-count change'}</p><p class="place-count"><strong>${n(Math.abs(count),2)} ${count<0?'more':'fewer'}</strong> taxis<br>of ${n(r.expected_vacant_heavy,1)} expected</p><p class="place-ci">95% CI: ${sign(lo)}% to ${sign(hi)}%<br>${share?'Count change is from the separate absolute model.':'Same square and time, heavy rain vs no rain.'}</p>`;
 $$('#map-where [data-selected]').forEach(x=>{x.removeAttribute('data-selected');x.setAttribute('stroke','#fbfcfe');x.setAttribute('stroke-width',.4);});
 const rect=$(`#map-where [data-cell="${r.cell}"]`);if(rect){rect.setAttribute('data-selected','true');rect.setAttribute('stroke',C.navy);rect.setAttribute('stroke-width',2);}
}
function drawWhere(){const share=state.where==='share',rows=share?DATA.share:DATA.absolute;mapChart('map-where',rows,{value:r=>share?r.share_pct:r.abs_pct,filter:r=>share?r.presentable_share:r.presentable_abs,callback:updatePlace});const r=rows.find(r=>r.cell===state.cell&&(share?r.presentable_share:r.presentable_abs))||rows.find(r=>share?r.presentable_share:r.presentable_abs);updatePlace(r);$('#where-scale').textContent=`${share?'Change in citywide share':'Change in vacant count'} vs no-rain expectation · colour capped at ±40%`;}
function drawMaps(){mapChart('hero-map',DATA.storm,{value:r=>r.pct,hero:true});drawWhere();mapChart('map-rain',DATA.storm,{value:r=>r.mmh});mapChart('map-storm',DATA.storm,{value:r=>r.pct});const gains=DATA.island.filter(r=>r.absolute==='more taxis').sort((a,b)=>a.cell-b.cell);mapChart('map-island',DATA.island,{value:r=>r.share_pct,markers:gains});$('#island-gainers').innerHTML=gains.map((r,i)=>`<p><b>${i+1} · ${r.presentable?esc(nameOf(r)):'Cell '+r.cell}</b> &nbsp; ${sign(r.abs_change_per_half_hour,3)} taxis / ${n(r.expected_vacant,2)} expected${r.presentable?'':' · below naming threshold'}</p>`).join('');}
function drawPlanning(){
 const host=$('#chart-planning'),grid=document.createElement('div');grid.className='planning-heatmap';grid.setAttribute('role','table');grid.setAttribute('aria-label','Fewer vacant taxis per half-hour by area and weekday time band');
 const bands=['00-07','07-10','10-17','17-20','20-24'],max=Math.max(...DATA.planning.map(r=>r.abs_loss_taxis_per_half_hour));
 function cell(text,cls=''){const v=document.createElement('div');v.className=cls;v.textContent=text;grid.append(v);return v;}
 cell('Weekday','heat-head');for(const band of bands)cell(band.replace('-','–'),'heat-head');
 for(const area of DATA.planningOrder){cell(area.toLowerCase().replace(/(^|\s)\S/g,v=>v.toUpperCase()),'heat-label');for(const band of bands){const r=DATA.planning.find(r=>r.planning_area===area&&r.time_band===band),value=r.abs_loss_taxis_per_half_hour,v=cell(Math.abs(value)<.05?'0.0':n(value),'heat-cell');v.style.background=sequential(Math.max(0,value),max);v.style.color=value/max>.5?C.white:C.ink;v.setAttribute('tabindex',0);v.setAttribute('role','cell');v.setAttribute('aria-label',`${area}, ${band}, ${n(Math.abs(value))} ${value<0?'more':'fewer'} taxis`);bindTip(v,`<strong>${esc(area)} · ${band.replace('-','–')}</strong>${n(Math.abs(value),2)} ${value<0?'more':'fewer'} taxis per half-hour<br>${n(r.expected_taxis_per_half_hour,2)} expected<br>${sign(r.pct_change)}% count change`);}}
 host.replaceChildren(grid);
}
function dotRows(id,rows,{domain=[-20,3],ticks=[-20,-10,0],axis='',height,rowHeight=61,thresholds=[]}={}){
 const{s,w,mobile}=chart(id,height||rows.length*rowHeight+90),l=mobile?112:225,r=mobile?70:110,x=scale(domain,[l,w-r]),bottom=rows.length*rowHeight+8;
 if(domain[0]<=0&&domain[1]>=0)line(s,x(0),13,x(0),bottom,C.muted,.9);
 for(const th of thresholds){line(s,x(th.value),13,x(th.value),bottom,C.blue,1,'4 4');if(!mobile)txt(s,x(th.value),12,th.label,{fill:C.blue,'font-size':10,'text-anchor':th.value===.01?'end':'start'});}
 for(const[i,row]of rows.entries()){
  const y=34+i*rowHeight;textLines(s,l-14,y+4,wrap(row.label,mobile?15:29),{'text-anchor':'end',fill:C.ink,'font-size':mobile?11:13});
  line(s,l,y,w-r,y,C.grid,.65);ci(s,x,row.lo,row.hi,y,row.color||C.navy,row.value,{hollow:row.hollow});
  txt(s,w-2,y+5,row.display,{fill:row.color||C.navy,'font-size':mobile?12:14,'font-weight':600,'text-anchor':'end'});
  pointTarget(s,x(row.value),y,row.label+' '+row.display,`<strong>${esc(row.label)}</strong>${row.display}<br>95% CI: ${sign(row.lo,row.decimals??2)} to ${sign(row.hi,row.decimals??2)}${row.ciUnit||''}`);
 }
 axisX(s,x,ticks,bottom,v=>Math.abs(v)<.1&&v!==0?v.toFixed(2):v,axis,w);
}
function drawFactors(){const labels={heavy_x_central_area:'Central Area',heavy_x_mrt_lt300m:'MRT exit <300 m',heavy_x_taxi_stand_300m:'Taxi stand <300 m',heavy_x_mall:'Mall in the square',heavy_x_hdb_units_sd:'HDB density (+1 SD)'};dotRows('chart-factors',Object.entries(labels).map(([term,label],i)=>{const r=DATA.factors.find(v=>v.term===term);return{label,value:r.pct,lo:r.pct_lo,hi:r.pct_hi,display:sign(r.pct)+'%',ciUnit:'%',color:i===0?C.red:C.blue};}),{domain:[-20,4],ticks:[-20,-10,0],axis:'Multiplicative difference in the heavy-rain association (%)',rowHeight:55,height:365});}
function drawForecast(){
 const r=DATA.forecast.find(r=>r.h===state.horizon),rows=[['Persistence','topk_precision_persistence',C.navy],['Regression','topk_precision_glm_no_weather',C.blue],['LightGBM','topk_precision_lgb_no_weather',C.blue],['LightGBM + weather','topk_precision_lgb_weather',C.red]];
 const{s,w,mobile}=chart('chart-forecast',365),l=mobile?106:200,rpad=65,x=scale([0,65],[l,w-rpad]);
 line(s,x(r.base_rate*100),18,x(r.base_rate*100),285,C.muted,1,'4 4');
 for(const[i,[label,key,color]]of rows.entries()){const y=47+i*63;txt(s,l-13,y+5,label==='LightGBM + weather'&&mobile?'LGBM + weather':label,{'text-anchor':'end',fill:C.ink,'font-size':mobile?11:13});add(s,'rect',{x:l,y:y-12,width:x(r[key]*100)-l,height:24,rx:3,fill:color});txt(s,w-2,y+5,pct(r[key]*100,2),{fill:color,'font-size':14,'font-weight':600,'text-anchor':'end'});}
 axisX(s,x,[0,20,40,60],285,v=>v+'%','Share of 19 alerts that are truly low',w);
 txt(s,l,352,`Base rate: ${pct(r.base_rate*100,2)} · dashed line`,{'font-size':10});
 const result=$('[data-main-graph="forecast"] .analysis-notes>div:nth-child(2) p');if(result)result.textContent=`At ${state.horizon} minutes, LightGBM precision is ${pct(r.topk_precision_lgb_no_weather*100,2)}, versus ${pct(r.topk_precision_persistence*100,2)} for persistence. With weather it is ${pct(r.topk_precision_lgb_weather*100,2)}.`;
 $('#forecast-takeaway').innerHTML=`<strong>${pct(r.topk_precision_lgb_no_weather*100)} with LightGBM, versus ${pct(r.topk_precision_persistence*100)} with persistence.</strong> Adding weather gives ${pct(r.topk_precision_lgb_weather*100)}. The model gain comes mainly from taxi information.`;
}
function drawLead(){
 const{s,w,mobile}=chart('chart-lead',350),l=mobile?54:95,r=20,x=scale([0,1],[l,w-r]);
 const keys=['share_warned_before_onset','share_detected_at_or_after_onset_only','share_missed'],colors=[C.blue,C.light,C.pale];
 DATA.lead.forEach((row,i)=>{const y=65+i*110;txt(s,l-12,y+25,row.h+' min',{'text-anchor':'end',fill:C.ink,'font-size':12});let start=0;
 keys.forEach((key,j)=>{const value=row[key],end=start+value;add(s,'rect',{x:x(start),y,width:x(end)-x(start),height:44,fill:colors[j],rx:2});if(value>.12)txt(s,(x(start)+x(end))/2,y+27,pct(value*100,1),{'text-anchor':'middle',fill:j===0?C.white:C.ink,'font-size':13});start=end;});
 txt(s,l,y-14,pct(row.share_warned_before_onset*100,2)+' warned before onset',{fill:C.blue,'font-size':14,'font-weight':600});});
 axisX(s,x,[0,.25,.5,.75,1],275,v=>Math.round(v*100)+'%','Share of low-availability runs',w);
}
function drawPolicy(){
 const choices=[['(c) top-19 forecast ranking, no constraints','Forecast ranking',C.navy],['(c) restricted to cells with a staging point','Eligible + staging',C.blue],['(b) policy, weights = forecast risk','Risk-weighted policy',C.red],['(a) policy as designed','Original policy',C.blue],['all candidate cells (expected >= 4)','All candidate cells',C.light]];
 horizontalBars('chart-policy',choices.map(([variant,label,color])=>{const r=DATA.policy.find(r=>r.variant===variant);return{label,value:r.precision_issue_time*100,display:pct(r.precision_issue_time*100,2)+' / '+n(r.cells_per_decision,1),color,tip:`<strong>${label}</strong>${pct(r.precision_issue_time*100,2)} precision<br>${n(r.cells_per_decision,2)} selected cells per decision`};}),{max:60,ticks:[0,20,40,60],axis:'Targeted cells truly low (%)',rowHeight:58,height:390});
}
function drawHoldout(){dotRows('chart-holdout',DATA.holdout.map((r,i)=>({label:['1 km test-year maximum','October 2026 · storms','2019 · storms'][i],value:r.gain,lo:r.lo,hi:r.hi,display:sign(r.gain,4),color:i===1?C.red:C.navy,hollow:i===1,decimals:4})),{domain:[-.005,.09],ticks:[0,.02,.04,.06,.08],axis:'Weather gain in PR-AUC',rowHeight:78,height:335,thresholds:[{value:.01,label:'Cell bar +.01'},{value:.02,label:'Regional bar +.02'}]});}
function drawMorning(){dotRows('chart-morning',DATA.morning.map(r=>({label:(r.model==='lgb'?'Flexible':'Linear')+' · '+r.label,value:r.deviance_improvement_pct,lo:state.morning==='week'?r.lo_block7:r.lo,hi:state.morning==='week'?r.hi_block7:r.hi,display:sign(r.deviance_improvement_pct)+'%',ciUnit:'%',color:r.deviance_improvement_pct<0?C.red:r.model==='lgb'?C.blue:C.navy})),{domain:[-7,13],ticks:[-5,0,5,10],axis:'Lower prediction deviance with weather (%)',rowHeight:65,height:355});}
function drawSimulation(){
 const{s,w,mobile}=chart('chart-simulation',285),l=mobile?118:235,x=scale([0,10],[l,w-62]);
 for(const[i,r]of DATA.simulation.entries()){
  const y=35+i*66;textLines(s,l-15,y+5,wrap(r.name,mobile?16:28),{fill:C.ink,'text-anchor':'end','font-size':mobile?11:13});
  for(let j=0;j<10;j++)add(s,'rect',{x:x(j)+2,y:y-12,width:Math.max(4,(x(1)-x(0))-5),height:25,rx:3,fill:j<r.passed?(i===1?C.red:C.navy):C.grid});
  txt(s,w-2,y+6,`${r.passed}/10`,{fill:i===1?C.red:C.navy,'font-size':16,'font-weight':600,'text-anchor':'end'});
 }
 line(s,x(7),12,x(7),203,C.blue,1.3,'4 4');txt(s,x(7),225,'At least 7 required',{fill:C.blue,'text-anchor':'middle','font-size':10});txt(s,l,263,mobile?'Full rule also checks direction.':'Storm-count condition only; the full rule also checks direction.',{'font-size':mobile?9:11});
}
function controls(id,update){$$('#'+id+' button').forEach(button=>button.addEventListener('click',()=>{$$('#'+id+' button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));update(button.dataset.value);}));}
controls('where-controls',v=>{state.where=v;drawWhere();morphHost($('#map-where'));});controls('forecast-controls',v=>{state.horizon=Number(v);drawForecast();morphHost($('#chart-forecast'));});controls('morning-controls',v=>{state.morning=v;drawMorning();morphHost($('#chart-morning'));});
function renderCharts(){drawEffects();drawRadar();drawCurve('chart-event',DATA.event,'event_min',[-60,180],[-8,3],[-60,0,60,120,180],[-8,-4,0],{event:true});drawCurve('chart-dose',DATA.dose,'mmh',[0,60],[-18,2],[0,20,40,60],[-15,-10,-5,0]);drawDuration();drawPlaces();drawForecast();drawLead();drawPolicy();drawHoldout();drawMorning();drawSimulation();}
function buildTables(){
 for(const host of $$('[data-table]')){const rows=DATA[host.dataset.table],cols=[...new Set(rows.flatMap(Object.keys))],box=document.createElement('div');box.className='data-table';box.innerHTML=`<table><thead><tr>${cols.map(c=>'<th scope="col">'+esc(c)+'</th>').join('')}</tr></thead><tbody>${rows.map(r=>'<tr>'+cols.map(c=>'<td>'+esc(r[c]??'')+'</td>').join('')+'</tr>').join('')}</tbody></table>`;host.replaceChildren(box);}
}
function renderGallery(){
 const items=DATA.gallery.filter(r=>(state.category==='All'||r.category===state.category)&&[r.title,r.id,r.category].join(' ').toLowerCase().includes(state.search.toLowerCase()));
 const visible=state.expanded?items:items.slice(0,9),grid=$('#evidence-grid');grid.replaceChildren();
 for(const item of visible){const b=document.createElement('button');b.className='evidence-card';b.setAttribute('aria-label',`Open ${item.title}, ${item.parts.length} panel group${item.parts.length>1?'s':''}`);b.innerHTML=`<img loading="lazy" width="444" height="172" src="${item.parts[0]}" alt="Preview: ${esc(item.title)}"><span><small>${esc(item.category)}</small><b>${esc(item.title)}</b><em>${item.parts.length} panel group${item.parts.length>1?'s':''} · open figure ↗</em></span>`;b.addEventListener('click',()=>openFigure(item));grid.append(b);}
 $('#evidence-count').textContent=`Showing ${visible.length} of ${items.length} figures${items.length===44?' · all 44 saved source graphs':''}`;
 const more=$('#show-all');more.hidden=state.expanded||items.length<=9;more.innerHTML=`Show all ${items.length} figures <span aria-hidden="true">↓</span>`;
 if(!items.length)grid.innerHTML='<p class="muted">No matching figures. Try another topic or clear the search.</p>';
}
const dialog=$('#evidence-dialog');
function showPart(){const item=state.modal;$('#modal-title').textContent=item.title;$('#modal-analysis').innerHTML=[['Method',item.method],['Result',item.result],['Practical meaning',item.meaning]].map(([title,text])=>`<div><h3>${title}</h3><p>${esc(text)}</p></div>`).join('');$('#modal-category').textContent=item.category;$('#modal-image').src=item.parts[state.part];$('#modal-image').alt=`${item.title}, panel group ${state.part+1} of ${item.parts.length}`;$('#modal-part').textContent=`${state.part+1} of ${item.parts.length}`;$('#modal-prev').disabled=state.part===0;$('#modal-next').disabled=state.part===item.parts.length-1;$('#modal-source').textContent=`Saved source: ${item.source}. Restyled from frozen evidence; no model was re-estimated.`;}
function openFigure(item){state.modal=item;state.part=0;showPart();dialog.showModal();}
$('#modal-close').addEventListener('click',()=>dialog.close());$('#modal-prev').addEventListener('click',()=>{if(state.part>0){state.part--;showPart();}});$('#modal-next').addEventListener('click',()=>{if(state.part<state.modal.parts.length-1){state.part++;showPart();}});
dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
$('#evidence-search').addEventListener('input',e=>{state.search=e.target.value;state.expanded=false;renderGallery();});$('#show-all').addEventListener('click',()=>{state.expanded=true;renderGallery();});
for(const category of['All',...new Set(DATA.gallery.map(g=>g.category))]){const b=document.createElement('button');b.textContent=category;b.setAttribute('aria-pressed',String(category==='All'));b.addEventListener('click',()=>{state.category=category;state.expanded=false;$$('#evidence-filters button').forEach(v=>v.setAttribute('aria-pressed',String(v===b)));renderGallery();});$('#evidence-filters').append(b);}
const progress=$('.reading-progress i');let scrolling=false;
function onScroll(){if(scrolling)return;scrolling=true;requestAnimationFrame(()=>{const total=document.documentElement.scrollHeight-innerHeight;progress.style.width=(total>0?scrollY/total*100:0)+'%';scrolling=false;tooltip.hidden=true;});}
addEventListener('scroll',onScroll,{passive:true});
const chapterObserver=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting){$$('.masthead nav a').forEach(a=>a.classList.toggle('active',a.hash==='#'+e.target.id));}},{rootMargin:'-10% 0px -65% 0px'});$$('[data-chapter]').forEach(s=>chapterObserver.observe(s));
let resizeTimer;addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(typeof fitScene==='function')fitScene();renderCharts();if(typeof refreshExplorers==='function')refreshExplorers();if(typeof fitScene==='function')fitScene();},140);});
buildTables();drawMaps();drawPlanning();renderGallery();renderCharts();
document.fonts.ready.then(async()=>{await Promise.all([document.fonts.load('400 16px Poppins'),document.fonts.load('500 16px Poppins'),document.fonts.load('600 16px Poppins'),document.fonts.load('400 20px Anton')]);if(!document.fonts.check('16px Poppins')||!document.fonts.check('50px Anton'))throw Error('Required fonts did not load');renderCharts();if(typeof refreshExplorers==='function')refreshExplorers();document.documentElement.dataset.ready='true';});
