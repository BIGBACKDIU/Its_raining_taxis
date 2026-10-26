"""Export the existing fit-period storm animation as inspectable presentation data only."""
from pathlib import Path
import hashlib
import json
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/story/data'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    source = ROOT / 'data/interim/panel30_2023.parquet'
    before = sha(source)
    peak = pd.Timestamp('2023-07-20 09:30')
    frame = pd.read_parquet(source, columns=['ts','cell','vacant','baseline','mmh'],
                            filters=[('ts','>=',peak-pd.Timedelta(hours=3)),
                                     ('ts','<=',peak+pd.Timedelta(hours=4))])
    frame['pct'] = 100 * (frame.vacant / frame.baseline.clip(lower=1) - 1)
    frame = frame.sort_values(['ts','cell']).reset_index(drop=True)
    assert len(frame)==15*374 and not frame.duplicated(['ts','cell']).any()
    assert frame.groupby('ts').size().eq(374).all()
    assert frame.ts.drop_duplicates().diff().dropna().eq(pd.Timedelta(minutes=30)).all()
    cell_set=set(frame.cell)
    assert len(cell_set)==374 and all(set(group.cell)==cell_set for _,group in frame.groupby('ts'))
    assert frame[['vacant','baseline','mmh','pct']].notna().all().all()
    anchor = pd.read_csv(ROOT/'outputs/figures/deck/data/deck_storm_peak.csv')
    check = frame[frame.ts==peak].set_index('cell').sort_index()
    anchor = anchor.set_index('cell').sort_index()
    for column in ['vacant','baseline','mmh','pct']:
        np.testing.assert_allclose(check[column],anchor[column],rtol=0,atol=1e-12)
    OUT.mkdir(exist_ok=True)
    target = OUT/'storm_2023-07-20.csv'
    frame.to_csv(target,index=False,float_format='%.17g')
    assert sha(source)==before
    (OUT/'storm_2023-07-20.json').write_text(json.dumps({
        'presentation_only':True,'source':str(source.relative_to(ROOT)),
        'source_sha256':before,'export_sha256':sha(target),'rows':len(frame),
        'frames':15,'cells_per_frame':374,'timezone':'Asia/Singapore',
        'start':str(frame.ts.min()),'end':str(frame.ts.max()),
        'selection':'Same existing step-2 storm animation: peak minus 3 hours through plus 4 hours.',
        'formula':'100 * (vacant / max(1, baseline) - 1); existing float32 panel arithmetic.',
        'peak_matches_existing_deck_csv':True,
        'no_model_fit_or_scoring':True},indent=2)+'\n')
    print('Exported 15 saved snapshots / 5,610 cell rows; peak exactly matches the saved deck CSV.')

if __name__=='__main__':
    main()
