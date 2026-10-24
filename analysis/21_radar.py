"""Separately registered step 21: paired radar/gauge rainfall associations, never replacements for frozen results.

Usage: python -m analysis.21_radar --part fit|chart [--dry-threshold 0|0.1] [--models main central approach event]
The only taxi panels read are 2022-2024; every paired model uses exactly the same observations.
"""
from __future__ import annotations

import argparse
import gc
import importlib
from pathlib import Path
import time

import numpy as np
import pandas as pd

if __package__ in (None, ''):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.common import BLUE, ORANGE, MUTED, rain_band, save, style
from analysis.fepois_hd import fepois, pct
from analysis.prep_radar import START, END, TABLES

E = importlib.import_module('analysis.03_effects')
REGS = ['light', 'moderate', 'heavy', 'mmh_lag1', 'mmh_lag2']
ROOT = Path('data/interim/radar_models')


def load():
    parts = []
    for year in (2022, 2023, 2024):
        cols = ['ts', 'cell', 'vacant', 'rain_band', 'mmh', 'mmh_lag1', 'mmh_lag2', 'how', 'month', 'ym',
                'regime_id', 'drop_main', 'rain_ring', 'rain_2km']
        p = pd.read_parquet(f'data/interim/panel30_{year}.parquet', columns=cols,
                            filters=[('ts', '>=', START - pd.Timedelta(days=1)), ('ts', '<=', END)])
        p = p.rename(columns={c: f'gauge_{c}' for c in ['mmh', 'mmh_lag1', 'mmh_lag2', 'rain_ring', 'rain_2km']})
        for kind, prefix in [('cell', 'radar'), ('ring', 'radar_ring'), ('near', 'radar_near')]:
            cols = ['ts', 'cell', 'mmh', 'mmh_lag1', 'mmh_lag2'] if kind == 'cell' else ['ts', 'cell', 'mmh']
            q = pd.read_parquet(f'data/interim/radar_{kind}_{year}.parquet', columns=cols)
            q = q.rename(columns={c: f'{prefix}_{c}' for c in cols if c not in ['ts', 'cell']})
            p = p.merge(q, on=['ts', 'cell'], how='left', validate='one_to_one')
        parts.append(p)
    p = pd.concat(parts, ignore_index=True).sort_values(['ts', 'cell']).reset_index(drop=True)
    c = pd.read_csv(TABLES / 'cell_characteristics.csv').set_index('cell')
    p['central_area'] = p.cell.map(c.central_area).astype(bool)
    cols = [f'{s}_{v}' for s in ['gauge', 'radar'] for v in ['mmh', 'mmh_lag1', 'mmh_lag2']]
    cols += ['gauge_rain_ring', 'gauge_rain_2km', 'radar_ring_mmh', 'radar_near_mmh']
    finite = np.isfinite(p[cols]).all(axis=1)
    in_scope = (p.ts >= START) & (p.ts <= END)
    p['paired_sample'] = in_scope & ~p.drop_main & (p.rain_band >= 0) & finite
    a = [{'stage': 'taxi panel within dates', 'rows': int(in_scope.sum()),
          'snapshots': p.loc[in_scope, 'ts'].nunique(), 'cells': p.loc[in_scope, 'cell'].nunique()},
         {'stage': 'frozen main exclusions removed', 'rows': int((in_scope & ~p.drop_main).sum())},
         {'stage': 'paired finite measurements and main exclusions', 'rows': int(p.paired_sample.sum()),
          'snapshots': p.loc[p.paired_sample, 'ts'].nunique(), 'cells': p.loc[p.paired_sample, 'cell'].nunique()},
         {'stage': 'otherwise-main rows removed for measurement support',
          'rows': int((in_scope & ~p.drop_main & ~finite).sum())}]
    pd.DataFrame(a).to_csv(TABLES / 'radar_sample.csv', index=False)
    assert p.loc[p.paired_sample, 'ts'].min() >= START and p.ts.max() <= END
    return p


def source_frame(p, source, threshold):
    q = p[['ts', 'cell']].copy()
    for c in ['mmh', 'mmh_lag1', 'mmh_lag2']:
        v = p[f'{source}_{c}'].values.copy()
        v[v <= threshold] = 0
        q[c] = v
    q['rain_band'] = rain_band(q.mmh)
    return q


def fit_one(p, X, names, source, model, threshold, fes):
    t0 = time.time()
    day = p.ts.values.astype('datetime64[D]')
    r = fepois(p.vacant.values, X, names, fes, day, xt_dtype='float32')
    vcov = r.attrs['vcov'].copy()
    n, g, it = r.attrs['n'], r.attrs['clusters'], r.attrs['iterations']
    r = pct(r).reset_index(names='term')
    r.attrs = {}
    r['source'], r['model'], r['dry_threshold_mmh'] = source, model, threshold
    r['n'], r['clusters'], r['iterations'] = n, g, it
    if model.endswith('_abs') or model == 'abs':
        # A stated count scale, not an estimate of demand or of realised lost trips.
        r['change_per_10_expected_taxis'] = r.pct / 10
        r['change_per_10_expected_lo'] = r.pct_lo / 10
        r['change_per_10_expected_hi'] = r.pct_hi / 10
    vcov.to_csv(ROOT / f'vcov_{source}_{model}_{threshold:g}.csv')
    print(source, model, threshold, 'n', n, 'seconds', round(time.time() - t0), flush=True)
    return r, vcov


def contrast(r, V, terms, label):
    d = r.set_index('term')
    b = float(d.loc[terms, 'coef'].sum())
    se = float(np.sqrt(V.loc[terms, terms].to_numpy().sum()))
    return {'group': label, 'coef': b, 'se': se, 'pct': 100 * np.expm1(b),
            'pct_lo': 100 * np.expm1(b - 1.96 * se), 'pct_hi': 100 * np.expm1(b + 1.96 * se),
            'change_per_10_expected_taxis': 10 * np.expm1(b)}


def fit(threshold, models):
    ROOT.mkdir(exist_ok=True)
    full = load()
    keep = full.paired_sample.values
    p = full[keep].reset_index(drop=True)
    fe_abs = [p.cell.values, p.how.values.astype('int32') * 100 + p.month.values,
              p.ym.values.astype('int64') * 100 + p.regime_id.values]
    fe_share = [p.cell.values, p.ts.values]
    all_rows, contrasts, event_rows, freq = [], [], [], []
    for source in ['gauge', 'radar']:
        qfull = source_frame(full, source, threshold)
        q = qfull[keep].reset_index(drop=True)
        X = np.column_stack([q.rain_band == b for b in (1, 2, 3)] + [q.mmh_lag1, q.mmh_lag2]).astype('float32')
        for b in range(4):
            m = q.rain_band.values == b
            freq.append({'source': source, 'dry_threshold_mmh': threshold, 'rain_band': b, 'rows': int(m.sum()),
                         'mean_vacant': float(p.loc[m, 'vacant'].mean()), 'mean_mmh': float(q.loc[m, 'mmh'].mean())})
        if 'main' in models:
            for model, fes in [('abs', fe_abs), ('share', fe_share)]:
                r, V = fit_one(p, X, REGS, source, model, threshold, fes)
                all_rows.append(r)
        if 'central' in models:
            xx = np.column_stack([X, (q.rain_band.values == 3) & p.central_area.values]).astype('float32')
            for model, fes in [('central_abs', fe_abs)]:
                r, V = fit_one(p, xx, REGS + ['heavy_x_central'], source, model, threshold, fes)
                all_rows.append(r)
                for label, terms in [('outside Central Area', ['heavy']), ('Central Area', ['heavy', 'heavy_x_central'])]:
                    contrasts.append({**contrast(r, V, terms, label), 'source': source, 'model': model,
                                      'dry_threshold_mmh': threshold, 'n': int(r.n.iloc[0])})
        if 'approach' in models:
            own_dry = (q.mmh.values == 0) & (q.mmh_lag1.values == 0) & (q.mmh_lag2.values == 0)
            ring = p['gauge_rain_ring' if source == 'gauge' else 'radar_ring_mmh'].values
            near = p['gauge_rain_2km' if source == 'gauge' else 'radar_near_mmh'].values
            rb, nb = rain_band(np.where(ring <= threshold, 0, ring)), rain_band(np.where(near <= threshold, 0, near))
            cols = [own_dry & (rb == b) for b in (1, 2, 3)] + [own_dry & (nb == b) for b in (1, 2, 3)]
            names = REGS + [f'ring_{b}_owndry' for b in ('light', 'moderate', 'heavy')] + \
                [f'near_{b}_owndry' for b in ('light', 'moderate', 'heavy')]
            xx = np.column_stack([X] + cols).astype('float32')
            for model, fes in [('approach_abs', fe_abs)]:
                r, V = fit_one(p, xx, names, source, model, threshold, fes)
                all_rows.append(r)
        if 'event' in models:
            # Source-specific onsets on the full calendar grid; the outcome sample remains identical.
            evt, info = E.onsets(qfull)
            evt = evt[keep]
            xx = np.column_stack([evt == b for b in E.EVT_BINS]).astype('float32')
            names = [f'evt_{b}' for b in E.EVT_BINS]
            for model, fes in [('event_abs', fe_abs)]:
                r, V = fit_one(p, xx, names, source, model, threshold, fes)
                d = r.set_index('term')
                for b, name in zip(E.EVT_BINS, names):
                    coef = float(d.loc[name, 'coef'] - d.loc['evt_-30', 'coef'])
                    se = np.sqrt(max(0, V.loc[name, name] + V.loc['evt_-30', 'evt_-30'] - 2 * V.loc[name, 'evt_-30']))
                    event_rows.append({'source': source, 'model': model, 'dry_threshold_mmh': threshold, 'event_min': b,
                                       'coef': coef, 'se': se, 'pct': 100 * np.expm1(coef),
                                       'pct_lo': 100 * np.expm1(coef - 1.96 * se),
                                       'pct_hi': 100 * np.expm1(coef + 1.96 * se), 'n': int(r.n.iloc[0]),
                                       'event_rows': int((evt == b).sum()), 'onsets_full_grid': info['onsets']})
            del evt
        del X, qfull, q
        gc.collect()
    # Per-part files prevent a later invocation from silently overwriting another model's results.
    label = '_'.join(models)
    if all_rows:
        pd.concat(all_rows, ignore_index=True).to_csv(ROOT / f'effects_{threshold:g}_{label}.csv', index=False)
    if contrasts:
        pd.DataFrame(contrasts).to_csv(ROOT / f'central_{threshold:g}_{label}.csv', index=False)
    if event_rows:
        pd.DataFrame(event_rows).to_csv(ROOT / f'event_{threshold:g}_{label}.csv', index=False)
    pd.DataFrame(freq).to_csv(ROOT / f'frequency_{threshold:g}_{label}.csv', index=False)
    for kind in ['effects', 'central', 'event', 'frequency']:
        paths = sorted(ROOT.glob(f'{kind}_*.csv'))
        if paths:
            d = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)
            keys = [c for c in ['source', 'model', 'dry_threshold_mmh', 'term', 'group', 'event_min', 'rain_band'] if c in d]
            d.drop_duplicates(keys, keep='last').to_csv(TABLES / f'radar_{kind}.csv', index=False, float_format='%.7f')


def chart():
    import matplotlib.pyplot as plt
    style()
    e = pd.read_csv(TABLES / 'radar_effects.csv')
    c = pd.read_csv(TABLES / 'radar_central.csv')
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.5), sharex=True)
    for ax, model, title in zip(axes[:2], ['abs', 'share'], ['Absolute vacant taxis', 'Share of citywide vacant taxis']):
        for source, offset, color in [('gauge', -.1, BLUE), ('radar', .1, ORANGE)]:
            q = e[(e.source == source) & (e.model == model) & (e.dry_threshold_mmh == 0)].set_index('term').loc[REGS[:3]]
            y = np.arange(3)[::-1] + offset
            ax.errorbar(q.pct, y, xerr=[q.pct - q.pct_lo, q.pct_hi - q.pct], fmt='o', color=color, capsize=3, label=source)
        ax.set_yticks(np.arange(3)[::-1], ['Light', 'Moderate', 'Heavy'])
        ax.set_title(title)
    for source, offset, color in [('gauge', -.1, BLUE), ('radar', .1, ORANGE)]:
        q = c[(c.source == source) & (c.model == 'central_abs') & (c.dry_threshold_mmh == 0)].set_index('group').loc[
            ['outside Central Area', 'Central Area']]
        axes[2].errorbar(q.pct, np.arange(2)[::-1] + offset,
                         xerr=[q.pct - q.pct_lo, q.pct_hi - q.pct], fmt='o', color=color, capsize=3, label=source)
    axes[2].set_yticks([1, 0], ['Outside Central Area', 'Central Area'])
    axes[2].set_title('Heavy rain: Central Area interaction')
    for ax in axes:
        ax.axvline(0, color=MUTED, lw=.8)
        ax.set_xlabel('Associated change (%)')
    axes[0].legend()
    fig.suptitle('Radar rainfall measurement check — identical sample, Apr 2022–Dec 2024', x=.01, ha='left')
    fig.tight_layout(rect=(0, .09, 1, .94))
    save(fig, 'radar_measurement_check', 'Sources: data.gov.sg/NEA; Zhuang et al. (2026), Zenodo 19642566, CC BY 4.0. '
         '95% day-clustered CIs.\nRadar–gauge merged product; agreement is not independent validation. '
         'Frozen gauge headline results unchanged.\nAbsolute-model -10% = 1 fewer vacant taxi per 10 expected; '
         'share changes are not count gains.')
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--part', required=True, choices=['fit', 'chart'])
    parser.add_argument('--dry-threshold', type=float, choices=[0, .1], default=0)
    parser.add_argument('--models', nargs='+', choices=['main', 'central', 'approach', 'event'],
                        default=['main', 'central', 'approach', 'event'])
    args = parser.parse_args()
    if args.part == 'fit':
        fit(args.dry_threshold, args.models)
    else:
        chart()


if __name__ == '__main__':
    main()
