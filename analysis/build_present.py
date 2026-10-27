"""Build outputs/story/present.html, the 15-minute talk version of the story page (decision 174).

Presentation only: reads saved tables, the saved storm export and the charts from analysis/present_charts.py.
No estimation, labels or scoring. outputs/story/index.html is not read or written.
Run: .venv/bin/python -m analysis.present_charts && .venv/bin/python -m analysis.build_present
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

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
    expected = {'heavy': '−12.9%', 'heavy_round': '−13%', 'central': '−24.5%', 'central_round': '−25%', 'approach': '−7%',
                'firsthour': '−5%', 'recovery': '2.5 h', 'changi_lost': '7.1', 'changi_expected': '83', 'changi_pct': '−8.5%',
                'bayfront': '−36%', 'dhoby': '−35%', 'raffles': '−31%', 'gain': '0.001', 'lgb': '53%', 'persist': '46%',
                'lead': '6–13%', 'morning': '6–10%', 'policy': '44%', 'random': '28%', 'holdout': '+0.009'}
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
    data = {'land': land, 'cells': [[int(c), bool(e)] for c, e in names.loc[names.land, ['cell', 'eligible']].itertuples(index=False)],
            'storm': storm(), 'meta': json.loads(track(CHARTS / 'meta.json').read_text())}
    template = (SOURCE / 'template.html').read_text()
    css = (SOURCE / 'present.css').read_text().replace('/*__FONTS__*/', fonts())
    js = (SOURCE / 'present.js').read_text()
    for key, value in v.items():
        assert '{{' + key + '}}' in template, key
        template = template.replace('{{' + key + '}}', value)
    assert '{{' not in template
    for name in ['present_event_timeline', 'present_places_bar', 'present_factors', 'present_planning_heatmap']:
        template = template.replace(f'<!--SVG:{name}-->', chart(name))
    assert '<!--SVG:' not in template
    slides = re.findall(r'<section class="slide[^"]*" id="([^"]+)"', template)
    assert len(slides) == 15 and template.count('data-appendix>') == 1
    notes = re.findall(r'<aside class="notes">(.*?)</aside>', template, flags=re.S)
    words = [len(n.split()) for n in notes]
    assert len(notes) == 15 and all(80 <= w <= 120 for w in words[:14]), words
    assert 'logo' not in template.lower() and 'not affiliated with ComfortDelGro' in template
    html = (template.replace('/*__CSS__*/', css)
            .replace('/*__DATA__*/', 'const DATA = ' + json.dumps(data, separators=(',', ':')).replace('</', '<\\/') + ';')
            .replace('/*__JS__*/', js))
    OUT.write_text(html)
    for rel, digest in HASHES.items():
        assert sha(ROOT / rel) == digest, rel
    (OUT.parent / 'present_provenance.json').write_text(json.dumps(
        {'presentation_only': True, 'decision': 174, 'slides': 14, 'appendix_slides': 1, 'notes_words': words,
         'values': v, 'source_hashes': HASHES, 'html_sha256': sha(OUT), 'bytes': OUT.stat().st_size},
        indent=2, ensure_ascii=False) + '\n')
    print(f'Built {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes); 14 slides + appendix; notes {min(words)}–{max(words)} words.')


if __name__ == '__main__':
    main()
