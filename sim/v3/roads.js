// Directed A* on metre-quantised OSM roads. Only visual geometry; engine travel times are untouched.
class MinHeap {
  constructor() { this.a = []; }
  push(node, score) {
    const a = this.a; let i = a.length; a.push([node, score]);
    while (i) { const p = (i-1)>>1; if (a[p][1] <= score) break; a[i] = a[p]; i = p; }
    a[i] = [node, score];
  }
  pop() {
    const a = this.a, first = a[0], end = a.pop();
    if (a.length) { let i = 0; while (i*2+1 < a.length) {
      let j = i*2+1; if (j+1 < a.length && a[j+1][1] < a[j][1]) j++;
      if (end[1] <= a[j][1]) break; a[i] = a[j]; i = j;
    } a[i] = end; } return first;
  }
}

class RoadRouter {
  constructor(road) {
    this.road = road; this.N = road.nodes.length/2;
    this.adj = Array.from({length:this.N},()=>[]);
    this.reverse = Array.from({length:this.N},()=>[]);
    road.edges.forEach((e, id)=>{this.adj[e[0]].push(id);this.reverse[e[1]].push(id);});
    this.cache = new Map(); this.paths = []; this.fallbacks = 0; this.queries = 0;
    this.localCache = new Map(); this.stationaryCruiseCells = new Set();
    this.dist = new Float64Array(this.N); this.prev = new Int32Array(this.N);
    this.seen = new Uint32Array(this.N); this.mark = 0;
  }
  point(node) { return [this.road.nodes[node*2],this.road.nodes[node*2+1]]; }
  geometry(id) {
    const e = this.road.edges[id]; return [...this.point(e[0]),...e.slice(4),...this.point(e[1])];
  }
  addPath(xy, endNode = null) {
    if (xy.length < 4) xy = [...xy,...xy];
    const cumulative = [0];
    for (let i = 2; i < xy.length; i+=2) cumulative.push(cumulative.at(-1)+Math.hypot(xy[i]-xy[i-2],xy[i+1]-xy[i-1]));
    const id = this.paths.length;
    this.paths.push({xy:Float32Array.from(xy), cumulative:Float32Array.from(cumulative), length:cumulative.at(-1), endNode});
    return id;
  }
  route(from, to, scope = null) {
    this.queries++;
    const key = `${scope?'local'+scope.home+':':''}${from}:${to}`;
    if (this.cache.has(key)) return this.cache.get(key);
    if (from === to) { const id = this.addPath([...this.point(from),...this.point(from)],to);this.cache.set(key,id);return id; }
    const mark = ++this.mark, heap = new MinHeap(), target = this.point(to);
    this.dist[from] = 0; this.seen[from] = mark; this.prev[from] = -1;
    const h = (n)=>Math.hypot(this.road.nodes[2*n]-target[0],this.road.nodes[2*n+1]-target[1]);
    heap.push(from,h(from)); let reached = false;
    while (heap.a.length) {
      const [u,score] = heap.pop();
      if (score > this.dist[u]+h(u)+.01) continue;
      if (u === to) { reached=true;break; }
      for (const id of this.adj[u]) {
        if(scope&&!scope.edges.has(id))continue;
        const e = this.road.edges[id], v=e[1], cost=this.dist[u]+e[3];
        if (this.seen[v] !== mark || cost < this.dist[v]) {
          this.seen[v]=mark;this.dist[v]=cost;this.prev[v]=id;heap.push(v,cost+h(v));
        }
      }
    }
    let xy=[];
    if (!reached) { this.fallbacks++;xy=[...this.point(from),...target]; }
    else {
      const ids=[];let u=to;
      while (u!==from) { const id=this.prev[u];ids.push(id);u=this.road.edges[id][0]; }
      ids.reverse();for(const id of ids) { const p=this.geometry(id);xy.push(...(xy.length?p.slice(2):p)); }
    }
    const id=this.addPath(xy,to);this.cache.set(key,id);return id;
  }
  join(ids) {
    const xy=[];for(const id of ids) { const p=this.paths[id];xy.push(...(xy.length?Array.from(p.xy).slice(2):p.xy)); }
    return this.addPath(xy,this.paths[ids.at(-1)].endNode);
  }
  sample(id, distance) {
    const p=this.paths[id], d=Math.max(0,Math.min(distance,p.length));
    let lo=0,hi=p.cumulative.length-1;
    while(lo<hi){const mid=(lo+hi+1)>>1;if(p.cumulative[mid]<=d)lo=mid;else hi=mid-1;}
    const k=Math.min(lo,p.cumulative.length-2), span=p.cumulative[k+1]-p.cumulative[k];
    const f=span>0?(d-p.cumulative[k])/span:0;
    return [p.xy[2*k]+(p.xy[2*k+2]-p.xy[2*k])*f,p.xy[2*k+1]+(p.xy[2*k+3]-p.xy[2*k+1])*f,k];
  }
  cruise(cell, random) {
    const home=this.road.cellNodes[cell], centre=this.point(home);
    const scope=this.local(cell);
    const ids=[];let node=home, previous=-1;
    for(let k=0;k<9;k++){
      let choices=this.adj[node].filter(id=>{
        const e=this.road.edges[id],p=this.point(e[1]);
        return scope.edges.has(id)&&e[1]!==previous&&Math.hypot(p[0]-centre[0],p[1]-centre[1])<=1100;
      });
      if(!choices.length)choices=this.adj[node].filter(id=>scope.edges.has(id));
      if(!choices.length) break;
      const id=choices[Math.floor(random()*choices.length)];ids.push(id);previous=node;node=this.road.edges[id][1];
    }
    if(!ids.length){this.stationaryCruiseCells.add(cell);return this.route(home,home);}
    const routeIds=ids.map(id=>this.addPath(this.geometry(id),this.road.edges[id][1]));
    routeIds.push(this.route(node,home,scope));return this.join(routeIds);
  }
  local(cell){
    const home=this.road.cellNodes[cell];if(this.localCache.has(home))return this.localCache.get(home);
    const centre=this.point(home),seen=new Uint8Array(this.N),edges=new Set(),queue=[home],checked=new Map();seen[home]=1;
    // Reverse reachability makes every permitted random-walk node able to return home locally.
    for(let k=0;k<queue.length;k++)for(const id of this.reverse[queue[k]]){
      const e=this.road.edges[id],p=this.point(e[0]);if(Math.hypot(p[0]-centre[0],p[1]-centre[1])>1100)continue;
      if(!checked.has(id)){
        const xy=this.geometry(id);let valid=true;
        for(let j=0;j<xy.length;j+=2)if(Math.hypot(xy[j]-centre[0],xy[j+1]-centre[1])>1250){valid=false;break;}
        checked.set(id,valid);
      }
      if(!checked.get(id))continue;edges.add(id);if(!seen[e[0]]){seen[e[0]]=1;queue.push(e[0]);}
    }
    const scope={home,edges};this.localCache.set(home,scope);return scope;
  }
  approach(cruiseId, distance, originCell, requestCell) {
    const p=this.paths[cruiseId], [x,y,k]=this.sample(cruiseId,distance);
    // Continue forward along the directed cruise walk, then use shortest cell-node paths.
    const tail=[x,y,...Array.from(p.xy).slice((k+1)*2)];
    const origin=this.road.cellNodes[originCell], request=this.road.cellNodes[requestCell];
    const ids=[this.addPath(tail,p.endNode),this.route(p.endNode,origin),this.route(origin,request)];
    return this.join(ids);
  }
}

if(typeof module!=="undefined")module.exports={RoadRouter,MinHeap};
