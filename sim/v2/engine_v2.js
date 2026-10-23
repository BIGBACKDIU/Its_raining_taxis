// Simulation v2 (step 20) - JavaScript port of analysis/sim_engine_v2.py: OpenStreetMap drive times between cells,
// drive-time dispatch rings, per-cell request/destination weights, per-cell rain sensitivity.
// Scenario-based operational model (never "validation"). Keep the rules identical to the Python engine.
// One seed per Sim instance; the Python engine vectorises seeds, the rules are the same.

const RING_MIN = [0.0, 4.0, 7.0, 10.0, 15.0, 20.0];
const PATIENCE_MIN = 6.0;
const RAIN_FACTOR = 1.25;
const DECAY_MIN = 15.0;
const HORIZON_PAD = 150;

// ---------------------------------------------------------------- random numbers (seeded)
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
class RNG {
  constructor(seed) { this.u = mulberry32(seed >>> 0); this.spare = null; }
  random() { return this.u(); }
  normal() {
    if (this.spare !== null) { const s = this.spare; this.spare = null; return s; }
    let u = 0, v = 0;
    while (u === 0) u = this.u();
    v = this.u();
    const r = Math.sqrt(-2 * Math.log(u)), th = 2 * Math.PI * v;
    this.spare = r * Math.sin(th);
    return r * Math.cos(th);
  }
  poisson(lam) {
    if (lam <= 0) return 0;
    if (lam < 30) {
      const L = Math.exp(-lam); let k = 0, p = 1;
      do { k++; p *= this.u(); } while (p > L);
      return k - 1;
    }
    return Math.max(0, Math.round(lam + Math.sqrt(lam) * this.normal()));
  }
  binomial(n, p) {
    if (n <= 0 || p <= 0) return 0;
    if (p >= 1) return n;
    if (n < 40) { let k = 0; for (let i = 0; i < n; i++) if (this.u() < p) k++; return k; }
    const m = n * p, sd = Math.sqrt(n * p * (1 - p));
    return Math.min(n, Math.max(0, Math.round(m + sd * this.normal())));
  }
  choiceCum(cum, offset, len) {          // index in a cumulative array slice [offset, offset+len)
    const x = this.u() * cum[offset + len - 1];
    let lo = 0, hi = len - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (cum[offset + mid] < x) lo = mid + 1; else hi = mid; }
    return lo;
  }
}

// ---------------------------------------------------------------- world
class World {
  constructor(cells, T, weights, offScale) {
    const C = cells.cell.length;
    this.C = C;
    this.T = Float64Array.from(T);
    this.rings = [];
    for (let r = 0; r < RING_MIN.length - 1; r++) {
      const a = RING_MIN[r], b = RING_MIN[r + 1], adj = [];
      for (let i = 0; i < C; i++) {
        const row = [];
        for (let j = 0; j < C; j++) { const t = this.T[i * C + j]; if (i !== j && t > a && t <= b) row.push(j); }
        adj.push(Int32Array.from(row));
      }
      this.rings.push({ adj, mid: (a + b) / 2 });
    }
    this.stands = Float64Array.from(cells.stands);
    this.offScale = Float64Array.from(offScale);
    this.attr = {}; this.P = {}; this.cum = {}; this.attrCum = {};
    for (const k of Object.keys(weights)) {
      const w = weights[k];
      let s = 0; for (const v of w) s += v;
      this.attr[k] = Float64Array.from(w.map((v) => v / s));
      const P = new Float64Array(C * C), cum = new Float64Array(C * C);
      for (let i = 0; i < C; i++) {
        let t = 0;
        for (let j = 0; j < C; j++) { const v = w[j] * Math.exp(-this.T[i * C + j] / DECAY_MIN); P[i * C + j] = v; t += v; }
        let c = 0;
        for (let j = 0; j < C; j++) { P[i * C + j] /= t; c += P[i * C + j]; cum[i * C + j] = c; }
      }
      this.P[k] = P; this.cum[k] = cum;
      const ac = new Float64Array(C); let c = 0;
      for (let i = 0; i < C; i++) { c += this.attr[k][i]; ac[i] = c; }
      this.attrCum[k] = ac;
    }
  }
  meanTripMinutes(dest) {
    const C = this.C, P = this.P[dest], a = this.attr[dest];
    let t = 0;
    for (let i = 0; i < C; i++) for (let j = 0; j < C; j++) t += a[i] * P[i * C + j] * (this.T[i * C + j] + 2);
    return t + 1;
  }
}

// ---------------------------------------------------------------- step-7 objective, greedy (same as Python)
function poissonPmf(mu, n) {
  const p = new Float64Array(n); let v = Math.exp(-mu); p[0] = v;
  for (let k = 1; k < n; k++) { v *= mu / k; p[k] = v; }
  return p;
}
function greedyPlan(world, vac, baseNow, baseNext, mu, rain, share, travel, N = 200, lam = 0.005, lead = 60, kmax = 20, s0min = 0.05) {
  const C = world.C;
  const movable = new Int32Array(C);
  for (let i = 0; i < C; i++) movable[i] = Math.floor(share * Math.max(0, vac[i] - baseNow[i]));
  const r = [], s0 = new Float64Array(C);
  let ymax = 0; for (let i = 0; i < C; i++) ymax = Math.max(ymax, Math.ceil(baseNext[i]));
  const ny = ymax + kmax + 2;
  for (let j = 0; j < C; j++) {
    const pmf = poissonPmf(Math.max(mu[j], 1e-6), ny), b = baseNext[j], S = new Float64Array(kmax + 1);
    for (let m = 0; m <= kmax; m++) { let e = 0; for (let y = 0; y < ny; y++) e += Math.max(0, b - (y + m)) * pmf[y]; S[m] = e / Math.max(1, b); }
    s0[j] = S[0];
    const rj = new Float64Array(kmax); for (let k = 0; k < kmax; k++) rj[k] = S[k] - S[k + 1];
    r.push(rj);
  }
  const origins = [], dests = [];
  for (let i = 0; i < C; i++) if (movable[i] > 0) origins.push(i);
  for (let j = 0; j < C; j++) if (baseNext[j] >= 4 && world.stands[j] > 0 && s0[j] >= s0min) dests.push(j);
  const moves = new Map();
  if (!origins.length || !dests.length) return moves;
  const T = (i, j) => world.T[i * C + j] * ((rain[i] > 0 && travel === "rain") ? RAIN_FACTOR : 1.0);
  const got = new Int32Array(C), left = Int32Array.from(movable);
  let budget = N;
  while (budget > 0) {
    let best = 0, bi = -1, bj = -1;
    for (const j of dests) {
      if (got[j] >= kmax) continue;
      const g = r[j][got[j]];
      for (const i of origins) {
        if (left[i] <= 0 || i === j) continue;
        const t = T(i, j);
        if (t > lead) continue;
        const v = g - lam * t;
        if (v > best) { best = v; bi = i; bj = j; }
      }
    }
    if (bi < 0) break;
    const key = bi * C + bj;
    moves.set(key, { i: bi, j: bj, n: (moves.get(key)?.n || 0) + 1, t: T(bi, bj) });
    got[bj]++; left[bi]--; budget--;
  }
  return moves;
}

// systematic rounding: each entry floor or ceil of x, total floor(sum + u) - floor(u)
function sysRound(x, u) {
  const out = new Int32Array(x.length);
  let c = 0, prev = Math.floor(u);
  for (let i = 0; i < x.length; i++) { c += x[i]; const k = Math.floor(c + u); out[i] = k - prev; prev = k; }
  return out;
}

// ---------------------------------------------------------------- one seed
class Sim {
  constructor(world, storm, scen, params, seed, opts = {}) {
    this.w = world; this.st = storm; this.scen = scen; this.p = params;
    this.rng = new RNG(seed);
    this.policy = !!opts.policy; this.rainMult = opts.rainMult ?? 1.0;
    const C = world.C, M = storm.minutes;
    this.C = C; this.M = M; this.m = 0;
    this.V = Int32Array.from(storm.v0);
    this.OFF = new Int32Array(C);
    this.ARR = Array.from({ length: M + HORIZON_PAD }, () => new Int32Array(C));
    this.Qw = new Float64Array(C);
    this.extra = new Float64Array(C);           // click-to-request (page only)
    const occ0 = params.occ0;
    let v0sum = 0; for (const v of storm.v0) v0sum += v;
    this.O0 = Math.round(v0sum * occ0 / (1 - occ0));
    this.F0 = v0sum + this.O0;
    this.tau = world.meanTripMinutes(scen.dest);
    this.lamTotal = this.O0 / this.tau * params.kappa;
    this.attr = world.attr[scen.dest];
    const ac = world.attrCum[scen.dest];
    for (let k = 0; k < this.O0; k++) {
      const o = this.rng.choiceCum(ac, 0, C);
      const t = 1 + Math.floor(this.rng.random() * 30);
      this.ARR[t][o]++;
    }
    this.Bcity0 = storm.base[0].reduce((a, b) => a + b, 0);
    this.stats = { requests: 0, served: 0, abandoned: 0, wait_minutes: 0, requests_rain: 0, abandoned_rain: 0 };
    this.lastMoves = [];
    this.inflight = 0;
  }
  rainAt(slot) { const r = this.st.rain[Math.min(slot, this.st.rain.length - 1)]; return r.map((v) => v * this.rainMult); }
  startTrips(cnt, i, approach, facArr) {
    const C = this.C, cum = this.w.cum[this.scen.dest];
    for (let k = 0; k < cnt; k++) {
      const d = this.rng.choiceCum(cum, i * C, C);
      const dur = approach + this.w.T[i * C + d] * facArr[i] + 2;
      const ta = Math.min(this.m + Math.ceil(dur), this.M + HORIZON_PAD - 1);
      this.ARR[ta][d]++;
    }
  }
  match(Q, nRings, facArr) {
    // Requests Q hold integers. Proportional allocation within each ring (decision 127): taxi cell i offers
    // min(V_i, P_i) over the requests it reaches; request cell j accepts at most Q_j of the offers it receives
    // (incoming adjacency); both sides are rounded with the same systematic offset, so taxis dispatched equal
    // requests served and no request or taxi is used twice.
    const C = this.C, V = this.V;
    let served = 0;
    let meanF = 0; for (let i = 0; i < C; i++) meanF += facArr[i]; meanF /= C;
    for (let i = 0; i < C; i++) {
      const own = Math.min(V[i], Q[i]);
      if (own > 0) { V[i] -= own; Q[i] -= own; served += own; this.startTrips(own, i, 1.0, facArr); }
    }
    for (let r = 0; r < nRings; r++) {
      let anyQ = 0, anyV = 0;
      for (let i = 0; i < C; i++) { anyQ += Q[i]; anyV += V[i]; }
      if (anyQ === 0 || anyV === 0) break;
      const { adj, mid } = this.w.rings[r];
      const g = new Float64Array(C), inc = new Float64Array(C);
      for (let i = 0; i < C; i++) {
        let P = 0; for (const j of adj[i]) P += Q[j];
        if (P > 0) { g[i] = Math.min(V[i], P) / P; for (const j of adj[i]) inc[j] += g[i]; }
      }
      const srv = new Float64Array(C), sj = new Float64Array(C), used = new Float64Array(C);
      for (let j = 0; j < C; j++) { const R = Q[j] * inc[j]; srv[j] = Math.min(Q[j], R); sj[j] = R > 0 ? srv[j] / R : 0; }
      for (let i = 0; i < C; i++) {
        if (g[i] === 0) continue;
        let t = 0; for (const j of adj[i]) t += Q[j] * sj[j];
        used[i] = Math.min(V[i], g[i] * t);
      }
      const u = this.rng.random();
      const d = sysRound(used, u), q = sysRound(srv, u);
      let gap = 0; for (let i = 0; i < C; i++) gap += d[i] - q[i];
      for (let i = 0; i < C && gap > 0; i++) if (d[i] > 0) { d[i]--; gap--; }
      for (let j = 0; j < C && gap < 0; j++) if (q[j] > 0) { q[j]--; gap++; }
      for (let i = 0; i < C; i++) {
        if (d[i] > 0) { V[i] -= d[i]; served += d[i]; this.startTrips(d[i], i, mid * meanF, facArr); }
        Q[i] -= q[i];
      }
    }
    return served;
  }
  step() {
    const C = this.C, m = this.m, V = this.V, scen = this.scen;
    const slot = Math.min(Math.floor(m / 30), this.st.rain.length - 1);
    const r = this.rainAt(slot);
    const facArr = new Float64Array(C);
    for (let i = 0; i < C; i++) facArr[i] = (r[i] > 0 && scen.travel === "rain") ? RAIN_FACTOR : 1.0;
    const arr = this.ARR[m]; for (let i = 0; i < C; i++) V[i] += arr[i];
    // normal time-of-day path
    if (m % 30 === 0 && m > 0) {
      let onroad = 0; for (let i = 0; i < C; i++) onroad += V[i] + this.OFF[i];
      for (let t = m + 1; t < this.ARR.length; t++) { const a = this.ARR[t]; for (let i = 0; i < C; i++) onroad += a[i]; }
      const b = this.st.base[slot]; let bs = 0; for (const v of b) bs += v;
      const target = this.F0 * bs / this.Bcity0;
      let diff = Math.round(target - onroad);
      if (diff > 0) {
        const cum = new Float64Array(C); let s = 0; for (let i = 0; i < C; i++) { s += b[i]; cum[i] = s; }
        for (let k = 0; k < diff; k++) V[this.rng.choiceCum(cum, 0, C)]++;
      } else if (diff < 0) {
        let vs = 0; for (let i = 0; i < C; i++) vs += V[i];
        let n = Math.min(-diff, vs);
        while (n > 0) {
          const cum = new Float64Array(C); let s = 0; for (let i = 0; i < C; i++) { s += V[i]; cum[i] = s; }
          const i = this.rng.choiceCum(cum, 0, C); V[i]--; n--;
        }
      }
    }
    // supply drop and return
    if (scen.mechanism === "supply" || scen.mechanism === "mix") {
      for (let i = 0; i < C; i++) {
        const pOff = Math.min(1, this.p.beta_off * Math.min(r[i], 30) / 30 * this.w.offScale[i]);
        const off = this.rng.binomial(V[i], pOff);
        V[i] -= off; this.OFF[i] += off;
      }
    }
    for (let i = 0; i < C; i++) {
      const back = this.rng.binomial(this.OFF[i], r[i] > 0 ? 0 : 1 / 30);
      this.OFF[i] -= back; V[i] += back;
    }
    // policy every 30 minutes
    if (this.policy && m % 30 === 0 && m > 0) {
      const nxt = Math.min(slot + 2, this.st.base.length - 1);
      const vm = Float64Array.from(V);
      const plan = greedyPlan(this.w, vm, this.st.base[slot], this.st.base[nxt], vm, r, this.st.share, scen.travel);
      this.lastMoves = [];
      for (const mv of plan.values()) {
        const n = Math.min(mv.n, V[mv.i]);
        if (n <= 0) continue;
        V[mv.i] -= n;
        this.ARR[Math.min(m + Math.ceil(mv.t), this.M + HORIZON_PAD - 1)][mv.j] += n;
        this.lastMoves.push({ i: mv.i, j: mv.j, n });
      }
    }
    // waiting requests
    let rmean = 0; for (const v of r) rmean += v; rmean /= C;
    const rainCity = rmean > 0.5;
    let ab = 0;
    for (let i = 0; i < C; i++) { const a = this.rng.binomial(this.Qw[i], 1 / PATIENCE_MIN); this.Qw[i] -= a; ab += a; }
    this.stats.abandoned += ab; if (rainCity) this.stats.abandoned_rain += ab;
    this.stats.served += this.match(this.Qw, scen.dispatch === "widening" ? 5 : 3, facArr);
    let wq = 0; for (let i = 0; i < C; i++) wq += this.Qw[i]; this.stats.wait_minutes += wq;
    // new requests
    const dl = scen.demand_level ?? 1.0;
    const nw = new Float64Array(C);
    let nreq = 0;
    for (let i = 0; i < C; i++) {
      let lam = this.lamTotal * this.attr[i] * dl;
      if (scen.mechanism === "demand" || scen.mechanism === "mix") lam *= 1 + this.p.beta_dem * Math.min(r[i], 30) / 10;
      nw[i] = this.rng.poisson(lam) + Math.round(this.extra[i]);
      this.extra[i] = 0;
      nreq += nw[i];
    }
    this.stats.requests += nreq; if (rainCity) this.stats.requests_rain += nreq;
    const servedNew = this.match(nw, 3, facArr);
    if (servedNew > nreq) throw new Error(`more trips than requests at minute ${m}`);
    this.stats.served += servedNew;
    for (let i = 0; i < C; i++) this.Qw[i] += nw[i];
    this.m++;
  }
  vacantTotal() { let s = 0; for (const v of this.V) s += v; return s; }
}

function runSeeds(world, storm, scen, params, S, seed, opts = {}) {
  const snaps = storm.snap_minutes;
  const city = Array.from({ length: S }, () => new Float64Array(snaps.length));
  for (let s = 0; s < S; s++) {
    const sim = new Sim(world, storm, scen, params, seed + 7919 * s, opts);
    let k = 0;
    for (let m = 0; m < storm.minutes; m++) {
      sim.step();
      while (k < snaps.length && snaps[k] === m) { city[s][k] = sim.vacantTotal(); k++; }
    }
  }
  return city;
}

if (typeof module !== "undefined") module.exports = { World, Sim, RNG, runSeeds, greedyPlan };
