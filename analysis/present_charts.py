"""Presentation charts for outputs/story/present.html (decision 174). No estimation, tuning or scoring.

Run: .venv/bin/python -m analysis.present_charts

Uses the deck renderer in analysis/deck_charts.py (registered Poppins, glyph and bounds checks, 2x PNG)
with the same saved inputs. Writes:
  outputs/figures/deck/deck_factors.{svg,png}           new chart in the deck palette
  outputs/figures/deck/present/*.{svg,png}              presentation palette, sized for a 1920x1080 slide
  outputs/figures/deck/present/meta.json                SVG coordinates used by the page's animations
The eleven original deck exports and deck/audit.json are not touched.
"""
from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Rectangle

from analysis import deck_charts as dc

DECK = dc.OUT
PRESENT = DECK / 'present'
PALETTES = {
    'deck': {'navy': dc.NAVY, 'blue': dc.BLUE, 'light': dc.LIGHT, 'pale': dc.PALE, 'bg': dc.BG},
    'present': {'navy': '#0B3D91', 'blue': '#1E88E5', 'light': '#9CC9F5', 'pale': '#E3EEFB', 'bg': 'none',
                'yellow': '#FFC72C'},
}
CENTRAL = {'Downtown Core', 'Museum', 'Rochor', 'Outram', 'Kallang'}
FACTORS = [
    ('CONTRAST: heavy, Central Area', 'URA Central Area'),
    ('CONTRAST: heavy, MRT < 300 m (vs >= 1 km reference)', 'MRT exit < 300 m'),
    ('CONTRAST: heavy, MRT 300-1000 m', 'MRT exit 300–1,000 m'),
    ('CONTRAST: heavy, MRT >= 1 km (reference)', 'MRT exit ≥ 1 km (reference)'),
    ('CONTRAST: heavy, taxi stand within 300 m', 'Taxi stand within 300 m'),
    ('CONTRAST: heavy, mall in cell', 'Mall in the square'),
]
META = {}


def use(palette, out):
    """Point the shared deck renderer at a palette and output folder."""
    p = PALETTES[palette]
    dc.OUT = out
    dc.BG = p['bg']
    dc.fonts()
    plt.rcParams.update({'svg.hashsalt': 'dao2702', 'svg.fonttype': 'none'})
    if palette == 'present':
        plt.rcParams.update({'figure.facecolor': 'none', 'axes.facecolor': 'none', 'savefig.facecolor': 'none',
                             'savefig.transparent': True})
    return p


def to_svg(fig, x, y, ax):
    """Data coordinates -> SVG user units of matplotlib's export (points; origin top-left)."""
    px, py = ax.transData.transform((x, y))
    return round(px * .72, 2), round((fig.bbox.height - py) * .72, 2)


def factors(palette, out, name, size):
    p = use(palette, out)
    t = dc.read('factors_panel_interactions').query("model=='abs'").set_index('term')
    rows = t.loc[[term for term, _ in FACTORS]].reset_index()
    assert rows.pct.round(1).tolist() == [-24.5, -12.5, -11.6, -12.0, -11.7, -12.3]
    dc.SIZES[name] = size
    dc.record(name, rows)
    fig = dc.figure(name)
    ax = dc.axes(fig, [.33, .17, .63, .78], grid=False)
    ax.xaxis.grid(True, color=dc.GRID, linewidth=.7)
    ref = rows.loc[3, 'pct']
    ax.axvline(ref, color=dc.MUTED, ls=(0, (1.5, 3)), lw=1.6, zorder=2)
    n = len(rows)
    for i, r in enumerate(rows.itertuples()):
        y = n - 1 - i
        color = dc.RED if i == 0 else p['navy']
        dc.error(ax, r.pct, y, r.pct_lo, r.pct_hi, color, horizontal=True, ms=11)
        ax.lines[-1].set_gid(f'factor-{i}')
        dc.label(ax, r.pct_lo - .5, y, dc.pct(r.pct), color, ha='right', va='center').set_gid(f'factor-label-{i}')
    dc.label(ax, ref + .3, n - .45, f'Reference {dc.pct(ref)}', dc.MUTED, size=22, va='center')
    ax.set(xlim=(-31, -6), ylim=(-.6, n - .2), xlabel='% vacant taxis in heavy rain vs dry')
    ax.set_yticks(range(n)[::-1], [label for _, label in FACTORS])
    ax.set_xticks([-30, -25, -20, -15, -10], ['−30%', '−25%', '−20%', '−15%', '−10%'])
    ax.tick_params(axis='y', pad=14)
    ax.spines['bottom'].set_color(dc.GRID)
    dc.save(fig, name)


def event(out, size):
    p = use('present', out)
    name = 'present_event_timeline'
    t = dc.read('effects_event_study').query("model=='event_abs'").reset_index(drop=True)
    dc.SIZES[name] = size
    dc.record(name, t)
    fig = dc.figure(name)
    ax = dc.axes(fig, [.10, .17, .87, .75])
    phases = [(-60, 0, 'Before'), (0, 60, 'First hour: deepest'), (60, 150, 'Recovery'), (150, 180, 'Noise')]
    for i, (start, end, text) in enumerate(phases):
        ax.axvspan(start, end, color=p['pale'] if i % 2 == 0 else '#EEF3FA', zorder=0, lw=0)
        dc.label(ax, (start + end) / 2, 2.2, text, dc.MUTED, size=22, ha='center', va='center')
    ax.fill_between(t.event_min, t.pct_lo, t.pct_hi, color=p['light'], alpha=.55, lw=0, gid='event-band')
    ax.plot(t.event_min, t.pct, color=p['navy'], lw=2.6, marker='o', ms=6, gid='event-line')
    ax.axvline(0, color=p['navy'], ls='--', lw=1.3)
    dc.label(ax, 0, 3.12, 'Rain starts', p['navy'], size=22, ha='center', va='bottom', weight=600, clip_on=False)
    ax.axhline(0, color=dc.MUTED, lw=.8)
    ax.set(xlim=(-60, 180), ylim=(-9, 3), xlabel='Minutes from rain onset in the square',
           ylabel='% vacant taxis vs −30 min')
    ax.set_xticks([-60, 0, 60, 120, 180], ['−60', '0', '+60', '+120', '+180'])
    ax.set_yticks([-8, -4, 0], ['−8%', '−4%', '0'])
    fig.canvas.draw()
    META[name] = {
        'points': [[*to_svg(fig, r.event_min, r.pct, ax), float(r.event_min), float(r.pct), float(r.pct_lo),
                    float(r.pct_hi)] for r in t.itertuples()],
        'top': to_svg(fig, -60, 3, ax)[1], 'bottom': to_svg(fig, -60, -9, ax)[1],
        'width': size[0] * .72, 'height': size[1] * .72,
    }
    dc.save(fig, name)


def places(out, size):
    p = use('present', out)
    name = 'present_places_bar'
    t = dc.read('rain_hit_top30_absolute').head(12).reset_index(drop=True)
    assert (t.expected_vacant_heavy >= 4).all() and (t.abs_q < .1).all()
    dc.SIZES[name] = size
    dc.record(name, t)
    fig = dc.figure(name)
    ax = dc.axes(fig, [.25, .14, .73, .84], grid=False)
    ax.xaxis.grid(True, color=dc.GRID, linewidth=.7)
    y = np.arange(12)[::-1]
    colors = [dc.RED if r.planning_area in CENTRAL else p['navy'] for r in t.itertuples()]
    bars = ax.barh(y, t.taxis_lost_per_heavy_half_hour, color=colors, height=.62, zorder=3)
    for i, (bar, yi, r, color) in enumerate(zip(bars, y, t.itertuples(), colors)):
        bar.set_gid(f'bar-{i}')
        text = f'{r.taxis_lost_per_heavy_half_hour:.1f} of {r.expected_vacant_heavy:.1f} ({dc.pct(r.abs_pct)})'
        dc.label(ax, r.taxis_lost_per_heavy_half_hour + .12, yi, text, color, va='center').set_gid(f'barlabel-{i}')
    ax.set_yticks(y, [dc.place_name(r) for r in t.itertuples()])
    ax.tick_params(axis='y', pad=14)
    ax.set(xlim=(0, 11.2), ylim=(-.7, 11.7), xlabel='Fewer vacant taxis per heavy-rain half-hour')
    ax.set_xticks([0, 2, 4, 6, 8])
    ax.spines['bottom'].set_color(dc.GRID)
    dc.save(fig, name)


def planning(out, size):
    p = use('present', out)
    name = 'present_planning_heatmap'
    t = dc.read('planning_rain_losses')
    t = t[t.condition.str.startswith('NEA') & (t.day == 'weekday')]
    order = t.groupby('planning_area').abs_loss_taxis_per_half_hour.max().sort_values(ascending=False).head(10).index
    bands = ['00-07', '07-10', '10-17', '17-20', '20-24']
    q = t[t.planning_area.isin(order)]
    dc.SIZES[name] = size
    dc.record(name, q)
    m = q.pivot(index='planning_area', columns='time_band', values='abs_loss_taxis_per_half_hour').reindex(index=order, columns=bands)
    pc = q.pivot(index='planning_area', columns='time_band', values='pct_change').reindex(index=order, columns=bands)
    cmap = LinearSegmentedColormap.from_list('present_blue', [p['pale'], p['light'], p['blue'], p['navy']])
    norm = Normalize(0, np.nanmax(m.values))
    fig = dc.figure(name)
    ax = fig.add_axes([.18, .22, .43, .65])
    for i in range(10):
        for j in range(5):
            v = m.iloc[i, j]
            if pd.isna(v):
                continue
            rgb = cmap(norm(max(0, v)))
            ax.add_patch(Rectangle((j - .5, i - .5), 1, 1, facecolor=rgb, edgecolor='#FFFFFF', lw=1.5, gid=f'cell-{i}-{j}'))
            lum = np.dot(rgb[:3], [.2126, .7152, .0722])
            ax.text(j, i, '0.0' if round(v, 1) == 0 else f'{v:.1f}'.replace('-', '−'), ha='center', va='center',
                    fontsize=dc.pt(24), color='#FFFFFF' if lum < .55 else dc.INK)
    ax.set(xlim=(-.5, 4.5), ylim=(9.5, -.5))
    ax.set_yticks(range(10), [s.title() for s in order])
    ax.set_xticks(range(5), ['00–07', '07–10', '10–17', '17–20', '20–24'])
    ax.tick_params(pad=10)
    ax.xaxis.tick_top()
    ax.set_xlabel('Weekday time band · NEA rain forecast issued', labelpad=12)
    ax.xaxis.set_label_position('top')
    for spine in ax.spines.values():
        spine.set_visible(False)
    rows = list(order)
    callouts = [
        ('CHANGI', ['00-07'], 'Changi 00–07', '{a} fewer per half-hour ({p})'),
        ('DOWNTOWN CORE', ['00-07'], 'Downtown Core 00–07', '{a} fewer ({p})'),
        ('BUKIT MERAH', ['17-20', '20-24'], 'Bukit Merah 17–20, 20–24', '{a} fewer ({p})'),
    ]
    tx = 4.9
    ty = [0.2, 2.6, 5.0]
    for k, (area, cols, title, fmt) in enumerate(callouts):
        i = rows.index(area)
        js = [bands.index(c) for c in cols]
        a = ' and '.join(f'{m.loc[area, c]:.1f}' for c in cols)
        pcs = sorted({f'{pc.loc[area, c]:.0f}' for c in cols})
        assert len(pcs) == 1, (area, pcs)
        text = fmt.format(a=a, p=dc.pct(float(pcs[0]), 0))
        ax.add_patch(Rectangle((min(js) - .47, i - .47), len(js) - .06, .94, fill=False, edgecolor=p['yellow'],
                               lw=3.2, zorder=5, gid=f'callout-box-{k}', clip_on=False))
        bx, by = min(js) - .47, i - .47
        ax.scatter([bx], [by], s=420, color=p['navy'], edgecolor='#FFFFFF', linewidth=1.5, zorder=7, clip_on=False,
                   gid=f'callout-badge-{k}')
        dc.label(ax, bx, by, str(k + 1), '#FFFFFF', size=18, ha='center', va='center', weight=600, zorder=8,
                 clip_on=False).set_gid(f'callout-num-{k}')
        ax.scatter([tx + .14], [ty[k]], s=420, color=p['navy'], zorder=7, clip_on=False, gid=f'callout-keybadge-{k}')
        dc.label(ax, tx + .14, ty[k], str(k + 1), '#FFFFFF', size=18, ha='center', va='center', weight=600, zorder=8,
                 clip_on=False).set_gid(f'callout-keynum-{k}')
        dc.label(ax, tx + .38, ty[k], title, p['navy'], size=22, va='center', weight=600, clip_on=False).set_gid(f'callout-title-{k}')
        dc.label(ax, tx + .38, ty[k] + .72, text, dc.RED, size=24, va='center', weight=500,
                 clip_on=False).set_gid(f'callout-text-{k}')
    dc.label(ax, tx, 9.3, 'Negative = more taxis than usual.', dc.MUTED, size=22, va='center', clip_on=False)
    dc.colorbar(fig, [.19, .115, .41, .022], cmap, norm, 'Fewer taxis per half-hour', ticks=[0, 10, 20, 30])
    dc.save(fig, name)


def main():
    PRESENT.mkdir(parents=True, exist_ok=True)
    factors('deck', DECK, 'deck_factors', (1100, 560))
    factors('present', PRESENT, 'present_factors', (1180, 700))
    event(PRESENT, (1180, 640))
    places(PRESENT, (1180, 690))
    planning(PRESENT, (1200, 760))
    for rel, digest in dc.AUDIT['inputs'].items():
        assert dc.sha(dc.ROOT / rel) == digest, f'Frozen input changed: {rel}'
    (PRESENT / 'meta.json').write_text(json.dumps(META, indent=1) + '\n')
    (PRESENT / 'audit.json').write_text(json.dumps(dc.AUDIT, indent=2) + '\n')
    print('deck_factors + 4 presentation charts; every glyph uses registered Poppins; input hashes unchanged.')


if __name__ == '__main__':
    main()
