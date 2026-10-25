// Precompute the unmodified model and observational actor trajectories off the UI thread.
function prepareSimulation(data,config,progress=()=>{}) {
  const world=new World(data.cells,data.T,data.weights,data.off_scale),storm=makeStorm(data,config);
  const {scen,params}=modelSettings(data,config),router=new RoadRouter(data.road);
  const outputs=[];
  for(const policy of [false,true]){
    const visualRng=new RNG((config.seed^0x5a17e19)>>>0),random=()=>visualRng.random(); // Separate RNG.
    const actors=[],pulses=[],frames=[],vac=Array.from({length:world.C},()=>[]),off=Array.from({length:world.C},()=>[]);
    const scheduled=new Map(),cruises=new Map();
    function cruise(cell){
      if(!cruises.has(cell))cruises.set(cell,Array.from({length:3},()=>router.cruise(cell,random)));
      const pool=cruises.get(cell);return pool[Math.floor(random()*pool.length)];
    }
    function vacant(id,cell,m,initial=false){
      const route=cruise(cell),length=router.paths[route].length;
      actors[id].legs.push({kind:0,from:m,to:Infinity,route,cell,phase:initial?random()*length:0});
      vac[cell].push(id);
    }
    function create(cell,m,initial=false){const id=actors.length;actors.push({id,born:m,legs:[]});vacant(id,cell,m,initial);return id;}
    function take(cell,m){
      const id=vac[cell].pop();if(id===undefined)throw Error(`No animated taxi in cell ${cell} at ${m}`);
      const leg=actors[id].legs.at(-1);leg.to=m;
      const length=router.paths[leg.route].length;
      const distance=length>0?(leg.phase+(m-leg.from)*180)%length:0;
      return {id,leg,distance};
    }
    function schedule(id,cell,m){const key=`${m}:${cell}`;if(!scheduled.has(key))scheduled.set(key,[]);scheduled.get(key).push(id);}
    const hooks={
      onRequest(cell,m){pulses.push({cell,m,kind:0});},
      onAbandon(cell,m){pulses.push({cell,m,kind:1});},
      onHire(pickup,dest,start,arrive,meta){
        const {id,leg,distance}=take(meta.taxiCell,start),at=meta.pickupMin;
        const approach=router.approach(leg.route,distance,meta.taxiCell,pickup);
        actors[id].legs.push({kind:3,from:start,to:at,route:approach,cell:pickup});
        actors[id].legs.push({kind:1,from:at,to:Infinity,arrive,route:router.route(data.road.cellNodes[pickup],data.road.cellNodes[dest]),cell:dest});
        schedule(id,dest,arrive);
      },
      onOffline(cell,m){
        const {id,leg,distance}=take(cell,m);const point=router.sample(leg.route,distance);
        actors[id].legs.push({kind:4,from:m,to:Infinity,point:[point[0],point[1]],cell});off[cell].push(id);
      },
      onReturn(cell,m,meta){
        let id;
        if(meta.kind==='duty')id=off[cell].pop();
        else id=scheduled.get(`${m}:${cell}`)?.pop();
        if(id===undefined)create(cell,m);
        else{actors[id].legs.at(-1).to=m;vacant(id,cell,m);}
      },
      onReposition(from,to,start,arrive){
        const {id,leg,distance}=take(from,start);
        actors[id].legs.push({kind:2,from:start,to:Infinity,arrive,
          route:router.approach(leg.route,distance,from,to),cell:to});schedule(id,to,arrive);
      },
      onStockAdjust(cell,delta,m){
        if(delta>0)create(cell,m);
        else{const {id,leg,distance}=take(cell,m),p=router.sample(leg.route,distance);
          actors[id].legs.push({kind:5,from:m,to:Infinity,point:[p[0],p[1]],cell});}
      }
    };
    storm.v0.forEach((n,cell)=>{for(let k=0;k<n;k++)create(cell,-1,true);});
    const sim=new Sim(world,storm,scen,params,config.seed,{policy,hooks});
    let maxCellError=0;
    for(let m=0;m<=240;m++){
      sim.step();
      for(let i=0;i<world.C;i++){
        const error=Math.abs(vac[i].length-sim.V[i]);maxCellError=Math.max(maxCellError,error);
        if(error||off[i].length!==sim.OFF[i])throw Error(`Visual/model count mismatch ${m}:${i}`);
      }
      frames.push({minute:m,vacant:sim.vacantTotal(),hired:sim.stats.served,
        offline:sim.OFF.reduce((a,b)=>a+b,0),waiting:sim.Qw.reduce((a,b)=>a+b,0),
        abandoned:sim.stats.abandoned,requests:sim.stats.requests,V:Int32Array.from(sim.V),
        expected:storm.base[Math.floor(m/30)].reduce((a,b)=>a+b,0)});
      if(m%30===0)progress({policy,minute:m});
    }
    outputs.push({policy,actors,pulses,frames,maxCellError,stats:{...sim.stats},
      initial:{minute:-1,vacant:storm.v0.reduce((a,b)=>a+b,0),hired:0,offline:0,waiting:0,abandoned:0,requests:0,
        V:Int32Array.from(storm.v0),expected:storm.base[0].reduce((a,b)=>a+b,0)}});
  }
  return {outputs,paths:router.paths,roadQueries:router.queries,pathFallbacks:router.fallbacks,
    cachedPaths:router.cache.size,stationaryCruiseCells:router.stationaryCruiseCells.size,storm,config,params};
}
if(typeof module!=="undefined")module.exports={prepareSimulation};
