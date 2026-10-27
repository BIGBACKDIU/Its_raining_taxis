"""Build outputs/story/present.html, the 15-minute talk version of the story page (decision 174).

Presentation only: reads saved tables, the saved storm export and the charts from analysis/present_charts.py.
No estimation, labels or scoring. outputs/story/index.html is not read or written.
Run: .venv/bin/python -m analysis.present_charts && .venv/bin/python -m analysis.build_present
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import segno
import zxingcpp
from PIL import Image

from pipeline.grid import to_xy

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'present'
CHARTS = ROOT / 'outputs/figures/deck/present'
OUT = ROOT / 'outputs/story/present.html'
HASHES = {}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def track(path):
    HASHES[str(path.relative_to(ROOT))] = sha(path)
    return path


def read(name):
    return pd.read_csv(track(ROOT / 'outputs/tables' / f'{name}.csv'))


def pct(value, decimals=0):
    return f'{value:.{decimals}f}%'.replace('-', '−')


def values():
    """Every number shown on the slides that comes from a saved table."""
    v = {}
    e = read('effects_main').query("model=='abs' and term=='heavy'").iloc[0]
    v['heavy'], v['heavy_round'] = pct(e.pct, 1), pct(e.pct)
    f = read('factors_panel_interactions').query("model=='abs'").set_index('term')
    c = f.loc['CONTRAST: heavy, Central Area', 'pct']
    v['central'], v['central_round'] = pct(c, 1), pct(c)
    a = read('effects_approach').query("model=='abs' and term=='ring_heavier_owndry'").iloc[0]
    v['approach'] = pct(a.pct)
    ev = read('effects_event_study').query("model=='event_abs'").sort_values('event_min').reset_index(drop=True)
    v['firsthour'] = pct(ev.loc[ev.event_min == 0, 'pct'].iloc[0])
    after = ev[ev.event_min >= 0]
    inside = (after.pct_lo <= 0) & (after.pct_hi >= 0)
    first = next(m for m, ok in zip(after.event_min, inside) if ok and inside[after.event_min >= m].all())
    v['recovery'] = f'{first / 60:g} h'
    top = read('rain_hit_top30_absolute').set_index('cell')
    ch = top.loc[48022]
    v['changi_lost'], v['changi_expected'], v['changi_pct'] = f'{ch.taxis_lost_per_heavy_half_hour:.1f}', f'{ch.expected_vacant_heavy:.0f}', pct(ch.abs_pct, 1)
    v['bayfront'], v['dhoby'], v['raffles'] = (pct(top.loc[c_, 'abs_pct']) for c_ in (34014, 32016, 33014))
    fc = read('forecast_eval_both_labels').query("analysis=='primary' and scale=='1km' and label_version=='issue-time' and subset=='all'")
    assert sorted(fc.h) == [30, 60]
    v['gain'] = f'{fc.weather_gain.mean():.3f}'
    v['lgb'] = pct(100 * fc[['topk_precision_lgb_no_weather', 'topk_precision_lgb_weather']].to_numpy().mean())
    v['persist'] = pct(100 * fc.topk_precision_persistence.mean())
    lead = read('forecast_eval_lead_both_labels').query(
        "analysis=='primary' and scale=='1km' and label_version=='retrospective' and model in ['lgb_no_weather','lgb_weather']")
    v['lead'] = f'{100 * lead.share_warned_before_onset.min():.0f}–{pct(100 * lead.share_warned_before_onset.max())}'
    m = read('morning_forecast_value').query("model=='lgb'").set_index('label').deviance_improvement_pct
    v['morning'] = f"{m['issue-time']:.0f}–{pct(m['retrospective'])}"
    pol = read('policy_diagnosis').query("split=='test'").set_index('variant').precision_issue_time
    v['policy'] = pct(100 * pol['(b) policy, weights = forecast risk'])
    v['random'] = pct(100 * pol['all candidate cells (expected >= 4)'])
    h = read('s22b_materiality').query("target=='T2_15' and horizon==60").iloc[0]
    v['holdout'] = f'+{h.gain:.3f}'
    r = read('radar_effects').query("model=='abs' and dry_threshold_mmh==0 and term=='heavy' and source=='radar'").iloc[0]
    v['radar_heavy'] = pct(r.pct, 1)
    v['cbd_range'] = f"{v['raffles']} to {v['bayfront']}"
    isl = read('spillover_islandwide_share')
    v['island_fewer'], v['island_more'] = str((isl.absolute == 'fewer taxis').sum()), str((isl.absolute == 'more taxis').sum())
    desert = read('taxi_deserts').set_index('subzone').loc['Punggol Town Centre', 'vacant_per_10k_residents']
    v['punggol'] = f'{desert:.2f}'
    v['holdout_onsets'] = str(len(read('s22b_storm_onsets')))
    october = read('s22_materiality').query("target=='T2_15' and horizon==60").iloc[0]
    sign = lambda x: f'{x:+.3f}'
    v['h26'], v['h26_ci'], v['h26_onsets'] = sign(october.gain), f'{sign(october.lo)} to {sign(october.hi)}', str(len(read('s22_storm_onsets')))
    v['h19'], v['h19_ci'] = sign(h.gain), f'{sign(h.lo)} to {sign(h.hi)}'
    audit = json.loads(track(ROOT / 'outputs/tables/audit_summary.json').read_text())
    v['snap_ok'], v['snap_expected'], v['snap_usable'] = (f"{audit[k]:,}" for k in ['snapshots_ok', 'snapshots_expected', 'snapshots_usable'])
    v['snap_share'] = pct(100 * audit['snapshots_ok'] / audit['snapshots_expected'], 1)
    monthly = read('audit_monthly').gauges.dropna()
    v['gauges'] = f'{int(monthly.min())}–{int(monthly.max())}'
    v['stuck_gauges'], v['stuck_days'] = str(audit['stuck_gauges']), str(audit['gauge_days_stuck'])
    v['excluded_days'], v['outage_days'] = str(audit['days_excluded_main']), str(audit['unusual_feed_outage'])
    v['spells'] = str((read('feed_regimes').kind == 'spell').sum())
    v['sim1'], v['sim2'] = (str(read(t).storms_passed.max()) for t in ['sim_plausibility', 'sim2_plausibility'])
    v['bench'] = str(read('sim2_diagnosis_summary').query("period=='test'").stat_passes.iloc[0])
    v['test_log'] = str(len(pd.read_csv(track(ROOT / 'outputs/test_scoring_log.csv'))))
    em = read('effects_main').set_index(['model', 'term']).pct
    v['light'], v['moderate'], v['share_heavy'] = pct(em['abs', 'light'], 1), pct(em['abs', 'moderate'], 1), pct(em['share', 'heavy'], 1)
    v['deepest'] = pct(ev.loc[ev.event_min == 30, 'pct'].iloc[0], 1)
    dose = read('dose_spline_curve').query("model=='abs'").set_index('mmh').pct
    v['dose1'] = pct(dose[1.0], 1)
    dh = read('dose_duration_hangover').query("model=='abs'").set_index('term').pct
    v['long_spell'] = pct(dh['heavy_wet>120'])
    v['after'] = pct(-dh[[t for t in dh.index if t.startswith('dry_')][0]])
    v['hotspots'] = str((read('inference_hotspots').hotspot == 'significantly lower').sum())
    v['reference'] = pct(f.loc['CONTRAST: heavy, MRT >= 1 km (reference)', 'pct'], 1)
    fs = read('factors_panel_interactions').query("model=='share'").set_index('term').pct
    v['central_share'], v['reference_share'] = pct(fs['CONTRAST: heavy, Central Area'], 1), pct(fs['CONTRAST: heavy, MRT >= 1 km (reference)'], 1)
    wls = read('factors_cell_wls').query("outcome=='abs'").set_index('characteristic').pct_per_sd
    v['wls_central'], v['wls_stands'] = f"{-wls['central_area']:.0f}%", f"+{wls['taxi_stands_300m']:.1f}%"
    others = f.loc[[t for t in f.index if t.startswith('CONTRAST') and 'Central' not in t], 'pct']
    v['others'] = f'{pct(others.max(), 1)} to {pct(others.min(), 1)}'
    rf = read('factors_cell_summary').rf_spatial_cv_r2
    v['rf_r2'] = f'{rf.min():.2f}–{rf.max():.2f}'
    expected = {'heavy': '−12.9%', 'heavy_round': '−13%', 'central': '−24.5%', 'central_round': '−25%', 'approach': '−7%',
                'firsthour': '−5%', 'recovery': '2.5 h', 'changi_lost': '7.1', 'changi_expected': '83', 'changi_pct': '−8.5%',
                'bayfront': '−36%', 'dhoby': '−35%', 'raffles': '−31%', 'gain': '0.001', 'lgb': '53%', 'persist': '46%',
                'lead': '6–13%', 'morning': '6–10%', 'policy': '44%', 'random': '28%', 'holdout': '+0.009',
                'radar_heavy': '−12.0%', 'cbd_range': '−31% to −36%', 'island_fewer': '329', 'island_more': '3',
                'punggol': '0.73', 'holdout_onsets': '49', 'h26': '+0.024', 'h26_ci': '+0.012 to +0.079', 'h26_onsets': '2',
                'h19': '+0.009', 'h19_ci': '+0.001 to +0.017', 'snap_ok': '120,017', 'snap_expected': '122,688',
                'snap_usable': '118,136', 'snap_share': '97.8%', 'gauges': v['gauges'], 'stuck_gauges': '20', 'stuck_days': '439',
                'excluded_days': '100', 'outage_days': '17', 'spells': '8', 'sim1': '4', 'sim2': '3', 'bench': '3',
                'test_log': v['test_log'], 'light': '−7.7%', 'moderate': '−10.8%', 'share_heavy': '−5.7%',
                'deepest': '−5.6%', 'dose1': '−9.7%', 'long_spell': '−18%', 'after': '5%', 'hotspots': '299',
                'reference': '−12.0%', 'central_share': '−18.9%', 'reference_share': '−5.0%', 'wls_central': '11%',
                'wls_stands': '+2.5%', 'rf_r2': '0.12–0.15', 'others': '−11.6% to −12.5%'}
    assert v == expected, {k: (v[k], expected[k]) for k in v if v[k] != expected.get(k)}
    return v


def storm():
    path, meta = ROOT / 'outputs/story/data/storm_2023-07-20.csv', ROOT / 'outputs/story/data/storm_2023-07-20.json'
    track(path), track(meta)
    assert sha(path) == json.loads(meta.read_text())['export_sha256']
    t = pd.read_csv(path)
    assert len(t) == 5610 and not t.duplicated(['ts', 'cell']).any()
    cells = sorted(t.cell.unique())
    frames = [g.set_index('cell').loc[cells] for _, g in t.groupby('ts', sort=True)]
    out = {'times': sorted(t.ts.unique()), 'cells': [int(c) for c in cells],
           'vacant': [g.vacant.astype(int).tolist() for g in frames],
           'baseline': [np.round(g.baseline, 4).tolist() for g in frames],
           'mmh': [np.round(g.mmh, 2).tolist() for g in frames]}
    peak = out['times'].index('2023-07-20 09:30:00')
    obs, exp = sum(out['vacant'][peak]), sum(out['baseline'][peak])
    assert obs == 1473 and round(exp - obs) == 837 and round(100 * (obs / exp - 1), 1) == -36.2 and round(exp) == 2310
    return out


def chart(name):
    svg = track(CHARTS / f'{name}.svg').read_text()
    svg = svg[svg.index('<svg'):]
    svg = re.sub(r'<metadata>.*?</metadata>', '', svg, flags=re.S)
    svg = re.sub(r'<svg([^>]*?) width="[^"]+" height="[^"]+"', r'<svg\1', svg, count=1)
    svg = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{name}-{m.group(1)}"', svg)
    svg = re.sub(r'url\(#([^)]+)\)', lambda m: f'url(#{name}-{m.group(1)})', svg)
    svg = re.sub(r'xlink:href="#([^"]+)"', lambda m: f'xlink:href="#{name}-{m.group(1)}"', svg)
    return svg.replace('<svg', '<svg role="img" aria-label="Chart"', 1)

URL = 'https://storm-builder-sg.vercel.app'


def qr():
    """Offline QR code for the Storm Builder, decoded again before it is used."""
    code = segno.make(URL, error='m')
    png = io.BytesIO()
    code.save(png, kind='png', scale=10, border=4)
    decoded = [r.text for r in zxingcpp.read_barcodes(Image.open(io.BytesIO(png.getvalue())).convert('L'))]
    assert decoded == [URL], decoded
    svg = code.svg_inline(dark='#0B1F3A', light='#FFFFFF', border=2, omitsize=True)
    return svg.replace('<svg ', '<svg role="img" aria-label="QR code for storm-builder-sg.vercel.app" ', 1), decoded[0]


def title_map(rng):
    """Dark title map from the Storm Builder's own map data (10 m units), plus taxi routes along real roads."""
    d = json.loads(track(ROOT / 'sim/v3/data.json').read_text())
    q = lambda a: [int(round(x / 10)) for x in a]
    land = [q([c for pt in ring for c in pt]) for ring in d['land']]
    green = [q(ring) for poly in d['landuse']['green'] for ring in poly if len(ring) >= 8]
    water = [q(ring) for poly in d['landuse']['water'] for ring in poly if len(ring) >= 8]
    nodes = d['road']['nodes']
    xy = lambda n: (nodes[2 * n], nodes[2 * n + 1])
    roads = [[], [], []]
    adjacency = {}
    for k, e in enumerate(d['road']['edges']):
        if e[2] > 2:
            continue
        line = [*xy(e[0]), *e[4:], *xy(e[1])]
        roads[e[2]].append(q(line))
        adjacency.setdefault(e[0], []).append((e[1], line))
        back = [c for i in range(len(line) - 2, -1, -2) for c in line[i:i + 2]]
        adjacency.setdefault(e[1], []).append((e[0], back))
    starts = sorted(adjacency)
    routes = []
    while len(routes) < 360:
        node = starts[int(rng.integers(len(starts)))]
        pts, previous, length = list(xy(node)), None, 0.0
        target = rng.uniform(6000, 14000)
        for _ in range(400):
            options = [o for o in adjacency.get(node, []) if o[0] != previous] or adjacency.get(node, [])
            if not options or length >= target:
                break
            nxt, line = options[int(rng.integers(len(options)))]
            seg = np.array(line).reshape(-1, 2)
            length += float(np.hypot(*np.diff(seg, axis=0).T).sum())
            pts += line[2:]
            previous, node = node, nxt
        if length < 3000:
            continue
        a = np.array(pts, float).reshape(-1, 2)
        cum = np.r_[0, np.cumsum(np.hypot(*np.diff(a, axis=0).T))]
        at = np.arange(0, cum[-1], 120.0)
        routes.append(q(np.column_stack([np.interp(at, cum, a[:, 0]), np.interp(at, cum, a[:, 1])]).ravel()))
    return {'land': land, 'green': green, 'water': water, 'roads': roads, 'routes': routes}


def fonts():
    out = []
    for family, folder, weights in [('Poppins', 'poppins', [('Regular', 400), ('Medium', 500), ('SemiBold', 600)]),
                                    ('Anton', 'anton', [('Regular', 400)])]:
        for filename, weight in weights:
            p = track(ROOT / f'assets/fonts/{folder}/{family}-{filename}.ttf')
            out.append(f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};font-display:block;"
                       f"src:url(data:font/ttf;base64,{base64.b64encode(p.read_bytes()).decode()}) format('truetype')}}")
    return '\n'.join(out)


def main():
    v = values()
    names = read('names_cells')
    coast = track(ROOT / 'data/static/sg_map.json')
    land = [np.round(np.array(to_xy(np.array(r)[:, 0], np.array(r)[:, 1])).T / 1000, 3).tolist()
            for r in json.loads(coast.read_text())['land']]
    qr_svg, decoded = qr()
    data = {'land': land, 'cells': [[int(c), bool(e)] for c, e in names.loc[names.land, ['cell', 'eligible']].itertuples(index=False)],
            'storm': storm(), 'meta': json.loads(track(CHARTS / 'meta.json').read_text()),
            'title': title_map(np.random.default_rng(2702))}
    template = (SOURCE / 'template.html').read_text()
    css = (SOURCE / 'present.css').read_text().replace('/*__FONTS__*/', fonts())
    js = (SOURCE / 'present.js').read_text()
    unused = {'firsthour', 'bayfront', 'dhoby', 'raffles', 'light', 'moderate', 'share_heavy', 'deepest', 'dose1',
              'long_spell', 'after', 'hotspots', 'central_share', 'reference_share', 'wls_central', 'wls_stands', 'rf_r2',
              'lgb', 'persist', 'lead'}  # checked against the tables above, no longer shown since decision 176
    for key, value in v.items():
        if key in unused:  # values kept in the provenance; slide text may no longer show them
            template = template.replace('{{' + key + '}}', value)
            continue
        assert '{{' + key + '}}' in template, key
        template = template.replace('{{' + key + '}}', value)
    assert '{{' not in template
    assert template.count('<!--QR-->') == 2
    template = template.replace('<!--QR-->', qr_svg)
    for name in sorted(set(re.findall(r'<!--SVG:([a-z_]+)-->', template))):
        template = template.replace(f'<!--SVG:{name}-->', chart(name))
    assert '<!--SVG:' not in template
    slides = re.findall(r'<section class="slide[^"]*" id="([^"]+)"', template)
    assert len(slides) == 27 and template.count('data-appendix=') == 13
    notes = re.findall(r'<aside class="notes">(.*?)</aside>', template, flags=re.S)
    words = [len(n.split()) for n in notes]
    assert len(notes) == 27 and all(80 <= w <= 120 for w in words[:14]), words
    assert 'logo' not in template.lower() and 'to be added' not in template.lower()
    html = (template.replace('/*__CSS__*/', css)
            .replace('/*__DATA__*/', 'const DATA = ' + json.dumps(data, separators=(',', ':')).replace('</', '<\\/') + ';')
            .replace('/*__JS__*/', js))
    OUT.write_text(html)
    for rel, digest in HASHES.items():
        assert sha(ROOT / rel) == digest, rel
    (OUT.parent / 'present_provenance.json').write_text(json.dumps(
        {'presentation_only': True, 'decisions': [174, 175, 176], 'slides': 14, 'appendix_slides': 13, 'qr_decoded': decoded, 'notes_words': words,
         'values': v, 'source_hashes': HASHES, 'html_sha256': sha(OUT), 'bytes': OUT.stat().st_size},
        indent=2, ensure_ascii=False) + '\n')
    print(f'Built {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes); 14 slides + references + A1–A9; QR decodes to {decoded}; notes {min(words)}–{max(words)} words.')


if __name__ == '__main__':
    main()
