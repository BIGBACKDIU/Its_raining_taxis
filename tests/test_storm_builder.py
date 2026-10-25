"""Presentation observers and routing must preserve model numbers and road direction."""
import json
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js required for browser engine")
def test_observers_preserve_every_minute_and_scheduled_arrival():
    out = subprocess.run(["node", "tests/storm_builder_hooks.cjs"], check=True, capture_output=True, text=True)
    result = json.loads(out.stdout)
    assert result["cases"] == 12 and result["hookStatesIdentical"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js required for browser routing")
def test_shortest_directed_path_and_missing_path_counter():
    script = r"""
const assert=require('assert'),{RoadRouter}=require('./sim/v3/roads.js');
const r=new RoadRouter({nodes:[0,0,100,0,200,0],cellNodes:[0,2],
edges:[[0,2,0,300,100,112],[0,1,2,100],[1,2,2,100]]});
const id=r.route(0,2);assert.strictEqual(r.paths[id].length,200);
assert.strictEqual(r.route(0,2),id);assert.strictEqual(r.cache.size,1);
const missing=r.route(2,0);assert.strictEqual(r.fallbacks,1);
assert.strictEqual(r.paths[missing].length,200);r.route(2,0);assert.strictEqual(r.fallbacks,1);
"""
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js required for browser routing")
def test_cruise_does_not_escape_via_a_long_oneway_return():
    script = r"""
const assert=require('assert'),{RoadRouter}=require('./sim/v3/roads.js');
const r=new RoadRouter({nodes:[0,0,500,0,4000,0],cellNodes:[0],
edges:[[0,1,0,500],[1,2,0,3500],[2,0,0,4000]]});
const cruise=r.cruise(0,()=>0);
assert.strictEqual(r.paths[cruise].length,0);assert(r.stationaryCruiseCells.has(0));
assert.strictEqual(r.fallbacks,0);assert.strictEqual(r.paths[r.route(0,1)].length,500);
"""
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
