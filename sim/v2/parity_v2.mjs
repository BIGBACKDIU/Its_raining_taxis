// Node parity check for simulation v2: run the JavaScript engine for one scenario and storm over N seeds.
// Usage: node sim/v2/parity_v2.mjs '{"scen": {...}, "params": {...}, "storm": "2026-09-27", "seeds": 50}'
import { createRequire } from "module";
import { readFileSync } from "fs";
const require = createRequire(import.meta.url);
const { World, runSeeds } = require("./engine_v2.js");
const arg = JSON.parse(process.argv[2]);
const data = JSON.parse(readFileSync(new URL("./data.json", import.meta.url)));
const world = new World(data.cells, data.T, data.weights, data.off_scale);
const storm = data.storms.find((s) => s.date === arg.storm);
const city = runSeeds(world, storm, arg.scen, arg.params, arg.seeds, 2702);
let mean = 0, n = 0;
const snaps = storm.snap_minutes;
let pk = 0, best = Infinity;
snaps.forEach((m, k) => { const d = Math.abs(m - storm.peak_minute); if (d < best) { best = d; pk = k; } });
let peak = 0;
for (const row of city) {
  for (let k = 0; k < row.length; k++) { mean += row[k] / row[0]; n++; }
  peak += row[pk] / row[0];
}
console.log(JSON.stringify({ mean_rel: mean / n, peak_rel: peak / city.length }));
