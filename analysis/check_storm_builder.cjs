// Headless Chromium checks for the single-file presentation. No historical outcome scoring.
const fs=require('fs'),path=require('path'),os=require('os'),assert=require('assert');
let playwright;try{playwright=require('playwright');}catch(error){playwright=require(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));}
const root=path.resolve(__dirname,'..'),url='file://'+path.join(root,'sim/v3/index.html');
const screenshots=path.join(root,'outputs/figures'),errors=[],external=[];
const executable=process.env.CHROMIUM_PATH||['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',playwright.chromium.executablePath()].find(p=>fs.existsSync(p));
const report={platform:os.platform(),architecture:os.arch(),cpu:os.cpus()[0].model,screenshots:[],checks:[]};
function observe(page){page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  page.on('request',r=>{if(!/^(file:|blob:|data:)/.test(r.url()))external.push(r.url());});}
async function ready(page){await page.waitForFunction(()=>window.StormBuilder?.ready,null,{timeout:120000});await page.waitForTimeout(150);}
async function screenshot(page,name){await page.screenshot({path:path.join(screenshots,name),fullPage:true});report.screenshots.push(name);}
async function counters(page,label){
  const check=await page.evaluate(()=>{
    const config=StormBuilder.config,{scen,params}=modelSettings(DATA,config),storm=makeStorm(DATA,config);
    const sim=new Sim(new World(DATA.cells,DATA.T,DATA.weights,DATA.off_scale),storm,scen,params,config.seed,{policy:config.policy});
    const time=StormBuilder.time;
    if(time>=0)for(let m=0;m<=Math.min(240,Math.floor(time));m++)sim.step();
    const expected={vacant:sim.vacantTotal(),hired:sim.stats.served,offline:sim.OFF.reduce((a,b)=>a+b,0),
      waiting:sim.Qw.reduce((a,b)=>a+b,0),abandoned:sim.stats.abandoned};
    const displayed=Object.fromEntries(Object.keys(expected).map(k=>[k,Number(document.getElementById(k).textContent.replace(/,/g,''))]));
    return {time,expected,displayed,requests:sim.stats.requests,served:sim.stats.served,
      drawnVacant:StormBuilder.performance().drawnVacant,cellErrors:StormBuilder.result.outputs.map(o=>o.maxCellError),
      fallbacks:StormBuilder.result.pathFallbacks};
  });
  assert.deepStrictEqual(check.displayed,check.expected,label+' displayed counters');
  assert.equal(check.drawnVacant,check.expected.vacant,label+' vacant dot count');
  assert(check.served<=check.requests);assert(check.cellErrors.every(n=>n===0));assert.equal(check.fallbacks,0);
  report.checks.push({label,...check});
}
(async()=>{
  const browser=await playwright.chromium.launch({headless:true,executablePath:executable});report.browser=browser.version();
  const page=await browser.newPage({viewport:{width:1440,height:1050},deviceScaleFactor:1});observe(page);
  const start=Date.now();await page.goto(url);await ready(page);report.desktopBuildSeconds=(Date.now()-start)/1000;
  report.cruising=await page.evaluate(()=>{
    let maxRadius=0;const seen=new Set;
    for(const output of StormBuilder.result.outputs)for(const actor of output.actors)for(const leg of actor.legs){
      if(leg.kind!==0||seen.has(leg.route))continue;seen.add(leg.route);
      const p=StormBuilder.result.paths[leg.route],node=DATA.road.cellNodes[leg.cell],x=DATA.road.nodes[node*2],y=DATA.road.nodes[node*2+1];
      for(let k=0;k<p.xy.length;k+=2)maxRadius=Math.max(maxRadius,Math.hypot(p.xy[k]-x,p.xy[k+1]-y));
    }
    return {uniquePaths:seen.size,maxRadiusMetres:maxRadius,stationaryCells:StormBuilder.result.stationaryCruiseCells};
  });assert(report.cruising.maxRadiusMetres<=1250.01);
  await page.evaluate(()=>scrollTo(0,500));report.permanentBannerVisible=await page.locator('.notice').evaluate(e=>e.getBoundingClientRect().top>=0&&e.getBoundingClientRect().bottom<=innerHeight);
  assert(report.permanentBannerVisible);await page.evaluate(()=>scrollTo(0,0));
  report.defaultBrief=await page.locator('.scenario-brief').innerText();
  assert(report.defaultBrief.includes('Heavy rain · 8 km across · 60 min'));
  assert(report.defaultBrief.includes('Rain raises simulated requests and moves some drivers off duty'));
  assert(report.defaultBrief.includes('25% longer'));
  await screenshot(page,'storm_builder_1440_before.png');await counters(page,'desktop initial');
  await page.evaluate(()=>StormBuilder.seek(30));await page.waitForTimeout(150);await screenshot(page,'storm_builder_1440_mid.png');await counters(page,'desktop mid storm');
  await page.evaluate(()=>{StormBuilder.seek(0);StormBuilder.setSpeed(16);StormBuilder.resetPerformance();});
  await page.locator('#play').click();await page.waitForFunction(()=>StormBuilder.time>=240,null,{timeout:60000});
  await page.waitForTimeout(100);report.desktopPlayback=await page.evaluate(()=>StormBuilder.performance());await counters(page,'desktop 16x end');
  await page.evaluate(()=>StormBuilder.stressTest(2500));await page.waitForTimeout(6000);
  report.desktopStress2500=await page.evaluate(()=>StormBuilder.performance());assert.equal(report.desktopStress2500.drawnDots,2500);
  await page.evaluate(()=>StormBuilder.stopStress());
  const phone=await browser.newPage({viewport:{width:400,height:900},deviceScaleFactor:1,isMobile:true,hasTouch:true});observe(phone);
  await phone.goto(url);await ready(phone);await screenshot(phone,'storm_builder_400_before.png');await counters(phone,'phone initial');
  await phone.evaluate(()=>StormBuilder.seek(30));await phone.waitForTimeout(150);await screenshot(phone,'storm_builder_400_mid.png');await counters(phone,'phone mid storm');
  await phone.evaluate(()=>StormBuilder.stressTest(2500));await phone.waitForTimeout(3000);
  report.emulatedPhoneStress2500=await phone.evaluate(()=>StormBuilder.performance());assert.equal(report.emulatedPhoneStress2500.drawnDots,2500);
  await phone.evaluate(()=>{StormBuilder.stopStress();StormBuilder.seek(30);});await phone.waitForTimeout(100);
  report.phoneHorizontalOverflow=await phone.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert(!report.phoneHorizontalOverflow);
  await phone.locator('#open-sheet').click();assert(await phone.locator('#controls').evaluate(x=>x.classList.contains('open')));
  await screenshot(phone,'storm_builder_400_controls.png');await phone.locator('#close-sheet').click();
  await phone.locator('#split').check();await phone.waitForTimeout(150);await screenshot(phone,'storm_builder_400_split.png');
  report.phoneSplitColumns=await phone.locator('#maps').evaluate(e=>getComputedStyle(e).gridTemplateColumns);assert(!report.phoneSplitColumns.includes(' '));
  await phone.locator('#split').uncheck();await phone.locator('#open-sheet').click();await phone.locator('#policy').click();await phone.locator('#close-sheet').click();
  await phone.waitForTimeout(100);await counters(phone,'phone repositioning counters');
  report.policyBrief=await phone.locator('#storm-effect').textContent();assert(report.policyBrief.includes('Repositioning sends surplus taxis'));
  await phone.locator('#open-sheet').click();await phone.locator('[data-preset=west]').click();
  await phone.waitForFunction(()=>StormBuilder.ready&&StormBuilder.result.config.size==='small',null,{timeout:120000});
  report.smallShower=await phone.evaluate(()=>({duration:StormBuilder.result.config.duration,firstSlotRain:StormBuilder.result.storm.rain[0].reduce((a,b)=>a+b,0),laterRain:StormBuilder.result.storm.rain.slice(1).flat().reduce((a,b)=>a+b,0)}));
  report.smallShowerBrief=await phone.locator('.scenario-brief').innerText();
  assert(report.smallShowerBrief.includes('Light rain · 3 km across · 30 min · stationary'));
  assert(!report.smallShowerBrief.includes('Repositioning sends surplus taxis'));
  assert.notEqual(report.smallShowerBrief,report.defaultBrief);
  assert(report.smallShower.firstSlotRain>0&&report.smallShower.laterRain===0);await phone.locator('#close-sheet').click();
  const reduced=await browser.newPage({viewport:{width:400,height:900},reducedMotion:'reduce'});observe(reduced);await reduced.goto(url);await ready(reduced);
  report.reducedMotion=await reduced.evaluate(()=>StormBuilder.reducedMotion);assert(report.reducedMotion);await reduced.evaluate(()=>StormBuilder.seek(30));await reduced.waitForTimeout(100);await counters(reduced,'reduced motion');
  const fallback=await browser.newPage({viewport:{width:1440,height:1000}});observe(fallback);
  await fallback.addInitScript(()=>{window.Worker=class{constructor(){throw new DOMException('Worker blocked by artifact sandbox','SecurityError');}};});
  await fallback.goto(url);await ready(fallback);report.workerBlockedFallback=true;await counters(fallback,'worker-blocked artifact fallback');
  report.consoleErrors=errors;report.externalRequests=external;assert.deepStrictEqual(errors,[]);assert.deepStrictEqual(external,[]);
  await browser.close();fs.writeFileSync(path.join(root,'outputs/tables/storm_builder_browser_check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(error=>{console.error(error);process.exit(1);});
