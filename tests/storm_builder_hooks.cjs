const fs=require('fs'),vm=require('vm'),assert=require('assert');
const current=require('../sim/v2/engine_v2.js');
const legacyPath=process.argv[2];let legacy=null;
if(legacyPath){const sandbox={module:{exports:{}}};vm.runInNewContext(fs.readFileSync(legacyPath,'utf8'),sandbox);legacy=sandbox.module.exports;}
const cells={cell:[0,1,2,3,4],stands:[1,1,1,1,1]};
const T=Array.from({length:25},(_,k)=>k%5===Math.floor(k/5)?0:2+Math.abs(k%5-Math.floor(k/5)));
function world(Engine){return new Engine.World(cells,T,{observed:[1,4,3,2,8]},[1,1,1,1,1]);}
const storm={minutes:121,v0:[70,10,20,30,15],share:.6,snap_minutes:[0,30,60,90,120],
  base:Array.from({length:6},(_,k)=>[8+k,12,35,35,55-k]),
  rain:Array.from({length:6},(_,k)=>k>0&&k<4?[0,8,25,2,0]:[0,0,0,0,0])};
const params={occ0:.35,kappa:1.1,beta_dem:.7,beta_off:.05};let cases=0,events=0;
function snapshot(s,arrivals=false){const a={m:s.m,V:[...s.V],OFF:[...s.OFF],Qw:[...s.Qw],stats:s.stats};if(arrivals)a.ARR=s.ARR.map(x=>[...x]);return JSON.stringify(a);}
for(const mechanism of ['demand','supply','mix'])for(const policy of [false,true])for(const seed of [7,2702]){
  const scen={mechanism,dest:'observed',travel:'rain',dispatch:'widening',demand_level:1};
  const counts={};const hooks={};
  for(const name of ['onRequest','onHire','onOffline','onReturn','onReposition','onAbandon','onStockAdjust'])hooks[name]=(...args)=>{counts[name]=(counts[name]||0)+1;events++;assert(args.every(x=>typeof x!=='function'));};
  const off=new current.Sim(world(current),storm,scen,params,seed,{policy});
  const on=new current.Sim(world(current),storm,scen,params,seed,{policy,hooks});
  const old=legacy?new legacy.Sim(world(legacy),storm,scen,params,seed,{policy}):null;
  for(let m=0;m<storm.minutes;m++){off.step();on.step();if(old)old.step();assert.strictEqual(snapshot(on),snapshot(off));if(old)assert.strictEqual(snapshot(on),snapshot(old));}
  assert.strictEqual(snapshot(on,true),snapshot(off,true));if(old)assert.strictEqual(snapshot(on,true),snapshot(old,true));
  assert.strictEqual(counts.onRequest,on.stats.requests);assert.strictEqual(counts.onHire,on.stats.served);
  assert.strictEqual(counts.onAbandon||0,on.stats.abandoned);assert(on.stats.served<=on.stats.requests);cases++;
}
console.log(JSON.stringify({cases,events,hookStatesIdentical:true,legacyIdentical:!!legacy}));
