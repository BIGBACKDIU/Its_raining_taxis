// Synthetic presentation input. No observed storm, held-out outcome or fitted parameter is changed.
function rainValue(config,x,y,minute){
  if(minute<0||minute>=config.duration)return 0;
  const q=minute/config.duration, temporal=Math.pow(Math.sin(Math.PI*q),.75);
  const velocity=config.driftSpeed*1000/60;
  const directions={still:[0,0],east:[1,0],west:[-1,0],south:[0,-1],north:[0,1]};
  const d=directions[config.direction],cx=config.x+d[0]*velocity*minute,cy=config.y+d[1]*velocity*minute;
  const radius={small:1500,medium:4000,large:10000,island:36000}[config.size];
  const dx=(x-cx)/(config.size==='island'?70000:radius),dy=(y-cy)/(config.size==='island'?30000:radius);
  const r=Math.hypot(dx,dy);return r>=1?0:config.strength*temporal*Math.exp(-2*r*r);
}
function makeStorm(data,config){
  const base=[],rain=[],C=data.cells.cell.length;
  for(let slot=0;slot<10;slot++){
    const half=(config.hour*2+slot)%48;
    base.push([...data.profiles[config.weekend?1:0][half]]);
    rain.push(Array.from({length:C},(_,i)=>{
      let sum=0;for(let k=0;k<6;k++)sum+=rainValue(config,data.cells.x[i],data.cells.y[i],slot*30+k*5+2.5);
      return sum/6;
    }));
  }
  return {minutes:241,base,rain,v0:base[0].map(v=>Math.round(v)),snap_minutes:Array.from({length:241},(_,i)=>i),share:data.share};
}
function modelSettings(data,config){
  const scen={mechanism:config.mechanism,dest:config.dest,travel:'rain',dispatch:config.dispatch,demand_level:config.demand};
  const row=data.tuned.find(r=>r.mechanism===scen.mechanism&&r.dest===scen.dest&&r.travel===scen.travel&&r.dispatch===scen.dispatch);
  if(!row)throw Error('Missing frozen parameter combination');
  return {scen,params:{occ0:row.occ0,kappa:row.kappa,beta_dem:row.beta_dem,beta_off:row.beta_off}};
}
if(typeof module!=="undefined")module.exports={rainValue,makeStorm,modelSettings};
