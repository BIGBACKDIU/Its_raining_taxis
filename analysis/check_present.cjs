// Headless Chrome checks for outputs/story/present.html (decision 174). Presentation only; no scoring.
// Run: node analysis/check_present.cjs   (screenshots + check.json in outputs/story/present_previews/)
const fs=require('fs'),path=require('path'),os=require('os'),assert=require('assert');
let playwright;try{playwright=require('playwright');}catch(error){playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const root=path.resolve(__dirname,'..'),url='file://'+path.join(root,'outputs/story/present.html');
const out=path.join(root,'outputs/story/present_previews');fs.mkdirSync(out,{recursive:true});
const executable=process.env.CHROMIUM_PATH||['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',playwright.chromium.executablePath()].find(p=>fs.existsSync(p));
const report={browser:null,viewports:{},embeds:{},storm:{},reducedMotion:{},errors:[]};
const WAIT={'s-title':3200,'s-close':2600,'s-market':3800,'s-method':5000,'s-playbook':6200,'s-storm':2200,'s-places':2600,'s-planning':3400,'s-next':3800,'s-builder':9000,'s-dashboard':9000};

// Layout audit of the active slide, in 1920x1080 stage pixels.
function audit(){
  const stage=document.querySelector('#stage'),slide=document.querySelector('.slide.active'),S=stage.getBoundingClientRect(),k=S.width/1920;
  const box=e=>{const r=e.getBoundingClientRect();return{x0:(r.left-S.left)/k,y0:(r.top-S.top)/k,x1:(r.right-S.left)/k,y1:(r.bottom-S.top)/k};};
  const visible=e=>{const st=getComputedStyle(e);return st.display!=='none'&&st.visibility!=='hidden'&&!e.closest('[hidden]')&&e.getClientRects().length;};
  const outside=[],overflow=[],overlaps=[];
  for(const e of slide.querySelectorAll('*')){
    if(!visible(e)||e.closest('svg')&&e.tagName!=='svg'||e.tagName==='CANVAS'||e.tagName==='ASIDE'||e.closest('aside'))continue;
    const b=box(e);if(b.x1-b.x0<1||b.y1-b.y0<1)continue;
    if(b.x0<-1||b.y0<-1||b.x1>1921||b.y1>1081)outside.push({el:e.tagName+'.'+e.className+'#'+e.id,b});
    if(e.scrollHeight>e.clientHeight+2&&getComputedStyle(e).overflow!=='visible'||e.scrollWidth>e.clientWidth+2&&['hidden','auto','scroll'].includes(getComputedStyle(e).overflowX))overflow.push(e.tagName+'.'+e.className+'#'+e.id);
  }
  const blocks=[...slide.querySelectorAll('.head h1,.kicker,.foot,.point,.card,.step,.tstep,.chart,.map,#storm-line,.avg,.tally,.clock,.frame,.strip,.qr,.question,.dataline,.callout-wide,.legend,.takeaway,.questions,.found,.conf,.stat,.defs p,.refs p,.title-copy>*,.radar-key,.anim-label,.label,.caption,.appendix-link,.tag,.benefits,.note-box')].filter(visible);
  for(let i=0;i<blocks.length;i++)for(let j=i+1;j<blocks.length;j++){
    const a=blocks[i],b=blocks[j];if(a.contains(b)||b.contains(a))continue;
    const A=box(a),B=box(b),w=Math.min(A.x1,B.x1)-Math.max(A.x0,B.x0),h=Math.min(A.y1,B.y1)-Math.max(A.y0,B.y0);
    if(w>2&&h>2)overlaps.push([a.className||a.tagName,b.className||b.tagName,Math.round(w),Math.round(h)]);
  }
  const number=document.querySelector('#number');
  for(const b of blocks){if(b.classList.contains('foot'))continue;const A=box(number),B=box(b),w=Math.min(A.x1,B.x1)-Math.max(A.x0,B.x0),h=Math.min(A.y1,B.y1)-Math.max(A.y0,B.y0);if(w>2&&h>2)overlaps.push(['#number',b.className||b.tagName,Math.round(w),Math.round(h)]);}
  const text=slide.innerText.replace(/\s+/g,' ').trim().length,svgs=slide.querySelectorAll('svg *').length;
  return{outside,overflow,overlaps,text,svgs};
}

(async()=>{
  const browser=await playwright.chromium.launch({headless:true,executablePath:executable});report.browser=browser.version();
  for(const [w,h] of [[1920,1080],[1440,900]]){
    for(const f of fs.readdirSync(out))if(f.startsWith(`${w}x${h}-`))fs.unlinkSync(path.join(out,f));
    const page=await browser.newPage({viewport:{width:w,height:h},deviceScaleFactor:1});
    page.on('pageerror',e=>report.errors.push(`${w}: ${e.message}`));
    page.on('console',m=>{if(m.type()==='error'&&!/storm-builder|netlify|favicon|ERR_|Refused to frame/i.test(m.text()))report.errors.push(`${w}: ${m.text()}`);});
    await page.goto(url+'#1');await page.evaluate(()=>document.fonts.ready);
    const fonts=await page.evaluate(()=>['Poppins','Anton'].map(f=>document.fonts.check(`32px ${f}`)));
    assert.deepStrictEqual(fonts,[true,true],'embedded fonts');
    if(w===1920){
      await page.waitForTimeout(3200);
      report.titleFrameMs=await page.evaluate(()=>new Promise(done=>{const times=[];let last=performance.now();const step=now=>{times.push(now-last);last=now;if(times.length<120)requestAnimationFrame(step);else done(times.slice(5).reduce((a,b)=>a+b,0)/(times.length-5));};requestAnimationFrame(step);}));
      for(const t of [2,9,16]){await page.evaluate(t=>TITLE_FRAME(t),t);await page.screenshot({path:path.join(out,`title-frame-${t}s-1920x1080.jpg`),type:'jpeg',quality:84});}
    }
    const ids=await page.evaluate(()=>[...document.querySelectorAll('.slide')].map(s=>s.id));
    const rows=[];
    for(const [i,id] of ids.entries()){
      await page.evaluate(i=>PRESENT.show(i),i);
      const t0=Date.now();
      await page.waitForTimeout(WAIT[id]||2400);
      if(id==='s-storm'&&w===1920){
        const a=await page.evaluate(()=>PRESENT.stormFrame());await page.waitForTimeout(3200);const b=await page.evaluate(()=>PRESENT.stormFrame());
        const fills=await page.evaluate(()=>[new Set([...document.querySelectorAll('#map-rain rect')].map(r=>r.getAttribute('fill'))).size,new Set([...document.querySelectorAll('#map-change rect')].map(r=>r.getAttribute('fill'))).size]);
        report.storm={frameBefore:a,frameAfter:b,plays:a!==b,distinctFills:fills};assert(a!==b,'storm replay advances');assert(fills[0]>2&&fills[1]>20,'storm maps drawn');
      }
      if(['s-builder','s-dashboard'].includes(id)){
        const state=await page.evaluate(id=>{const f=document.querySelector(`#${id} iframe`),fb=document.querySelector(`#${id} .fallback`);return{iframe:!!f,src:f?.src||null,fallbackShown:!fb.hidden};},id);
        report.embeds[`${id}@${w}`]={...state,secondsWaited:(Date.now()-t0)/1000};
      }
      const a=await page.evaluate(audit);
      if(id==='s-title')a.canvasColours=await page.evaluate(()=>{const c=document.querySelector('#title-canvas').getContext('2d').getImageData(0,0,1920,1080).data,s=new Set;for(let k=0;k<c.length;k+=4*997)s.add(c[k]>>4<<8|c[k+1]>>4<<4|c[k+2]>>4);return s.size;});
      const file=`${w}x${h}-${String(i+1).padStart(2,'0')}-${id.replace(/^s-/,'')}.jpg`;
      await page.screenshot({path:path.join(out,file),type:'jpeg',quality:82});
      rows.push({slide:i+1,id,file,...a});
      if(id==='s-builder'){
        await page.evaluate(i=>PRESENT.show(i+1),i);await page.waitForTimeout(300);
        report.embeds[`s-builder-unload@${w}`]={iframeAfterLeaving:await page.evaluate(()=>!!document.querySelector('#s-builder iframe'))};
        await page.evaluate(i=>PRESENT.show(i),i);
      }
    }
    report.viewports[`${w}x${h}`]=rows;
    await page.close();
  }
  // reduced motion: everything visible immediately, replay shows the 09:30 peak
  const ctx=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});const page=await ctx.newPage();
  await page.goto(url+'#4');await page.waitForTimeout(800);
  report.reducedMotion={stormFrame:await page.evaluate(()=>PRESENT.stormFrame()),hiddenEntries:await page.evaluate(()=>[...document.querySelectorAll('.slide.active [data-in]')].filter(e=>getComputedStyle(e).opacity<.99).length)};
  await ctx.close();await browser.close();
  const problems=[];
  for(const [vp,rows] of Object.entries(report.viewports))for(const r of rows){
    if(r.outside.length||r.overflow.length||r.overlaps.length)problems.push({vp,slide:r.slide,id:r.id,outside:r.outside,overflow:r.overflow,overlaps:r.overlaps});
    if(r.text<20&&r.svgs<20&&!(r.canvasColours>8))problems.push({vp,slide:r.slide,blank:true});
  }
  report.problems=problems;
  fs.writeFileSync(path.join(out,'check.json'),JSON.stringify(report,null,1)+'\n');
  console.log(JSON.stringify({errors:report.errors,problems,storm:report.storm,embeds:report.embeds,reducedMotion:report.reducedMotion,titleFrameMs:report.titleFrameMs},null,1));
  if(report.errors.length||problems.length)process.exitCode=1;
})();
