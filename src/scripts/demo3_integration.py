import argparse
import csv
import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def request(base, path, *, method='GET', params=None, csv_response=False):
    url = base.rstrip('/') + path
    if params:
        url += '?' + urlencode(params)
    req = Request(url, method=method, headers={'Accept': 'text/csv' if csv_response else 'application/json'})
    try:
        with urlopen(req, timeout=90) as response:
            raw = response.read()
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'HTTP {exc.code}: {url}\n{body}') from exc
    except URLError as exc:
        raise RuntimeError(f'Cannot connect to {url}: {exc.reason}') from exc
    return raw if csv_response else json.loads(raw.decode('utf-8'))


def check_csv(raw, expected, *, label):
    text = raw.decode('utf-8-sig')
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise RuntimeError(f'{label}: CSV contains no data rows')
    columns = list(rows[0])
    if columns != expected:
        raise RuntimeError(f'{label}: unexpected columns: {columns!r}')
    return rows


def main():
    parser = argparse.ArgumentParser(description='MOEX -> DB -> curves -> CSV demo via QuantumTeam API')
    parser.add_argument('--url', default='http://localhost:8000', help='FastAPI base URL')
    parser.add_argument('--date', help='MOEX trading date YYYY-MM-DD; omit for latest available')
    parser.add_argument('--months', type=int, default=12, help='Demo forecast months (1..360)')
    parser.add_argument('--output', default='demo_output', help='Output directory')
    args = parser.parse_args()
    if not 1 <= args.months <= 360:
        parser.error('--months must be in 1..360')
    if args.date:
        from datetime import date
        try:
            date.fromisoformat(args.date)
        except ValueError:
            parser.error('--date must be YYYY-MM-DD')

    print('[1/5] MOEX request and curve calculation...')
    params = {'trade_date': args.date} if args.date else None
    snapshot = request(args.url, '/api/v1/curves/calculate', method='POST', params=params)
    snapshot_id = snapshot['id']
    if snapshot['status'] != 'built':
        raise RuntimeError(f'Snapshot {snapshot_id} is not built: {snapshot["status"]}')
    print(f'  snapshot_id={snapshot_id}, trade_date={snapshot["trade_date"]}, status={snapshot["status"]}')

    print('[2/5] Verify base curve...')
    base = request(args.url, f'/api/v1/curves/{snapshot_id}/base')
    if not base:
        raise RuntimeError('Base curve is empty')
    print(f'  base points: {len(base)}; first point: {base[0]}')

    print('[3/5] List scenarios...')
    scenarios = request(args.url, '/api/v1/scenarios')
    active = [s['code'] for s in scenarios if s.get('is_active', True)]
    print('  active scenarios:', ', '.join(active) if active else '(none)')

    print('[4/5] Export real MOEX curves...')
    moex = request(args.url, f'/api/v1/exports/curves/{snapshot_id}/moex.csv', csv_response=True)
    moex_rows = check_csv(moex, ['trade_date', 'scenario', 'bucket_code', 'tenor_years', 'rate'], label='MOEX')
    if sum(row['scenario'] == 'base' for row in moex_rows) != len(base):
        raise RuntimeError('Base curve count differs between API and CSV')

    print('[5/5] Export DEMO calculator forecast (NOT financial forecast)...')
    demo = request(args.url, f'/api/v1/exports/curves/{snapshot_id}/calculator-demo.csv', params={'months': args.months}, csv_response=True)
    demo_rows = check_csv(demo, ['indicator', 'date', 'rate', 'scenario'], label='Calculator DEMO')
    if sum(row['scenario'] == 'base' for row in demo_rows) != args.months:
        raise RuntimeError('Incorrect number of base forecast rows')

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    moex_path = out / f'moex_curves_{snapshot_id}.csv'
    demo_path = out / f'calculator_DEMO_{snapshot_id}.csv'
    moex_path.write_bytes(moex)
    demo_path.write_bytes(demo)
    print(f'  MOEX CSV: {moex_path} ({len(moex_rows)} rows)')
    print(f'  DEMO CSV: {demo_path} ({len(demo_rows)} rows)')
    print('  First calculator row:', demo_rows[0])
    print('SUCCESS: API workflow completed; no financial validation of demo indicator rates was performed.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, KeyError, ValueError, UnicodeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
