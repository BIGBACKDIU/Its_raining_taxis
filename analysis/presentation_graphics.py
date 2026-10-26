"""Convert frozen Matplotlib SVG evidence to editable slide paths and Poppins text.

No fitting or scoring. Numerical labels and paths come from the saved SVGs. Percentage
map fills alone are re-read by cell ID from their saved result tables for a common ±40% scale.
"""
from __future__ import annotations
import base64, colorsys, copy, hashlib, html, io, json, math, re, sys, zipfile
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from lxml import etree as E
from PIL import Image, ImageFont
from matplotlib import font_manager
from pipeline.grid import cell_ids

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'.deck-build'
NS={'s':'http://www.w3.org/2000/svg'}
XL='{http://www.w3.org/1999/xlink}href'
NUM=r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'
BG='#FBFCFE'; NAVY='#14295B'; BLUE='#2C5EAA'; LIGHT='#8FB8F2'; PALE='#DCE6F4'; RED='#C0453C'; INK='#14203A'; MUTED='#5A6683'; GRID='#E4EAF4'; NODATA='#F2F4F7'
INPUTS={}

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def table(name):
 p=ROOT/'outputs/tables'/f'{name}.csv';INPUTS[str(p.relative_to(ROOT))]=digest(p);return pd.read_csv(p)
def rgb(hex):return np.array([int(hex[i:i+2],16) for i in (1,3,5)],float)/255

def blend(a,b,f):return '#'+''.join(f'{int(round(v*255)):02X}' for v in rgb(a)*(1-f)+rgb(b)*f)
def change(value):return blend('#FFFFFF',RED if value<0 else BLUE,min(1,abs(value)/40))
def palette(color,kind='stroke'):
 if not color or color=='none':return 'none'
 if not color.startswith('#'):return color
 c=color.lower()
 fixed={'#ffffff':BG,'#fbfcfe':BG,'#000000':INK,'#172b45':INK,'#172c46':INK,'#14203a':INK,
        '#606a76':MUTED,'#64748b':MUTED,'#6b7280':MUTED,'#52514e':MUTED,
        '#cececc':NODATA,'#bdbcb7':GRID,'#f4f3f0':GRID,'#f2f1ed':BG,
        '#dad9d5':GRID,'#c8c7c2':PALE,'#e7e5e0':GRID,'#d6d3ca':GRID,
        '#eb6834':RED,'#b8431c':RED,'#2a78d6':BLUE,'#0d2f5c':NAVY}
 if c in fixed:return fixed[c]
 if c in [x.lower() for x in [NAVY,BLUE,LIGHT,PALE,RED,INK,MUTED,GRID,NODATA,BG]]:return color.upper()
 try:
  h,l,s=colorsys.rgb_to_hls(*rgb(c))
  if s<.15:return GRID if l>.6 else MUTED
  if h<.14 or h>.9:
   return blend(RED,'#FFFFFF',max(0,min(1,(l-.48)/.52)))
  if .4<h<.8:
   stops=[NAVY,BLUE,LIGHT,PALE]
   v=max(0,min(2.999,(l-.20)/.70*3));k=int(v);return blend(stops[k],stops[k+1],v-k)
  return BLUE
 except Exception:return INK

def matrix(value):
 out=np.eye(3)
 for name,args in re.findall(r'([a-zA-Z]+)\s*\(([^)]*)\)',value or ''):
  a=[float(n) for n in re.findall(NUM,args)];m=np.eye(3)
  if name=='translate':m[0,2]=a[0];m[1,2]=a[1] if len(a)>1 else 0
  elif name=='scale':m[0,0]=a[0];m[1,1]=a[1] if len(a)>1 else a[0]
  elif name=='rotate':
   t=math.radians(a[0]);m[:2,:2]=[[math.cos(t),-math.sin(t)],[math.sin(t),math.cos(t)]]
   if len(a)>2:
    x,y=a[1:3];m[0,2]=x-m[0,0]*x-m[0,1]*y;m[1,2]=y-m[1,0]*x-m[1,1]*y
  elif name=='matrix':m=np.array([[a[0],a[2],a[4]],[a[1],a[3],a[5]],[0,0,1]])
  out=out@m
 return out

def point(m,x,y):return (m@np.array([x,y,1]))[:2].tolist()
def commands(d,m):
 tokens=re.findall(r'[MLCQZmlcqz]|'+NUM,d or '');i=0;cmd=None;out=[]
 while i<len(tokens):
  if tokens[i].isalpha():cmd=tokens[i].upper();i+=1
  if cmd=='Z':out.append({'close':{}});cmd=None;continue
  count={'M':2,'L':2,'Q':4,'C':6}.get(cmd)
  if count is None:raise RuntimeError(f'Unsupported SVG command {cmd}')
  v=[float(s) for s in tokens[i:i+count]];i+=count
  xy=[point(m,*v[k:k+2]) for k in range(0,len(v),2)]
  if cmd=='M':out.append({'moveTo':dict(zip(('x','y'),xy[0]))});cmd='L'
  elif cmd=='L':out.append({'lineTo':dict(zip(('x','y'),xy[0]))})
  elif cmd=='Q':out.append({'quadBezTo':dict(zip(('x1','y1','x','y'),sum(xy,[])))})
  else:out.append({'cubicBezTo':dict(zip(('x1','y1','x2','y2','x','y'),sum(xy,[])))})
 return out

def coords(cmds):
 points=[]
 for c in cmds:
  for v in c.values():
   for x,y in [('x','y'),('x1','y1'),('x2','y2')]:
    if x in v:points.append((v[x],v[y]))
 return np.array(points)

def bounds(cmds):
 xy=coords(cmds)
 if not len(xy):return [0,0,0,0]
 return [*xy.min(0),*xy.max(0)]

def style(el, inherited):
 d={**inherited}
 for item in (el.get('style') or '').split(';'):
  if ':' in item:
   k,v=item.split(':',1);d[k.strip()]=v.strip()
 for k in ['fill','stroke','stroke-width','opacity','fill-opacity','stroke-opacity','font-size','font-family','text-anchor']:
  if el.get(k) is not None:d[k]=el.get(k)
 return d

class SVG:
 def __init__(self,path,modern=False):
  self.path=path;self.name=path.stem;self.modern=modern;self.root=E.parse(str(path)).getroot();self.defs={el.get('id'):el for el in self.root.xpath('.//*[@id]')}
  self.width,self.height=map(float,self.root.get('viewBox').split()[2:]);self.map_tables={};self.maps=0;self.glyph_boxes={}
  self.axes=self.root.xpath(".//s:g[starts-with(@id,'axes_')]",namespaces=NS)
  self.named_axes={i for i,a in enumerate(self.axes) if any(len(c:=g.xpath('./comment()'))>=4 and all(re.match(r'^\d+\s',v.text.strip()) for v in c) for g in a.xpath(".//s:g[starts-with(@id,'text_')]",namespaces=NS))}
  self.boxes=[self.axis_box(a) for a in self.axes]
  self.colorbars=[i for i,b in enumerate(self.boxes) if (b[2]-b[0]>6*(b[3]-b[1]) and b[3]-b[1]<35) or (b[3]-b[1]>5*(b[2]-b[0]) and b[2]-b[0]<35)]
  if not modern:self.load_maps()
 def axis_box(self,a):
  clips=[]
  for el in a.xpath('.//*[@clip-path]'):
   match=re.search(r'#([^)]*)',el.get('clip-path'))
   if match:
    ref=self.defs.get(match[1]);r=ref.find('s:rect',NS) if ref is not None else None
    if r is not None:clips.append(tuple(float(r.get(k)) for k in ['x','y','width','height']))
  if clips:
   x,y,w,h=Counter(clips).most_common(1)[0][0];return [x,y,x+w,y+h]
  for g in a:
   if (g.get('id') or '').startswith('patch_'):
    p=g.find('s:path',NS)
    if p is not None:
     b=bounds(commands(p.get('d'),np.eye(3)))
     if b[2]>b[0] and b[3]>b[1]:return b
  return [0,0,self.width,self.height]
 def load_maps(self):
  if self.name=='desc_maps_dry_heavy':self.map_tables[2]=(table('desc_maps_dry_heavy').set_index('cell'),'pct_change_heavy_vs_dry',None)
  if self.name=='desc_storm_2023-07-20_peak':
   t=pd.read_csv(ROOT/'outputs/figures/deck/data/deck_storm_peak.csv');self.map_tables[1]=(t.set_index('cell'),'pct',None)
  if self.name=='names_rain_hit_map':
   t=table('cell_rain_effects').set_index('cell')
   self.map_tables={0:(t,'abs_pct','presentable_abs'),1:(t,'share_pct','presentable_share')}
  if self.name=='spillover_islandwide_map':self.map_tables[0]=(table('spillover_islandwide_share').set_index('cell'),'share_pct',None)
  if self.name=='stands_predicted_sensitivity':self.map_tables[0]=(table('stands_predicted_sensitivity_cells').set_index('cell'),'pred_heavy_abs_pct','eligible')
  if self.name=='inference_hotspots':
   t=table('inference_hotspots').set_index('cell');t['show']=t.hotspot.str.startswith('significantly');self.map_tables[0]=(t,'pct','show')
 def shape(self,el,m,st,axis):
  d=el.get('d')
  if not d:return None
  cmds=commands(d,m);box=bounds(cmds);fill=st.get('fill','none');stroke=st.get('stroke','none');recolored=False
  if axis in self.map_tables and fill!='none':
   b=self.boxes[axis];w,h=box[2]-box[0],box[3]-box[1]
   rectangle=all(set(c)<= {'moveTo','lineTo','close'} for c in cmds) and sum('lineTo' in c for c in cmds) in (3,4) and any('close' in c for c in cmds)
   if rectangle and .012 < w/max(1,b[2]-b[0]) < .03 and .015 < h/max(1,b[3]-b[1]) < .055:
    lon=103.6+((box[0]+box[2])/2-b[0])/(b[2]-b[0])*.45
    lat=1.475-((box[1]+box[3])/2-b[1])/(b[3]-b[1])*.26
    cell=int(cell_ids(lon,lat,size=1000));t,col,flag=self.map_tables[axis]
    if cell in t.index and (flag is None or bool(t.loc[cell,flag])):
     fill=change(float(t.loc[cell,col]));self.maps+=1
    else:fill=NODATA
    stroke=BG;recolored=True
   elif any('cubicBezTo' in c for c in cmds) and .005<w/max(1,b[2]-b[0])<.04 and .005<h/max(1,b[3]-b[1])<.06 and fill.lower()=='#ffffff':
    fill=NAVY;stroke=NAVY;recolored=True
  # Remove vertical grid lines and legend boxes, while retaining data and reference lines.
  ancestors=[a.get('id','') for a in el.iterancestors()]
  if any(a.startswith('xtick_') for a in ancestors) and abs(box[2]-box[0])<.1 and box[3]-box[1]>40:return None
  # Omit axes backgrounds and top/right Cartesian spines. Keep all data paths.
  b=self.boxes[axis] if axis is not None else None
  ident=el.getparent().get('id','') if el.getparent() is not None else ''
  if any(a.startswith('legend_') for a in ancestors) and ident.startswith('patch_') and box[2]-box[0]>40 and box[3]-box[1]>15:return None
  if ident.startswith('patch_') and b and np.allclose(box,b,atol=.05):return None
  if ident.startswith('patch_') and b and fill=='none':
   if abs(box[1]-b[1])<.05 and abs(box[3]-b[1])<.05:return None
   if abs(box[0]-b[2])<.05 and abs(box[2]-b[2])<.05:return None
  return {'kind':'path','commands':cmds,'fill':fill if recolored else palette(fill,'fill'),'stroke':palette(stroke),'strokeWidth':float(st.get('stroke-width',1)),
          'alpha':float(st.get('opacity',1))*float(st.get('fill-opacity',1)),
          'dash':st.get('stroke-dasharray'), 'box':box}
 def old_text(self,comment,m,st,axis):
  text=html.unescape(comment.text.strip());power=re.fullmatch(r'\$\\mathdefault\{10\^\{([-+]?\d+)\}\}\$',text)
  if power:text=f'{10**int(power[1]):g}'
  g=comment.getnext()
  while g is not None and not (isinstance(g.tag,str) and E.QName(g).localname=='g'):g=g.getnext()
  if g is None:return None
  tr=g.get('transform','');gm=m@matrix(tr);font=max(np.linalg.norm(gm[:2,0])*100,.1)
  position=point(gm,0,0);rot=math.degrees(math.atan2(gm[1,0],gm[0,0]));st=style(g,st)
  first=g.find('.//s:use',NS);bold=first is not None and 'Bold' in first.get(XL,'')
  # Recover the original alignment from the saved glyph geometry, not an approximate font.
  right=0
  for use in g.findall('s:use',NS):
   key=use.get(XL,'').lstrip('#');ref=self.defs.get(key)
   if ref is None or not ref.get('d'):continue
   if key not in self.glyph_boxes:self.glyph_boxes[key]=bounds(commands(ref.get('d'),matrix(ref.get('transform'))))
   b=self.glyph_boxes[key];um=matrix(use.get('transform'))
   right=max(right,point(um,b[2],b[3])[0])
  width=right*np.linalg.norm(gm[:2,0])
  parents=[a.get('id','') for a in comment.iterancestors()]
  anchor='start'
  if any(x.startswith('xtick_') for x in parents):anchor='middle'
  elif any(x.startswith('ytick_') for x in parents):anchor='end'
  elif abs(rot)>10 or any(x.startswith('matplotlib.axis_') for x in parents):anchor='middle'
  shift=width/2 if anchor=='middle' else width if anchor=='end' else 0
  position[0]+=shift*math.cos(math.radians(rot));position[1]+=shift*math.sin(math.radians(rot))
  if axis in self.named_axes and text.isdigit() and 1<=int(text)<=20:
   b=self.boxes[axis]
   if b[0]<position[0]<b[2] and b[1]<position[1]<b[3]:
    return {'kind':'mapMarker','text':text,'x':position[0]+width/2,'y':position[1]-font*.33}
  item=self.text_item(text,position,font,rot,anchor,st,bold,axis)
  item['role']='ytick' if any(x.startswith('ytick_') for x in parents) else 'xtick' if any(x.startswith('xtick_') for x in parents) else ('ylabel' if abs(rot)>10 else 'xlabel') if any(x.startswith('matplotlib.axis_') for x in parents) else 'label'
  return item
 def text_item(self,text,pos,font,rot,anchor,st,bold,axis):
  # Original axes titles become the slide's editable panel headings, not tiny chart titles.
  b=self.boxes[axis] if axis is not None else None
  if b and pos[1]<b[1]-1 and abs(rot)<5 and axis not in self.colorbars:
   return {'kind':'panelTitle','text':text}
  color=palette(st.get('fill',INK))
  if axis in self.map_tables and text.isdigit() and 1<=int(text)<=20 and b[0]<pos[0]<b[2] and b[1]<pos[1]<b[3]:color='#FFFFFF'
  return {'kind':'text','text':text,'x':pos[0],'y':pos[1],'fontSize':font,'rotation':rot,'anchor':anchor,'color':color,'bold':bold}
 def walk(self,el,m=None,st=None,axis=None):
  if m is None:m=np.eye(3)
  if st is None:st={'fill':'#000000'}
  if not isinstance(el.tag,str):return []
  tag=E.QName(el).localname
  if tag=='g' and el.get('id','').startswith('legend_'):return []
  if tag in ['defs','clipPath','metadata','style']:return []
  m=m@matrix(el.get('transform'));st=style(el,st)
  if tag=='g' and el.get('id','').startswith('text_') and el.xpath('./comment()'):
   comments=el.xpath('./comment()')
   items=[item for c in comments if (item:=self.old_text(c,m,st,axis))]
   if len(comments)>=4 and all(re.match(r'^\d+\s',c.text.strip()) for c in comments):
    for item in items:item['kind']='placeList'
   return items
  if tag=='text':
   x=float(el.get('x',0));y=float(el.get('y',0));pos=point(m,x,y)
   font=float(re.findall(NUM,st.get('font-size','10'))[0])*np.linalg.norm(m[:2,0])
   rot=math.degrees(math.atan2(m[1,0],m[0,0]));item=self.text_item(''.join(el.itertext()),pos,font,rot,st.get('text-anchor','start'),st,'600' in st.get('font-weight','') or st.get('font-weight')=='bold',axis)
   return [item]
  if tag=='path':
   item=self.shape(el,m,st,axis);return [item] if item else []
  if tag=='use':
   ref=self.defs.get(el.get(XL,'').lstrip('#'))
   if ref is None:return []
   return self.walk(ref,m@matrix(f"translate({el.get('x',0)} {el.get('y',0)})"),st,axis)
  if tag=='image':
   data=base64.b64decode(el.get(XL).split(',',1)[1]);im=Image.open(io.BytesIO(data)).convert('RGBA')
   values=np.array(im);unique=np.unique(values[:,:,:3].reshape(-1,3),axis=0)
   for v in unique:
    old='#'+''.join(f'{x:02x}' for x in v);new=rgb(palette(old,'fill'))*255
    mask=(values[:,:,:3]==v).all(2);values[mask,:3]=new.round().astype('uint8')
   stream=io.BytesIO();Image.fromarray(values).save(stream,format='PNG')
   x,y=float(el.get('x',0)),float(el.get('y',0));w,h=float(el.get('width')),float(el.get('height'))
   points=np.array([point(m,x,y),point(m,x+w,y+h)]);lo=points.min(0);hi=points.max(0)
   return [{'kind':'image','data':base64.b64encode(stream.getvalue()).decode(),'box':[*lo,*hi],'flipY':bool(m[1,1]<0),'flipX':bool(m[0,0]<0)}]
  out=[]
  for child in el:out.extend(self.walk(child,m,st,axis))
  return out
 def components(self):
  components=[]
  for i,axis in enumerate(self.axes):
   items=self.walk(axis,axis=i);titles=[x['text'] for x in items if x['kind']=='panelTitle']
   legend_items=[]
   for legend in axis.xpath(".//s:g[starts-with(@id,'legend_')]",namespaces=NS):
    for child in legend:legend_items.extend(self.walk(child,axis=i))
   components.append({'legendItems':legend_items,'placeList':[x['text'] for x in items if x['kind']=='placeList'],'axis':i,'isColorbar':i in self.colorbars,'items':[x for x in items if x['kind'] not in ['panelTitle','placeList']],'titles':titles,'box':self.boxes[i]})
  return components
 def whole(self):
  # Used for the already styled 11 charts; preserve their intentional figure-level notes.
  return self.walk(self.root,axis=None)


def main():
 PRIVATE.mkdir(exist_ok=True);charts=[]
 for path in sorted((ROOT/'outputs/figures').glob('*.svg')):
  if path.stem.startswith('storm_builder'):continue
  INPUTS[str(path.relative_to(ROOT))]=digest(path)
  svg=SVG(path);comps=svg.components();data=[c for c in comps if not c['isColorbar'] and c['items']];cbs=[c for c in comps if c['isColorbar']]
  if path.stem in ['effects_robustness','forecast_pr_auc','sim_heldout_storms','sim2_heldout_storms']:
   # Shared axes in the saved figure need their existing labels repeated when split across slides.
   first=data[0];b=first['box']
   for c in data[1:]:
    roles={v.get('role') for v in c['items']}
    q=c['box']
    for item in first['items']:
     if item.get('role') not in ['ytick','ylabel'] or item.get('role') in roles:continue
     v=copy.deepcopy(item);v['x']=q[0]+item['x']-b[0];v['y']=q[1]+(item['y']-b[1])/(b[3]-b[1])*(q[3]-q[1]);c['items'].append(v)
  # Explicit colour bars for percentage maps use the shared ±40% range.
  if svg.map_tables:
   for cb in cbs:
    cb['standardChange']=False
    # In mixed count/percent maps only the final bar belongs to the percent panel.
    if path.stem=='desc_maps_dry_heavy':cb['standardChange']=cb['axis']==max(c['axis'] for c in cbs)
    elif path.stem=='desc_storm_2023-07-20_peak':cb['standardChange']=cb['axis']==max(c['axis'] for c in cbs)
    else:cb['standardChange']=True
  legends=[]
  for g in svg.root.xpath(".//s:g[starts-with(@id,'legend_') and not(ancestor::s:g[starts-with(@id,'axes_')])]",namespaces=NS):
   legends.append([item for child in g for item in svg.walk(child,axis=None)])
  charts.append({'name':path.stem,'source':str(path.relative_to(ROOT)),'sourceSha256':digest(path),'components':data,'colorbars':cbs,'recoloredMapCells':svg.maps,'legends':legends})
 modern={}
 for path in sorted((ROOT/'outputs/figures/deck').glob('deck_*.svg')):
  svg=SVG(path,modern=True);modern[path.stem]={'width':svg.width,'height':svg.height,'items':svg.whole()}
 planning=table('planning_rain_losses');planning=planning[planning.condition.str.startswith('NEA') & (planning.day=='weekday')]
 order=planning.groupby('planning_area').abs_loss_taxis_per_half_hour.max().sort_values(ascending=False).head(15).index
 bands=['00-07','07-10','10-17','17-20','20-24']
 full_heatmap=planning.pivot(index='planning_area',columns='time_band',values='abs_loss_taxis_per_half_hour').reindex(index=order,columns=bands)
 package={'charts':charts,'modern':modern,'inputs':INPUTS,'planning':{'areas':[s.title() for s in order],'bands':bands,'values':full_heatmap.values.tolist()}}
 (PRIVATE/'graphics.json').write_text(json.dumps(package,separators=(',',':')))
 print('Converted',len(charts),'frozen graph files,',sum(len(c['components']) for c in charts),'data panels;',len(modern),'selected deck charts.')

def export_panels():
 """Export the finished appendix cards and verify every frozen source hash."""
 manifest=json.loads((ROOT/'outputs/presentations/graph_coverage.json').read_text())
 for relative,expected in manifest['sourceInputs'].items():
  assert digest(ROOT/relative)==expected,f'Frozen input changed: {relative}'
 assert len({c['sourceGraph'] for c in manifest['coverage']})==44
 assert sum(len(c['panels']) for c in manifest['coverage'])==97
 out=ROOT/'outputs/figures/deck/all';out.mkdir(exist_ok=True)
 for old in out.glob('*.png'):old.unlink()
 for row in manifest['coverage']:
  image=Image.open(PRIVATE/'final_previews'/f"slide-{row['slide']:03}.png")
  assert image.size==(2560,1440)
  image.crop((170,404,2390,1260)).save(out/f"{row['sourceGraph']}_part{row['part']}.png")
 archive=ROOT/'outputs/presentations/all_project_charts.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
  for path in sorted((ROOT/'outputs/figures/deck').glob('*.png')):bundle.write(path,'selected/'+path.name)
  for path in sorted(out.glob('*.png')):bundle.write(path,'all/'+path.name)
  for folder in ['poppins','anton']:
   for path in sorted((ROOT/'assets/fonts'/folder).iterdir()):
    if path.suffix.lower() in ['.ttf','.txt','.md']:bundle.write(path,f'fonts/{folder}/{path.name}')
  bundle.write(ROOT/'outputs/presentations/graph_coverage.json','graph_coverage.json')
  bundle.writestr('README.txt','All 44 unique saved project graphs appear in all/ (multipart charts use several files).\nselected/ contains the eleven main-story chart exports. No models were re-estimated.\nFonts and their OFL licences are included for editing the accompanying PowerPoint.\n')
 print(f"{len(manifest['coverage'])} appendix cards exported at 2220 × 856; all frozen hashes unchanged.")

if __name__=='__main__':
 if '--export-panels' in sys.argv:export_panels()
 else:main()
