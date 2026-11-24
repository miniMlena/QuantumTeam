import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from api.deps import get_db
from api.schemas.curve import SnapshotOut
from db.repositories import curve_repo, scenario_repo
from services.curve_pipeline import build_curves
from domain.curve.shifts import _interpolate_shift
from domain.curve.scenarios import BASEL_SHIFTS, basel_shift_bp

router = APIRouter(prefix='/curve-ui', tags=['curve-ui'])
PARAMS = ('b1','b2','b3','t1', *(f'g{i}' for i in range(1,10)))

def snapshot_or_404(db, snapshot_id):
    snap = curve_repo.get_snapshot(db, snapshot_id)
    if snap is None:
        raise HTTPException(404, 'Snapshot not found')
    return snap

@router.get('/{snapshot_id}/parameters')
def parameters(snapshot_id: int, db: Session = Depends(get_db)):
    s = snapshot_or_404(db, snapshot_id)
    return {'id': s.id, 'trade_date': s.trade_date, 'source': s.source,
            'parameters': {k: getattr(s,k) for k in PARAMS}}

@router.post('/{snapshot_id}/recalculate', response_model=SnapshotOut)
def recalculate(snapshot_id: int, db: Session = Depends(get_db)):
    s = snapshot_or_404(db, snapshot_id)
    new = curve_repo.copy_snapshot(db,s)
    build_curves(db,new)
    return new

@router.post('/import-points')
def import_points(content: str = Body(media_type='text/plain'), db: Session = Depends(get_db)):
    # Import exported term CSV or a simple tenor_years,rate CSV. Rates are fractions.
    if len(content) > 2_000_000:
        raise HTTPException(413, 'CSV too large')
    try:
        reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
        if not {'tenor_years','rate'}.issubset(reader.fieldnames or []):
            raise ValueError('Required columns: tenor_years,rate')
        points = {}; dates = set()
        for row in reader:
            if row.get('scenario','base') != 'base':
                continue
            t = Decimal(row['tenor_years']); r = Decimal(row['rate'])
            if not t.is_finite() or not r.is_finite() or not 0 < t <= 100 or abs(r)>10:
                raise ValueError('Invalid tenor or rate')
            if t in points: raise ValueError('Duplicate tenor')
            points[t] = float(r*100)
            if row.get('trade_date'): dates.add(date.fromisoformat(row['trade_date']))
            if len(points)>5000: raise ValueError('Too many points')
        if len(points)<2 or len(dates)>1: raise ValueError('Need at least two points from one date')
    except (ValueError, InvalidOperation, TypeError, KeyError, csv.Error) as exc:
        raise HTTPException(422, f'Invalid CSV: {exc}') from exc
    scenarios = scenario_repo.list_scenarios(db, only_active=True)
    series = {'base': [{'tenor_years':float(t),'rate':r,'shift_bp':0} for t,r in sorted(points.items())]}
    for s in scenarios:
        if s.code=='base': continue
        shifts = scenario_repo.get_shift_map(db,s.id)
        series[s.code] = []
        for t,r in sorted(points.items()):
            x=float(t)
            shift=basel_shift_bp(s.code,x) if s.is_regulatory and s.code in BASEL_SHIFTS else _interpolate_shift(x,shifts)
            series[s.code].append({'tenor_years':x,'rate':r+shift/100,'shift_bp':shift})
    return {'source':'csv_preview','trade_date':next(iter(dates),None),'series':series}
