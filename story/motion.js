/* Presentation motion and exploration. All endpoints are saved observations or estimates. */
const motionPreference=matchMedia('(prefers-reduced-motion: reduce)');
let motionEnabled=!motionPreference.matches;
const motionButton=$('#motion-toggle');
function updateMotion(){
 document.body.classList.toggle('motion-off',!motionEnabled);
 motionButton.textContent=motionEnabled?'Motion on':'Motion off';
 motionButton.setAttribute('aria-pressed',String(motionEnabled));
 if(!motionEnabled)document.getAnimations().forEach(animation=>animation.finish());
}
motionButton.addEventListener('click',()=>{motionEnabled=!motionEnabled;updateMotion();if(!motionEnabled)pausePlayers();});
motionPreference.addEventListener('change',e=>{motionEnabled=!e.matches;updateMotion();if(!motionEnabled)pausePlayers();});
function morphHost(host){if(motionEnabled)host.animate([{opacity:.35,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:360,easing:'cubic-bezier(.2,.8,.2,1)'});}
function revealChart(host){
 if(!motionEnabled)return;
 host.animate([{opacity:0,transform:'translateY(13px)'},{opacity:1,transform:'translateY(0)'}],{duration:650,easing:'cubic-bezier(.2,.8,.2,1)'});
 const svg=host.querySelector('.chart svg')||host.querySelector('svg');
 if(!svg)return;
 for(const [i,path]of [...svg.querySelectorAll('path[fill="none"]')].entries()){
  if(!path.getAttribute('d')||!path.getTotalLength)continue;
  const length=path.getTotalLength();
  path.animate([{strokeDasharray:`${length} ${length}`,strokeDashoffset:length},{strokeDasharray:`${length} ${length}`,strokeDashoffset:0}],{duration:1000,delay:i*60,easing:'ease-out'});
 }
 const bars=[...svg.querySelectorAll('rect')].filter(r=>Number(r.getAttribute('height'))>=20&&Number(r.getAttribute('height'))<=25&&r.getAttribute('fill')!=='transparent');
 bars.forEach((bar,i)=>{bar.style.transformBox='fill-box';bar.style.transformOrigin='left center';bar.animate([{transform:'scaleX(0)',opacity:.4},{transform:'scaleX(1)',opacity:1}],{duration:650,delay:Math.min(240,i*35),easing:'cubic-bezier(.2,.8,.2,1)'});});
}
const revealObserver=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){revealChart(entry.target);revealObserver.unobserve(entry.target);}},{threshold:.16});
$$('figure[data-main-graph]').forEach(host=>revealObserver.observe(host));

// Step through the original 15 half-hour snapshots, never synthetic in-between observations.
let stormIndex=0,stormTimer=null,eventIndex=0,eventTimer=null;
const stormTimes=DATA.stormFrames;
$('#storm-scrub').max=stormTimes.length-1;
$('#event-scrub').max=DATA.event.length-1;
$('#dose-scrub').max=DATA.dose.length-1;
let doseIndex=DATA.dose.findIndex(r=>r.mmh===1);
$('#dose-scrub').value=doseIndex;
function buttonState(id,running,label){const button=$(id);button.textContent=running?'Ⅱ Pause':`▶ ${label}`;button.setAttribute('aria-pressed',String(running));}
function stopStorm(){clearInterval(stormTimer);stormTimer=null;buttonState('#storm-play',false,stormIndex===stormTimes.length-1?'Replay storm':'Play storm');}
function stopEvent(){clearInterval(eventTimer);eventTimer=null;buttonState('#event-play',false,eventIndex===DATA.event.length-1?'Replay timeline':'Play timeline');}
function pausePlayers(){stopStorm();stopEvent();tooltip.hidden=true;}
function playerIsVisible(element){const r=element.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight&&r.width>0;}
function setStormFrame(index,animate=true){
 stormIndex=Math.max(0,Math.min(stormTimes.length-1,index));
 const frame=stormTimes[stormIndex];currentStormRows=frame.rows;
 const byCell=new Map(frame.rows.map(r=>[r.cell,r]));
 for(const id of ['map-rain','map-storm']){
  for(const rect of $$('#'+id+' rect[data-cell]')){const r=byCell.get(Number(rect.dataset.cell));rect.setAttribute('fill',r?(id==='map-rain'?sequential(r.mmh):change(r.pct)):C.none);}
  if(animate)morphHost($('#'+id));
 }
 $('#storm-time').textContent=frame.time.slice(11,16)+' SGT';
 $('#storm-scrub').value=stormIndex;if(!stormTimer)buttonState('#storm-play',false,stormIndex===stormTimes.length-1?'Replay storm':'Play storm');
 const observed=frame.rows.reduce((sum,r)=>sum+r.vacant,0),expected=frame.rows.reduce((sum,r)=>sum+r.baseline,0),wet=frame.rows.filter(r=>r.mmh>0).length;
 $('#storm-summary').innerHTML=`<strong>${observed.toLocaleString('en-SG')} vacant taxis</strong> across the 374 analysed squares, versus ${expected.toLocaleString('en-SG',{minimumFractionDigits:1,maximumFractionDigits:1})} expected. <strong>${wet} squares</strong> have rain in the preceding half-hour.`;
 $('#storm-scrub').setAttribute('aria-valuetext',frame.time.slice(11,16)+' Singapore time');
 tooltip.hidden=true;
}
$('#storm-play').addEventListener('click',()=>{
 if(stormTimer){stopStorm();return;}
 if(stormIndex>=stormTimes.length-1)setStormFrame(0,false);
 buttonState('#storm-play',true,'Play storm');
 stormTimer=setInterval(()=>{if(document.hidden||!playerIsVisible($('#storm-play').closest('figure'))){stopStorm();return;}setStormFrame(stormIndex+1);if(stormIndex===stormTimes.length-1)stopStorm();},950);
});
$('#storm-scrub').addEventListener('input',e=>{stopStorm();setStormFrame(Number(e.target.value),false);});
$('#storm-peak').addEventListener('click',()=>{stopStorm();setStormFrame(6);});
function setCurveCursor(id,row,xvalue,domainX,domainY){
 const svg=$('#'+id+' svg');if(!svg)return;
 const [a,b,width,height]=svg.getAttribute('viewBox').split(' ').map(Number);
 const x=scale(domainX,[48,width-22])(xvalue),y=scale(domainY,[height-60,id==='chart-event'?50:25])(row.pct),g=svg.querySelector('[data-curve-cursor]');
 if(!g)return;
 g.style.transform=`translateX(${x}px)`;g.querySelector('circle').setAttribute('cy',y);
}
function showEvent(index){
 eventIndex=Math.max(0,Math.min(DATA.event.length-1,index));const row=DATA.event[eventIndex];
 $('#event-scrub').value=eventIndex;if(!eventTimer)buttonState('#event-play',false,eventIndex===DATA.event.length-1?'Replay timeline':'Play timeline');
 $('#event-scrub').setAttribute('aria-valuetext',`${row.event_min} minutes, ${pct(row.pct,2)}`);
 $('#event-value').textContent=`${row.event_min>0?'+':''}${String(row.event_min).replace('-','−')} min · ${pct(row.pct)}`;
 $('#event-explanation').textContent=`${row.event_min<0?'Before local rain onset.':row.event_min<60?'First hour after local onset.':row.event_min<150?'Later after onset.':'Within statistical noise by the saved criterion.'} Saved estimate relative to −30 min. 95% CI ${pct(row.pct_lo,2)} to ${pct(row.pct_hi,2)}. This is an average event profile.`;
 setCurveCursor('chart-event',row,row.event_min,[-60,180],[-8,3]);
}
$('#event-scrub').addEventListener('input',e=>{stopEvent();showEvent(Number(e.target.value));});
$('#event-play').addEventListener('click',()=>{
 if(eventTimer){stopEvent();return;}
 if(eventIndex>=DATA.event.length-1)showEvent(0);
 buttonState('#event-play',true,'Play timeline');
 eventTimer=setInterval(()=>{if(document.hidden||!playerIsVisible($('#event-play').closest('figure'))){stopEvent();return;}showEvent(eventIndex+1);if(eventIndex===DATA.event.length-1)stopEvent();},1050);
});
function showDose(index){doseIndex=index;const row=DATA.dose[doseIndex];$('#dose-value').textContent=`${row.mmh} mm/h · ${pct(row.pct)} vacant taxis · 95% CI ${pct(row.lo,1)} to ${pct(row.hi,1)}`;$('#dose-scrub').setAttribute('aria-valuetext',`${row.mmh} mm/h, ${pct(row.pct)}`);setCurveCursor('chart-dose',row,row.mmh,[0,60],[-18,2]);}
$('#dose-scrub').addEventListener('input',e=>showDose(Number(e.target.value)));
function refreshExplorers(){showEvent(eventIndex);showDose(doseIndex);}
document.addEventListener('visibilitychange',()=>{if(document.hidden)pausePlayers();});

// Move the real figures into a stage: one scene, unique IDs, original controls and data.
const present=$('#present-toggle'),stage=$('#presentation-stage'),scene=$('#scene-content'),viewport=$('#scene-viewport');
const slides=$$('[data-scene]').map(node=>({node,title:(node.querySelector('h3')&&node.tagName==='FIGURE'?node.querySelector('h3'):node.querySelector('h1,h2')).textContent,chapter:node.dataset.chapter||'RESULTS'}));
for(const slide of slides){slide.home=document.createComment('presentation home');slide.node.before(slide.home);}
let presentIndex=0,presentEnabled=false,previousScroll=0,sceneAnimation=null;
function restoreSlide(){const slide=slides[presentIndex];if(slide.node.parentElement===scene)slide.home.after(slide.node);}
function fitScene(){
 if(!presentEnabled)return;
 scene.style.transform='none';scene.style.width='';scene.style.height='';
 if(slides[presentIndex].node.id==='simulation-demo'){scene.style.height='100%';viewport.style.overflowY='hidden';viewport.style.alignItems='stretch';return;}
 const mobile=innerWidth<700;
 if(mobile){scene.style.transform='';viewport.style.overflowY='auto';viewport.style.alignItems='flex-start';return;}
 const available=viewport.clientHeight-12,scaleBy=Math.min(1,available/scene.scrollHeight);
 // Keep chart text readable; very tall scenes can scroll rather than shrink below 80%.
 const factor=Math.max(.8,scaleBy);scene.style.transform=`scale(${factor})`;scene.style.transformOrigin='center top';
 viewport.style.overflowY=scaleBy<.8?'auto':'hidden';viewport.style.alignItems=scaleBy>=1?'center':'flex-start';
}
function showSlide(index,direction=1){
 pausePlayers();if(typeof stopLiveSimulation==='function')stopLiveSimulation();if(sceneAnimation)sceneAnimation.cancel();
 restoreSlide();presentIndex=Math.max(0,Math.min(slides.length-1,index));const slide=slides[presentIndex];
 document.body.classList.toggle('demo-active',slide.node.id==='simulation-demo');
 scene.replaceChildren(slide.node);stage.dataset.scene=slide.node.dataset.scene;
 $('#stage-chapter').textContent=slide.chapter;$('#stage-count').textContent=`${String(presentIndex+1).padStart(2,'0')} / ${slides.length}`;
 $('#slide-title').textContent=slide.title;$('#slide-progress').style.width=((presentIndex+1)/slides.length*100)+'%';
 $('#slide-prev').disabled=presentIndex===0;$('#slide-next').disabled=presentIndex===slides.length-1;
 viewport.scrollTop=0;renderCharts();refreshExplorers();fitScene();
 if(motionEnabled){sceneAnimation=scene.animate([{opacity:0,translate:`${direction*28}px 9px`},{opacity:1,translate:'0px 0px'}],{duration:520,easing:'cubic-bezier(.2,.8,.2,1)'});revealChart(slide.node);}
 stage.setAttribute('aria-label',`Presentation slide ${presentIndex+1} of ${slides.length}: ${slide.title}`);
}
function setPresent(enabled){
 if(enabled===presentEnabled)return;
 pausePlayers();presentEnabled=enabled;
 if(enabled){previousScroll=scrollY;stage.hidden=false;document.body.classList.add('present-mode');$('#story').inert=true;showSlide(0);}
 else{stopLiveSimulation();if(sceneAnimation)sceneAnimation.cancel();restoreSlide();scene.replaceChildren();stage.hidden=true;document.body.classList.remove('present-mode','demo-active');$('#story').inert=false;scene.style.transform='';renderCharts();refreshExplorers();window.scrollTo({top:previousScroll,behavior:'instant'});present.focus();}
 present.setAttribute('aria-pressed',String(enabled));present.textContent=enabled?'Exit presentation':'↗ Present';
}
present.addEventListener('click',()=>setPresent(!presentEnabled));
$('.hero-link').addEventListener('click',e=>{if(presentEnabled){e.preventDefault();setPresent(false);$('#brief').scrollIntoView({behavior:motionEnabled?'smooth':'instant'});}});
$$('[data-start-presentation]').forEach(button=>button.addEventListener('click',()=>{if(presentEnabled)showSlide(1);else setPresent(true);}));
$('#slide-prev').addEventListener('click',()=>showSlide(presentIndex-1,-1));$('#slide-next').addEventListener('click',()=>showSlide(presentIndex+1,1));
$('#slide-replay').addEventListener('click',()=>revealChart(slides[presentIndex].node));
document.addEventListener('keydown',e=>{
 if(dialog.open){if(e.key==='ArrowRight'&&state.part<state.modal.parts.length-1){state.part++;showPart();}if(e.key==='ArrowLeft'&&state.part>0){state.part--;showPart();}return;}
 if(e.key==='Escape'&&document.body.classList.contains('demo-expanded')){setDemoExpanded(false);return;}
 if(e.key==='Escape'&&presentEnabled){setPresent(false);return;}
 if(!presentEnabled||e.altKey||e.metaKey||e.ctrlKey||['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)||e.target.closest('.segmented'))return;
 if(['ArrowRight','PageDown'].includes(e.key)){e.preventDefault();showSlide(presentIndex+1,1);}
 if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();showSlide(presentIndex-1,-1);}
 if(e.key==='Home'){e.preventDefault();showSlide(0,-1);}
 if(e.key==='End'){e.preventDefault();showSlide(slides.length-1,1);}
});
updateMotion();setStormFrame(0,false);refreshExplorers();

addEventListener('beforeprint',()=>{if(presentEnabled)setPresent(false);pausePlayers();});

function setDemoExpanded(enabled){document.body.classList.toggle('demo-expanded',enabled);const button=$('#expand-simulation');button.textContent=enabled?'↙ Back to presentation':'Expand view ↗';button.setAttribute('aria-pressed',String(enabled));if(presentEnabled)fitScene();}
$('#expand-simulation').addEventListener('click',()=>setDemoExpanded(!document.body.classList.contains('demo-expanded')));
function stopLiveSimulation(){setDemoExpanded(false);$('#expand-simulation').disabled=true;const frame=$('#simulation-frame');if(!frame)return;frame.removeAttribute('src');frame.hidden=true;$('#simulation-placeholder').hidden=false;$('#load-simulation').textContent='Load Storm Builder';}
$('#load-simulation').addEventListener('click',()=>{const frame=$('#simulation-frame');if(frame.getAttribute('src')){stopLiveSimulation();return;}$('#expand-simulation').disabled=false;frame.src='https://storm-builder-sg.vercel.app/';frame.hidden=false;$('#simulation-placeholder').hidden=true;$('#load-simulation').textContent='Stop demo';});
$('#conclusion a[href="#evidence"]').addEventListener('click',e=>{if(presentEnabled){e.preventDefault();setPresent(false);$('#evidence').scrollIntoView({behavior:motionEnabled?'smooth':'instant'});}});
