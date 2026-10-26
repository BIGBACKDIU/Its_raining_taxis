"""Render slide-card charts from frozen results. No estimation, tuning or scoring.

Run: .venv/bin/python -m analysis.deck_charts
Pixel units below refer to the requested display size; PNG output is exactly 2x.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager, ft2font
from matplotlib.collections import PatchCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm
from matplotlib.patches import Polygon, Rectangle
from matplotlib.text import Text
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
from PIL import Image

from pipeline.grid import to_xy

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / 'outputs/tables'
OUT = ROOT / 'outputs/figures/deck'
FONTS = ROOT / 'assets/fonts/poppins'
NAVY, BLUE, LIGHT, PALE, RED = '#14295B', '#2C5EAA', '#8FB8F2', '#DCE6F4', '#C0453C'
INK, MUTED, GRID, NO_DATA, BG, WHITE = '#14203A', '#5A6683', '#E4EAF4', '#F2F4F7', '#FBFCFE', '#FFFFFF'
SEQUENTIAL = LinearSegmentedColormap.from_list('deck_blue', [PALE, LIGHT, BLUE, NAVY])
DIVERGING = LinearSegmentedColormap.from_list('deck_change', [RED, WHITE, BLUE], N=257)
DIVERGING.set_bad(NO_DATA)
CHANGE = TwoSlopeNorm(vmin=-40, vcenter=0, vmax=40)
SIZES = {
    'deck_effects_main': (1016, 490), 'deck_radar_check': (1146, 440),
    'deck_storm_peak': (1560, 516), 'deck_event_timeline': (1040, 536),
    'deck_dose': (1016, 375), 'deck_where_map': (1520, 547),
    'deck_places_bar': (1010, 552), 'deck_islandwide_map': (889, 552),
    'deck_planning_heatmap': (772, 560), 'deck_forecast_bars': (1300, 487),
    'deck_holdout_gain': (1100, 420),
}
AUDIT = {'inputs': {}, 'charts': {}, 'fonts': {}, 'notes': []}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name):
    path = TABLES / (name + '.csv')
    AUDIT['inputs'][str(path.relative_to(ROOT))] = sha(path)
    return pd.read_csv(path)


def record(name, data):
    """Save exact, unrounded plotted rows alongside the PNGs for numeric review."""
    (OUT / 'data').mkdir(exist_ok=True)
    data.to_csv(OUT / 'data' / (name + '.csv'), index=False, float_format='%.17g')


def pt(px):
    return px * 72 / 100


def fonts():
    weights = {'Regular': 'normal', 'Medium': 500, 'SemiBold': 600}
    for name, weight in weights.items():
        path = FONTS / f'Poppins-{name}.ttf'
        if not path.exists():
            raise RuntimeError(f'Missing required Poppins font: {path}')
        font_manager.fontManager.addfont(path)
        prop = font_manager.FontProperties(family='Poppins', weight=weight)
        resolved = Path(font_manager.findfont(prop, fallback_to_default=False)).resolve()
        if resolved != path.resolve():
            raise RuntimeError(f'Poppins {name} resolves to {resolved}, expected {path}')
        AUDIT['fonts'][name] = {'file': str(path.relative_to(ROOT)), 'sha256': sha(path)}
    plt.rcParams.update({
        'font.family': 'Poppins', 'font.size': pt(22), 'font.weight': 'normal',
        'axes.labelsize': pt(22), 'xtick.labelsize': pt(22), 'ytick.labelsize': pt(22),
        'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': MUTED, 'ytick.color': MUTED,
        'axes.edgecolor': GRID, 'axes.facecolor': BG, 'figure.facecolor': BG,
        'savefig.facecolor': BG, 'axes.spines.top': False, 'axes.spines.right': False,
        'axes.linewidth': .8, 'xtick.major.size': 0, 'ytick.major.size': 0,
        'axes.unicode_minus': True, 'figure.dpi': 100, 'savefig.dpi': 200,
    })


def figure(name):
    w, h = SIZES[name]
    return plt.figure(figsize=(w / 100, h / 100), dpi=100)


def axes(fig, rect, grid=True):
    ax = fig.add_axes(rect)
    ax.set_axisbelow(True)
    if grid:
        ax.yaxis.grid(True, color=GRID, linewidth=.7)
    ax.spines['left'].set_visible(False)
    ax.tick_params(pad=10)
    return ax


def label(ax, x, y, text, color=INK, size=24, **kwargs):
    return ax.text(x, y, text, color=color, fontsize=pt(size), **kwargs)


def pct(value, decimals=1):
    return f'{value:+.{decimals}f}%'.replace('-', '−')


def error(ax, x, y, lo, hi, color=NAVY, horizontal=False, marker='o', ms=8):
    extent = [[x - lo], [hi - x]] if horizontal else [[y - lo], [hi - y]]
    ax.errorbar(x, y, **{'xerr' if horizontal else 'yerr': extent}, fmt=marker,
                color=color, ecolor=color, elinewidth=1.6, capsize=4, markersize=ms, zorder=4)


def save(fig, name):
    if any(ax.get_title() for ax in fig.axes):
        raise RuntimeError(f'{name}: chart title present')
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    font_files, bounds = set(), []
    for text in fig.findobj(Text):
        if not text.get_visible() or not text.get_text():
            continue
        path = Path(font_manager.findfont(text.get_fontproperties(), fallback_to_default=False)).resolve()
        if path.parent != FONTS.resolve() or not path.name.startswith('Poppins-'):
            raise RuntimeError(f'{name}: non-Poppins text {text.get_text()!r} uses {path}')
        font_files.add(path.name)
        cmap = ft2font.FT2Font(str(path)).get_charmap()
        missing = [c for c in text.get_text() if not c.isspace() and ord(c) not in cmap]
        if missing:
            raise RuntimeError(f'{name}: Poppins lacks glyphs {missing!r}')
        b = text.get_window_extent(renderer)
        if b.x0 < -1 or b.y0 < -1 or b.x1 > fig.bbox.width + 1 or b.y1 > fig.bbox.height + 1:
            bounds.append({'text': text.get_text(), 'bbox': list(b.bounds)})
    if bounds:
        raise RuntimeError(f'{name}: text outside image: {bounds}')
    path = OUT / (name + '.png')
    fig.savefig(path, dpi=200, bbox_inches=None, pad_inches=0)
    with plt.rc_context({'svg.fonttype':'none'}):
        fig.savefig(OUT / (name + '.svg'), format='svg', bbox_inches=None, pad_inches=0)
    expected = tuple(2 * n for n in SIZES[name])
    with Image.open(path) as image:
        if image.size != expected:
            raise RuntimeError(f'{name}: {image.size}, expected {expected}')
    AUDIT['charts'][name] = {'display_pixels': SIZES[name], 'png_pixels': expected,
                           'fonts_used': sorted(font_files), 'sha256': sha(path)}
    plt.close(fig)


def main_effects():
    name = 'deck_effects_main'
    t = read('effects_main').query("model in ['abs', 'share'] and term in ['light','moderate','heavy']")
    record(name, t)
    expected = {'abs': [-7.7, -10.8, -12.9], 'share': [-1.9, -4.5, -5.7]}
    for model in expected:
        assert t[t.model == model].set_index('term').loc[['light','moderate','heavy'], 'pct'].round(1).tolist() == expected[model]
    fig = figure(name)
    ax = axes(fig, [.16, .19, .79, .72])
    for i, term in enumerate(['light','moderate','heavy']):
        y = 2 - i
        for model, offset, color in [('abs', .14, NAVY), ('share', -.14, LIGHT)]:
            r = t[(t.term == term) & (t.model == model)].iloc[0]
            color = RED if term == 'heavy' and model == 'abs' else color
            error(ax, r.pct, y + offset, r.pct_lo, r.pct_hi, color, horizontal=True, ms=10)
            if model == 'abs':
                label(ax, r.pct_lo - .4, y + offset, pct(r.pct), color, ha='right', va='center')
            else:
                label(ax, r.pct_hi + .4, y + offset, pct(r.pct), BLUE, va='center')
    ax.set(xlim=(-18.5, 1), ylim=(-.6, 2.7), xlabel='% change vs dry')
    ax.set_yticks([2,1,0], ['Light','Moderate','Heavy'])
    ax.set_xticks([-15,-10,-5,0], ['−15%','−10%','−5%','0'])
    ax.axvline(0, color=MUTED, lw=.8)
    label(ax, -8.4, 2.6, 'Absolute', NAVY, size=22, ha='center')
    label(ax, -1.6, 2.6, 'Citywide share', BLUE, size=22, ha='center')
    save(fig, name)


def radar():
    name = 'deck_radar_check'
    t = read('radar_effects').query("model=='abs' and dry_threshold_mmh==0 and term in ['light','moderate','heavy']").copy()
    c = read('radar_central').query("group=='Central Area' and dry_threshold_mmh==0").copy()
    c['term'] = 'Central Area heavy'
    t = pd.concat([t, c], ignore_index=True)
    record(name, t)
    fig = figure(name)
    ax = axes(fig, [.23, .20, .74, .75])
    terms = ['light','moderate','heavy','Central Area heavy']
    for i, term in enumerate(terms):
        q = t[t.term == term].set_index('source')
        y = 3-i
        ax.plot([q.loc['gauge','pct'],q.loc['radar','pct']], [y+.12,y-.12], color=PALE, lw=3)
        for source, off, color in [('gauge',.12,NAVY),('radar',-.12,BLUE)]:
            r=q.loc[source]
            color=RED if source=='radar' and i==3 else color
            error(ax,r.pct,y+off,r.pct_lo,r.pct_hi,color,horizontal=True)
            x=r.pct_lo-.7 if source=='gauge' else r.pct_hi+.7
            label(ax,x,y+off,f'{source.title()} {pct(r.pct)}',color,ha='right' if source=='gauge' else 'left',va='center')
    ax.set(xlim=(-44,9),ylim=(-.65,3.55),xlabel='% vacant taxis vs dry · identical sample')
    ax.set_yticks(range(4), ['Central Area\nheavy','Heavy','Moderate','Light'])
    ax.set_xticks([-40,-30,-20,-10,0],['−40%','−30%','−20%','−10%','0'])
    ax.axvline(0,color=MUTED,lw=.8)
    save(fig,name)


def geography():
    names=read('names_cells')
    land=json.loads((ROOT/'data/static/sg_map.json').read_text())['land']
    return names,land


def map_axes(fig, rect, names, land):
    ax=fig.add_axes(rect)
    ax.set_aspect('equal');ax.set_axis_off()
    for ring in land:
        # sg_map stores polygon rings as point arrays.
        xy=np.asarray(ring)
        if xy.ndim!=2: raise RuntimeError('Unexpected coastline geometry')
        x,y=to_xy(xy[:,0],xy[:,1])
        ax.add_patch(Polygon(np.column_stack([x/1000,y/1000]),facecolor=GRID,edgecolor=GRID,lw=.3,zorder=0))
    patches=[]
    for cell in names.loc[names.land,'cell']:
        patches.append(Rectangle((cell//1000,cell%1000),1,1))
    ax.add_collection(PatchCollection(patches,facecolor=NO_DATA,edgecolor=BG,linewidth=.2,zorder=1))
    ax.set(xlim=(5,60),ylim=(6,36))
    return ax


def map_values(ax,t,column,cmap=DIVERGING,norm=CHANGE):
    patches,values=[],[]
    for r in t.itertuples():
        value=getattr(r,column)
        if not np.isfinite(value): continue
        patches.append(Rectangle((r.cell//1000,r.cell%1000),1,1));values.append(value)
    col=PatchCollection(patches,cmap=cmap,norm=norm,edgecolor=BG,linewidth=.25,zorder=2)
    col.set_array(np.array(values));ax.add_collection(col)
    return col


def colorbar(fig,rect,cmap=DIVERGING,norm=CHANGE,label_text='% vacant taxis vs normal',ticks=None):
    ax=fig.add_axes(rect)
    cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=ax,orientation='horizontal',ticks=ticks or [-40,-20,0,20,40])
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=pt(22),pad=5)
    cb.set_label(label_text,fontsize=pt(22),labelpad=8)
    return cb


def markers(ax,rows):
    """Spread crowded numbered circles with leaders; numbers still point at exact cells."""
    placed=[]
    for k,r in enumerate(rows.itertuples(),1):
        origin=np.array([r.cell//1000+.5,r.cell%1000+.5])
        candidates=[origin]
        for radius in [1.2,2.2,3.2,4.2]:
            for theta in np.linspace(0,2*np.pi,16,endpoint=False):
                candidates.append(origin+radius*np.array([np.cos(theta),np.sin(theta)]))
        point=next((p for p in candidates if all(np.linalg.norm(p-q)>2.3 for q in placed)),candidates[-1])
        placed.append(point)
        ax.plot([origin[0],point[0]],[origin[1],point[1]],color=NAVY,lw=.8,zorder=5)
        ax.scatter(*point,s=150,color=NAVY,zorder=6)
        label(ax,*point,str(k),WHITE,size=17,ha='center',va='center',zorder=7)


def place_name(r):
    # Compact names taken verbatim from existing geographical fields.
    aliases={48022:'Changi T3',48023:'Changi T1 / Jewel',33014:'Lau Pa Sat',34014:'Marina Bay Sands',
             32016:'Dhoby Ghaut',34017:'Lavender',33016:'Victoria',34016:'Nicoll',33015:'City Hall'}
    return aliases.get(int(r.cell),str(r.subzone).title().replace(' Subzone',''))


def key(fig, rect, rows, effect, count=None, size=20):
    ax=fig.add_axes(rect);ax.set_axis_off()
    n=len(rows)
    for i,r in enumerate(rows.itertuples()):
        y=1-(i+.35)/n
        ax.text(0,y,str(i+1),fontsize=pt(size),color=NAVY,weight=600,va='top',transform=ax.transAxes)
        ax.text(.09,y,place_name(r),fontsize=pt(size),color=INK,va='top',transform=ax.transAxes)
        value=getattr(r,effect)
        text=pct(value)
        if count:
            text+=f' · {getattr(r,count):+.2f} taxis'.replace('-', '−')
        ax.text(.09,y-.043,text,fontsize=pt(24),color=MUTED,va='top',transform=ax.transAxes)
    return ax


def storm():
    name='deck_storm_peak'
    panel=ROOT/'data/interim/panel30_2023.parquet'
    t=pd.read_parquet(panel,columns=['ts','cell','vacant','baseline','mmh'],filters=[('ts','==',pd.Timestamp('2023-07-20 09:30'))])
    assert len(t)==374 and t.cell.is_unique
    t['pct']=100*(t.vacant/t.baseline.clip(lower=1)-1)
    record(name,t)
    AUDIT['inputs'][str(panel.relative_to(ROOT))] = sha(panel)
    AUDIT['notes'].append('Storm snapshot has no existing CSV. Exported unchanged saved panel rows and the original 02_describe.py formula, without refitting or rescoring.')
    names,land=geography()
    fig=figure(name)
    context=read('rain_hit_top30_absolute').query('cell in [48022,33014,33015]').copy()
    if len(context)!=3: raise RuntimeError('Missing frozen map context cells')
    for i,(col,cmap,norm) in enumerate([('mmh',SEQUENTIAL,Normalize(0,60)),('pct',DIVERGING,CHANGE)]):
        ax=map_axes(fig,[.008+i*.5,.26,.345,.67],names,land)
        map_values(ax,t,col,cmap,norm);markers(ax,context)
        ka=fig.add_axes([.36+i*.5,.29,.135,.60]);ka.set_axis_off()
        for k,r in enumerate(context.itertuples()):
            row=t[t.cell==r.cell].iloc[0];y=.91-k*.31
            ka.text(0,y,f'{k+1}  {place_name(r)}',fontsize=pt(22),color=NAVY,weight=500,va='top')
            text=f'{row.mmh:.1f} mm/h' if i==0 else pct(row.pct)
            ka.text(0,y-.09,text,fontsize=pt(24),color=INK,va='top')
            if i: ka.text(0,y-.18,f'{row.vacant:g} / {row.baseline:.1f} taxis',fontsize=pt(24),color=MUTED,va='top')
    cb=colorbar(fig,[.065,.16,.37,.023],SEQUENTIAL,Normalize(0,60),'Rain in previous 30 min (mm/h)',[0,10,30,60])
    cb.ax.set_xticklabels(['0','10','30','≥60'])
    colorbar(fig,[.565,.16,.37,.023])
    save(fig,name)


def event():
    name='deck_event_timeline'
    t=read('effects_event_study').query("model=='event_abs'")
    a=read('effects_approach').query("model=='abs' and term=='ring_heavier_owndry'").iloc[0]
    record(name,pd.concat([t,pd.DataFrame([a])],ignore_index=True))
    assert round(a.pct)==-7
    fig=figure(name);ax=axes(fig,[.095,.30,.87,.57])
    phases=[(-60,0,'Before: act\non forecast'),(0,60,'First hour:\ndeepest'),(60,150,'Recovery'),(150,180,'Back within\nnoise')]
    for i,(start,end,text) in enumerate(phases):
        ax.axvspan(start,end,color=PALE if i%2==0 else GRID,alpha=.65,zorder=0)
        label(ax,(start+end)/2,2.9,text,size=22,ha='center',va='bottom')
    ax.fill_between(t.event_min,t.pct_lo,t.pct_hi,color=LIGHT,alpha=.55,lw=0)
    ax.plot(t.event_min,t.pct,color=NAVY,lw=2.2,marker='o',ms=5)
    ax.axvline(0,color=NAVY,ls='--',lw=1.2)
    label(ax,-2,-8.7,'Rain starts',NAVY,size=22,ha='right',va='bottom')
    ax.axhline(0,color=MUTED,lw=.8)
    ax.set(xlim=(-60,180),ylim=(-9,3),xlabel='Minutes from rain onset',ylabel='% vs −30 min')
    ax.set_xticks([-60,0,60,120,180]);ax.set_yticks([-8,-4,0],['−8%','−4%','0'])
    lowest=t.loc[t.pct.idxmin()]
    label(ax,lowest.event_min,lowest.pct_lo-.5,pct(lowest.pct),NAVY,ha='center',va='top')
    fig.text(.095,.055,'−7% already when rain is 2–5 km away (separate model)',color=RED,fontsize=pt(24),weight=500)
    AUDIT['notes'].append('Event recovery shading starts at +150 min: first saved CI including zero and all later CIs include zero. Before/onset phases are descriptive slide annotations. Approaching-rain callout rounds −7.3384034% to −7%; it is not an event-study point.')
    save(fig,name)


def dose():
    name='deck_dose';curve=read('dose_spline_curve');t=read('dose_duration_hangover')
    record(name,pd.concat([curve,t],ignore_index=True))
    fig=figure(name)
    for j in range(3):
        ax=axes(fig,[.075+j*.325,.31,.265,.56]);ax.axhline(0,color=MUTED,lw=.7)
        ax.set_ylim(-24,3);ax.set_yticks([-20,-10,0],['−20%','−10%','0'])
        if j==0:
            for model,color in [('abs',NAVY),('share',BLUE)]:
                q=curve[curve.model==model]
                ax.plot(q.mmh,q.pct,color=color,lw=1.8)
                ax.fill_between(q.mmh,q.lo,q.hi,color=PALE if model=='abs' else LIGHT,alpha=.6,lw=0)
                last=q.iloc[-1];label(ax,61,last.pct,'Abs.' if model=='abs' else 'Share',color,size=22,va='center')
            q=curve[(curve.model=='abs')&(curve.mmh==20)].iloc[0]
            ax.plot(q.mmh,q.pct,'o',color=RED,ms=7);label(ax,19,-20,pct(q.pct),RED,ha='center')
            ax.set(xlim=(0,79),xlabel='Rain intensity (mm/h)');ax.set_xticks([0,20,40,60])
        elif j==1:
            q=t[(t.model=='abs')&(t.part=='duration')&t.term.str.startswith('heavy_wet')]
            x=np.arange(4);ax.plot(x,q.pct,color=NAVY,lw=1.8)
            for k,r in enumerate(q.itertuples()): error(ax,k,r.pct,r.pct_lo,r.pct_hi,RED if k==3 else NAVY,ms=6)
            label(ax,1.9,-23,pct(q.iloc[-1].pct),RED,ha='center')
            ax.set_xticks(x,['≤30','31–60','61–120','>120']);ax.tick_params(axis='x',labelrotation=25,pad=5)
            ax.set(xlim=(-.3,3.45),xlabel='Heavy-rain spell (min)')
        else:
            for model,color,off in [('abs',NAVY,-4),('share',BLUE,4)]:
                q=t[(t.model==model)&t.term.str.startswith('dry_')]
                x=np.array([int(term.split('_')[1].split('-')[0])+15 for term in q.term])
                ax.plot(x,q.pct,color=color,lw=1.5)
                for k,r in enumerate(q.itertuples()): error(ax,x[k]+off,r.pct,r.pct_lo,r.pct_hi,RED if model=='abs' and k==0 else color,ms=5)
                last=q.iloc[-1];label(ax,206,last.pct+(-2 if model=='abs' else 2),'Abs.' if model=='abs' else 'Share',color,size=22,va='center')
            r=t[(t.model=='abs')&t.term.str.startswith('dry_')].iloc[0]
            label(ax,45,-12,pct(r.pct),RED,ha='center')
            ax.set(xlim=(25,265),xlabel='Minutes after rain');ax.set_xticks([60,120,180])
        if j: ax.set_yticklabels([])
    # Reference definitions are axis text, not a headline or source line.
    fig.text(.075,.925,'% vacant taxis vs dry',fontsize=pt(22),color=MUTED)
    fig.text(.725,.925,'After-rain reference: dry ≥6 h',fontsize=pt(18),color=MUTED,ha='center')
    save(fig,name)


def where():
    name='deck_where_map';a=read('rain_hit_absolute_all');s=read('rain_hit_share_all');names,land=geography()
    fig=figure(name);plotted=[]
    for j,(t,flag,metric,count) in enumerate([(a,'presentable_abs','abs_pct','taxis_lost_per_heavy_half_hour'),(s,'presentable_share','share_pct','abs_change_per_half_hour')]):
        q=t[t[flag] & (t.expected_vacant_heavy>=4) & (t['abs_q' if j==0 else 'share_q']<.1)].copy()
        top=q.nlargest(10,count) if j==0 else q.nsmallest(10,metric)
        if j==0: q['signed_count']=-q[count];top['signed_count']=-top[count]
        else: q['signed_count']=q[count];top['signed_count']=top[count]
        q['panel']='absolute' if j==0 else 'share';plotted.append(q)
        ax=map_axes(fig,[.006+j*.5,.25,.277,.56],names,land);map_values(ax,q,metric);markers(ax,top)
        key(fig,[.289+j*.5,.13,.205,.84],top,metric,'signed_count',size=19)
        fig.text(.012+j*.5,.91,'Absolute count' if j==0 else 'Citywide share',fontsize=pt(22),color=NAVY,weight=500)
        colorbar(fig,[.035+j*.5,.17,.23,.021])
    record(name,pd.concat(plotted));save(fig,name)


def places():
    name='deck_places_bar';t=read('rain_hit_top30_absolute').head(12)
    assert (t.expected_vacant_heavy>=4).all() and (t.abs_q<.1).all()
    record(name,t)
    fig=figure(name);ax=axes(fig,[.27,.16,.70,.80]);y=np.arange(12)[::-1]
    central={'Downtown Core','Museum','Rochor','Outram','Kallang'}
    colors=[RED if r.planning_area in central else NAVY for r in t.itertuples()]
    ax.barh(y,t.taxis_lost_per_heavy_half_hour,color=colors,height=.60,zorder=3)
    ax.set_yticks(y,[place_name(r) for r in t.itertuples()]);ax.tick_params(axis='y',pad=15)
    for yi,r,color in zip(y,t.itertuples(),colors):
        text=f'{r.taxis_lost_per_heavy_half_hour:.1f} of {r.expected_vacant_heavy:.1f} ({pct(r.abs_pct)})'
        label(ax,r.taxis_lost_per_heavy_half_hour+.12,yi,text,color,va='center')
    ax.set(xlim=(0,11),ylim=(-.7,11.7),xlabel='Fewer vacant taxis per heavy-rain half-hour');ax.set_xticks([0,2,4,6,8])
    fig.text(.27,.985,'CBD and fringe',color=RED,fontsize=pt(22),va='top')
    AUDIT['notes'].append('Places red group is presentation-only: Downtown Core, Museum, Rochor, Outram and Lavender/Kallang; other bars navy. Changi T3 table value is −8.50%, shown −8.5%, not the illustrative −8% in the request.')
    save(fig,name)


def island():
    name='deck_islandwide_map';t=read('spillover_islandwide_share');names,land=geography()
    record(name,t)
    gains=t[t.absolute=='more taxis'].sort_values('cell').copy();assert len(gains)==3
    fig=figure(name);ax=map_axes(fig,[.015,.28,.64,.58],names,land)
    # Plot all estimated share changes, including estimates whose intervals cross zero.
    map_values(ax,t,'share_pct');markers(ax,gains)
    ka=fig.add_axes([.67,.28,.31,.60]);ka.set_axis_off()
    for i,r in enumerate(gains.itertuples()):
        name_text=place_name(r) if r.presentable else f'Cell {r.cell}'
        y=.92-i*.28
        ka.text(0,y,f'{i+1}  {name_text}',fontsize=pt(22),color=NAVY,weight=500,va='top')
        ka.text(0,y-.07,f'{pct(r.share_pct)} share',fontsize=pt(24),color=BLUE,va='top')
        ka.text(0,y-.14,f'+{r.abs_change_per_half_hour:.3f} taxis',fontsize=pt(24),color=INK,va='top')
        if not r.presentable: ka.text(0,y-.21,'<4 expected; unnamed',fontsize=pt(18),color=MUTED,va='top')
    colorbar(fig,[.06,.245,.54,.022])
    fig.text(.67,.94,'Absolute-gain cells',fontsize=pt(22),color=INK)
    fig.text(.025,.035,'Share gains do not necessarily mean more vacant taxis.',fontsize=pt(22),color=MUTED)
    AUDIT['notes'].append('Island-wide map marks the three cells with positive absolute-change CIs, not the much larger set gaining share. Only Senoko West meets the naming filter; cells 48018 and 49023 remain unnamed (<4 expected). Map fills show all saved share estimates, not significance-thresholded zeros.')
    save(fig,name)


def planning():
    name='deck_planning_heatmap';t=read('planning_rain_losses')
    t=t[t.condition.str.startswith('NEA') & (t.day=='weekday')]
    order=t.groupby('planning_area').abs_loss_taxis_per_half_hour.max().sort_values(ascending=False).head(10).index
    bands=['00-07','07-10','10-17','17-20','20-24']
    q=t[t.planning_area.isin(order)];record(name,q)
    m=q.pivot(index='planning_area',columns='time_band',values='abs_loss_taxis_per_half_hour').reindex(index=order,columns=bands)
    fig=figure(name);ax=fig.add_axes([.32,.31,.64,.60])
    norm=Normalize(0,np.nanmax(m.values));ax.imshow(m.values.clip(min=0),cmap=SEQUENTIAL,norm=norm,aspect='auto')
    for i in range(10):
        for j in range(5):
            v=m.iloc[i,j]
            if pd.notna(v):
                rgb=SEQUENTIAL(norm(max(0,v)))[:3]
                luminance=np.dot(rgb,[.2126,.7152,.0722])
                ax.text(j,i,('0.0' if round(v,1)==0 else f'{v:.1f}'.replace('-','−')),ha='center',va='center',fontsize=pt(24),color=WHITE if luminance<.55 else INK)
    ax.set_yticks(range(10),[s.title() for s in order]);ax.set_xticks(range(5),['00–07','07–10','10–17','17–20','20–24'])
    ax.tick_params(pad=10);ax.set_xlabel('Weekday time band · NEA rain forecast',labelpad=3);ax.xaxis.set_label_position('top')
    for spine in ax.spines.values(): spine.set_visible(False)
    colorbar(fig,[.34,.17,.59,.018],SEQUENTIAL,norm,'Fewer taxis per half-hour',ticks=[0,10,20,30])
    AUDIT['notes'].append('Planning areas use the original planning chart ordering: largest gap in any weekday band under an issued NEA rain forecast, top 10. Negative gaps retain their signed text; sequential colour floors at zero, exactly as the original chart.')
    save(fig,name)


def forecasting():
    name='deck_forecast_bars';t=read('forecast_eval_both_labels').query("analysis=='primary' and scale=='1km' and label_version=='issue-time' and subset=='all'")
    record(name,t);assert len(t)==2 and (t.K==19).all()
    fig=figure(name)
    cols=['topk_precision_persistence','topk_precision_glm_no_weather','topk_precision_lgb_no_weather','topk_precision_lgb_weather']
    names=['Persistence','Regression','LightGBM','LightGBM\n+ weather']
    for j,h in enumerate([30,60]):
        ax=axes(fig,[.08+j*.49,.27,.43,.64]);r=t[t.h==h].iloc[0];values=r[cols].to_numpy(float)*100
        bars=ax.bar(np.arange(4),values,color=[NAVY,BLUE,LIGHT,RED],width=.62,zorder=3)
        for bar,v in zip(bars,values): label(ax,bar.get_x()+bar.get_width()/2,v+1.6,f'{v:.2f}%',ha='center')
        ax.axhline(r.base_rate*100,color=MUTED,ls='--',lw=1.1)
        label(ax,.02,r.base_rate*100+1.6,f'Base rate {r.base_rate*100:.2f}%',MUTED,size=24,bbox={'facecolor':BG,'edgecolor':'none','pad':2},zorder=6)
        ax.set(ylim=(0,65),xlim=(-.6,3.7));ax.set_xticks(range(4),names);ax.tick_params(axis='x',labelsize=pt(22),pad=13)
        ax.set_yticks([0,20,40,60],['0','20%','40%','60%'])
        if j==0: ax.set_ylabel('% of 19 alerts truly low')
        fig.text(.08+j*.49,.94,f'{h}-minute horizon',fontsize=pt(22),color=NAVY,weight=500)
    save(fig,name)


def holdout():
    name='deck_holdout_gain';f=read('forecast_eval_both_labels')
    october_onsets=len(read('s22_storm_onsets'))
    # The requested maximum is descriptive selection over every saved 1 km combination, explicitly labelled.
    r=f[f.scale=='1km'].nlargest(1,'weather_gain').iloc[0]
    rows=[{'test':'1 km test year max','gain':r.weather_gain,'lo':r.gain_lo,'hi':r.gain_hi,'details':f'{r.analysis}; {r.label}; {r.h} min; {r.label_version}; {r.subset}'}]
    for name_table,title in [('s22_materiality','Oct 2026 storms · 60 min'),('s22b_materiality','2019 storms · 60 min')]:
        v=read(name_table).query("target=='T2_15' and horizon==60").iloc[0]
        rows.append({'test':title,'gain':v.gain,'lo':v.lo,'hi':v.hi,'details':'Pooled T2 15%; '+(f'descriptive: only {october_onsets} onsets' if name_table=='s22_materiality' else 'confirmatory backward holdout')})
    q=pd.DataFrame(rows);record(name,q)
    fig=figure(name);ax=axes(fig,[.31,.30,.65,.55]);ax.yaxis.grid(False)
    for i,v in enumerate(q.itertuples()):
        y=2-i;color=RED if i==1 else NAVY
        error(ax,v.gain,y,v.lo,v.hi,color,horizontal=True,ms=9)
        label(ax,v.gain,y+.24,f'{v.gain:+.4f}',color,ha='center')
    for v,text in [(.01,'Cells +0.01'),(.02,'Regions +0.02')]:
        ax.axvline(v,color=BLUE,ls='--',lw=1.1)
        label(ax,v,2.95,text,BLUE,size=22,va='bottom',ha='right' if v==.01 else 'left')
    ax.axvline(0,color=MUTED,lw=.7)
    ax.set(xlim=(-.004,.087),ylim=(-.65,2.65),xlabel='Weather gain in PR-AUC')
    ax.set_yticks([2,1,0],q.test);ax.set_xticks([0,.02,.04,.06,.08],['0','.02','.04','.06','.08'])
    fig.text(.025,.025,f'1 km max: descriptive selection · Oct 2026: {october_onsets} onsets, descriptive only',fontsize=pt(18),color=MUTED)
    AUDIT['notes'].append('1 km maximum is +0.00240 (S1 NB issue-time label, 30 min, all times), not the primary deficit-label maximum. It is a descriptive maximum across saved combinations; no model or outcome is re-scored. The Oct 2026 CI uses 893 defined bootstrap draws and cannot override the registered minimum-eight-onset power rule.')
    save(fig,name)


def main():
    OUT.mkdir(parents=True,exist_ok=True);fonts()
    for function in [main_effects,radar,storm,event,dose,where,places,island,planning,forecasting,holdout]:
        function();print(function.__name__,'saved',flush=True)
    for rel,digest in AUDIT['inputs'].items():
        assert sha(ROOT/rel)==digest, f'Frozen input changed: {rel}'
    (OUT/'audit.json').write_text(json.dumps(AUDIT,indent=2)+'\n')
    print('11 charts; every rendered glyph uses registered Poppins; input hashes unchanged.')


if __name__=='__main__':
    main()
