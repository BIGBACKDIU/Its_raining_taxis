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
DECK_COLOURS = {k: getattr(dc, k) for k in ['NAVY', 'BLUE', 'LIGHT', 'PALE', 'RED', 'INK', 'MUTED', 'GRID', 'NO_DATA', 'BG', 'WHITE']}
PALETTES = {
    'deck': {'navy': dc.NAVY, 'blue': dc.BLUE, 'light': dc.LIGHT, 'pale': dc.PALE, 'bg': dc.BG, 'accent': dc.NAVY,
             'colours': DECK_COLOURS},
    # Decision 175: calm presentation palette (slate/steel data, red only for fewer taxis).
    'present': {'navy': '#2E4A6B', 'blue': '#4F7CAC', 'light': '#A9C0DA', 'pale': '#E6ECF3', 'bg': 'none',
                'accent': '#0B1F3A',
                'colours': {'NAVY': '#2E4A6B', 'BLUE': '#4F7CAC', 'LIGHT': '#A9C0DA', 'PALE': '#E6ECF3',
                            'RED': '#B5473A', 'INK': '#1A2433', 'MUTED': '#5B6676', 'GRID': '#DDE3EA',
                            'NO_DATA': '#F1F3F6', 'BG': '#FFFFFF', 'WHITE': '#FFFFFF'}},
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
    for key, value in p['colours'].items():
        setattr(dc, key, value)
    dc.SEQUENTIAL = LinearSegmentedColormap.from_list('deck_blue', [dc.PALE, dc.LIGHT, dc.BLUE, dc.NAVY])
    dc.DIVERGING = LinearSegmentedColormap.from_list('deck_change', [dc.RED, dc.WHITE, dc.BLUE], N=257)
    dc.DIVERGING.set_bad(dc.NO_DATA)
    dc.OUT = out
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
        ax.axvspan(start, end, color=p['pale'] if i % 2 == 0 else '#F4F6F9', zorder=0, lw=0)
        dc.label(ax, (start + end) / 2, 2.2, text, dc.MUTED, size=22, ha='center', va='center')
    ax.fill_between(t.event_min, t.pct_lo, t.pct_hi, color=p['light'], alpha=.55, lw=0, gid='event-band')
    ax.plot(t.event_min, t.pct, color=p['navy'], lw=2.6, marker='o', ms=6, gid='event-line')
    ax.axvline(0, color=p['navy'], ls='--', lw=1.3)
    dc.label(ax, 0, 3.12, 'Rain starts', p['accent'], size=22, ha='center', va='bottom', weight=600, clip_on=False)
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
        ax.add_patch(Rectangle((min(js) - .47, i - .47), len(js) - .06, .94, fill=False, edgecolor=p['accent'],
                               lw=2.2, zorder=5, gid=f'callout-box-{k}', clip_on=False))
        bx, by = min(js) - .47, i - .47
        ax.scatter([bx], [by], s=360, color='#FFFFFF', edgecolor=p['accent'], linewidth=1.4, zorder=7, clip_on=False,
                   gid=f'callout-badge-{k}')
        dc.label(ax, bx, by, str(k + 1), p['accent'], size=18, ha='center', va='center', weight=600, zorder=8,
                 clip_on=False).set_gid(f'callout-num-{k}')
        ax.scatter([tx + .14], [ty[k]], s=360, color='#FFFFFF', edgecolor=p['accent'], linewidth=1.4, zorder=7, clip_on=False, gid=f'callout-keybadge-{k}')
        dc.label(ax, tx + .14, ty[k], str(k + 1), p['accent'], size=18, ha='center', va='center', weight=600, zorder=8,
                 clip_on=False).set_gid(f'callout-keynum-{k}')
        dc.label(ax, tx + .38, ty[k], title, p['accent'], size=22, va='center', weight=600, clip_on=False).set_gid(f'callout-title-{k}')
        dc.label(ax, tx + .38, ty[k] + .72, text, dc.RED, size=24, va='center', weight=500,
                 clip_on=False).set_gid(f'callout-text-{k}')
    dc.label(ax, tx, 9.3, 'Negative = more taxis than usual.', dc.MUTED, size=22, va='center', clip_on=False)
    dc.colorbar(fig, [.19, .115, .41, .022], cmap, norm, 'Fewer taxis per half-hour', ticks=[0, 10, 20, 30])
    dc.save(fig, name)


def regimes(out, size):
    use('present', out)
    name = 'present_regimes'
    t = dc.read('feed_regimes')
    t['start'], t['end'] = pd.to_datetime(t.start), pd.to_datetime(t.end) + pd.Timedelta(days=1)
    dc.SIZES[name] = size
    dc.record(name, t)
    fig = dc.figure(name)
    ax = dc.axes(fig, [.08, .2, .9, .72])
    ax.axvspan(pd.Timestamp('2025-10-01'), pd.Timestamp('2026-10-01'), color=dc.PALE, lw=0, zorder=0)
    dc.label(ax, pd.Timestamp('2026-04-01'), 2.12, 'Test year', dc.MUTED, size=22, ha='center')
    ax.axhline(1, color=dc.MUTED, lw=.8)
    for r in t.itertuples():
        spell = r.kind == 'spell'
        ax.plot([r.start, r.end], [r.level_ratio] * 2, color=dc.RED if spell else dc.NAVY, lw=4,
                solid_capstyle='butt')
    ax.set(ylim=(0.3, 2.3), ylabel='Feed level vs typical (×)')
    ax.set_yticks([.5, 1, 1.5, 2], ['0.5', '1.0', '1.5', '2.0'])
    years = pd.date_range('2022-01-01', '2026-01-01', freq='YS')
    ax.set_xticks(years, [str(d.year) for d in years])
    ax.set_xlim(pd.Timestamp('2021-10-01'), pd.Timestamp('2026-10-01'))
    n_regimes, n_spells = int(t.loc[t.kind == 'regime', 'regime'].nunique()), int((t.kind == 'spell').sum())  # R06 spans two rows
    fig.text(.08, .045, f'{n_regimes} feed periods (slate) · {n_spells} short spells excluded (red)', fontsize=dc.pt(22), color=dc.MUTED)
    META[name] = {'regimes': n_regimes, 'spells': n_spells}
    dc.save(fig, name)


ROBUST_ORDER = ['3-gauge mean rain', 'rain window lagged 15 min', 'robustness sample (outage days back in)',
                'with COVID months (from Oct 2021)', 'FY2022 only', 'FY2023 only', 'FY2024 only', '1 km cells (FY2024)',
                '500 m cells (FY2024)', '30-minute snapshots (Oct 24-Mar 25)', '15-minute snapshots (Oct 24-Mar 25)']


def robustness(out, size):
    use('present', out)
    name = 'present_robustness'
    t = dc.read('effects_robust').query("model=='abs' and term=='heavy'").copy()
    t['variant'] = t.variant.str.replace('\n', ' ', regex=False).str.split().str.join(' ')
    main = dc.read('effects_main').query("model=='abs' and term=='heavy'").iloc[0]
    order = [v for v in ROBUST_ORDER if v in set(t.variant)] + sorted(set(t.variant) - set(ROBUST_ORDER))
    t = t.set_index('variant').loc[order].reset_index()
    dc.SIZES[name] = size
    dc.record(name, t)
    fig = dc.figure(name)
    ax = dc.axes(fig, [.47, .13, .46, .83], grid=False)
    ax.xaxis.grid(True, color=dc.GRID, linewidth=.7)
    ax.axvline(main.pct, color=dc.MUTED, ls=(0, (1.5, 3)), lw=1.6)
    n = len(t)
    for i, r in enumerate(t.itertuples()):
        y = n - 1 - i
        dc.error(ax, r.pct, y, r.pct_lo, r.pct_hi, dc.NAVY, horizontal=True, ms=8)
        dc.label(ax, r.pct_hi + .4, y, dc.pct(r.pct), dc.NAVY, size=22, va='center')
    dc.label(ax, main.pct, n - .35, f'Main estimate {dc.pct(main.pct)}', dc.MUTED, size=22, ha='center')
    short = {'robustness sample (outage days back in)': 'Outage days put back in',
             'with COVID months (from Oct 2021)': 'COVID months included',
             '30-minute snapshots (Oct 24-Mar 25)': '30-min snapshots (Oct 24–Mar 25)',
             '15-minute snapshots (Oct 24-Mar 25)': '15-min snapshots (Oct 24–Mar 25)'}
    show = [short.get(v, v.split(',')[0]) for v in t.variant]
    ax.set_yticks(range(n)[::-1], [v[0].upper() + v[1:] for v in show])
    ax.set(xlim=(-22, -2), ylim=(-.6, n), xlabel='Heavy rain vs dry · % vacant taxis')
    ax.set_xticks([-20, -15, -10, -5], ['−20%', '−15%', '−10%', '−5%'])
    dc.save(fig, name)


POLICY = [('all candidate cells (expected >= 4)', 'All candidate squares'),
          ('(a) policy as designed', 'Plan as designed'),
          ('(a) policy as designed, 19 cells with most taxis', 'Plan, 19 squares with most taxis'),
          ('(b) policy, weights = forecast risk', 'Plan weighted by forecast risk'),
          ('(c) restricted to cells with a staging point', 'Risk plan, staging points only'),
          ('(c) ... and reachable from a surplus cell within 60 min', 'Risk plan, reachable in 60 min'),
          ('(c) top-19 forecast ranking, no constraints', 'Top-19 forecast, no constraints')]


def policy(out, size):
    use('present', out)
    name = 'present_policy'
    t = dc.read('policy_diagnosis').query("split=='test'").set_index('variant').loc[[v for v, _ in POLICY]].reset_index()
    dc.SIZES[name] = size
    dc.record(name, t)
    fig = dc.figure(name)
    ax = dc.axes(fig, [.37, .16, .6, .8], grid=False)
    ax.xaxis.grid(True, color=dc.GRID, linewidth=.7)
    y = np.arange(len(t))[::-1]
    colours = [dc.LIGHT if i == 0 else dc.NAVY if i == 3 else dc.BLUE for i in range(len(t))]
    ax.barh(y, 100 * t.precision_issue_time, color=colours, height=.6, zorder=3)
    for yi, r in zip(y, t.itertuples()):
        dc.label(ax, 100 * r.precision_issue_time + .8, yi, f'{100 * r.precision_issue_time:.1f}% · {r.cells_per_decision:.1f} squares',
                 dc.INK, size=22, va='center')
    ax.set_yticks(y, [label for _, label in POLICY])
    ax.set(xlim=(0, 75), xlabel='Chosen squares that really run short (test year)')
    ax.set_xticks([0, 20, 40, 60], ['0', '20%', '40%', '60%'])
    dc.save(fig, name)


def main():
    PRESENT.mkdir(parents=True, exist_ok=True)
    factors('deck', DECK, 'deck_factors', (1100, 560))
    factors('present', PRESENT, 'present_factors', (1180, 700))
    event(PRESENT, (1180, 640))
    places(PRESENT, (1180, 690))
    planning(PRESENT, (1200, 760))
    regimes(PRESENT, (1500, 520))
    robustness(PRESENT, (1000, 680))
    policy(PRESENT, (1150, 600))
    # The deck's appendix charts, redrawn unchanged in the presentation palette (same saved inputs).
    use('present', PRESENT)
    for function in [dc.main_effects, dc.radar, dc.dose, dc.where, dc.island, dc.forecasting, dc.holdout]:
        use('present', PRESENT)
        function()
    for rel, digest in dc.AUDIT['inputs'].items():
        assert dc.sha(dc.ROOT / rel) == digest, f'Frozen input changed: {rel}'
    (PRESENT / 'meta.json').write_text(json.dumps(META, indent=1) + '\n')
    (PRESENT / 'audit.json').write_text(json.dumps(dc.AUDIT, indent=2) + '\n')
    print('deck_factors + presentation charts; every glyph uses registered Poppins; input hashes unchanged.')


if __name__ == '__main__':
    main()
