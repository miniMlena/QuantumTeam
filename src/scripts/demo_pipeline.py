"""
Демо-пайплайн: fetch MOEX → build base curve → apply scenarios → save.
Запускается вручную, печатает прогресс в stdout.
"""
import sys
import traceback
from datetime import date

from db.engine import SessionLocal, init_db
from db.repositories import curve_repo, scenario_repo
from domain.moex.client import fetch_curve_from_moex
from domain.curve.builder import build_base_curve
from domain.curve.shifts import apply_shift


def log(step: str, msg: str = ""):
    print(f"[{step}] {msg}", flush=True)


def ensure_default_scenarios(session):
    scenario_repo.ensure_default_scenarios(session)


def main() -> int:
    try:
        log("0/5", "init_db (create tables if missing)")
        init_db()

        with SessionLocal() as session:
            log("0/5", "ensure default scenarios")
            ensure_default_scenarios(session)

            log("1/5", "fetching MOEX curve...")
            params = fetch_curve_from_moex()
            trade_date = params.pop("trade_date", date.today())
            log("1/5", f"trade_date = {trade_date}")
            log("1/5", f"params = b1={params['b1']}, b2={params['b2']}, "
                       f"b3={params['b3']}, t1={params['t1']}")

            log("2/5", "creating snapshot...")
            snap = curve_repo.create_snapshot(
                session, trade_date=trade_date, params=params
            )
            log("2/5", f"snapshot id = {snap.id}")

            log("3/5", "building base curve (Nelson-Siegel)...")
            base_points = build_base_curve(params)
            curve_repo.save_base_points(session, snap.id, base_points)
            types = {}
            for p in base_points:
                types[p["point_type"]] = types.get(p["point_type"], 0) + 1
            log("3/5", f"{len(base_points)} points saved")
            log("3/5", f"point_types: {types}")

            log("4/5", "applying scenarios...")
            scenarios = scenario_repo.list_scenarios(session, only_active=True)
            for sc in scenarios:
                shift_map = scenario_repo.get_shift_map(session, sc.id)
                shifted = apply_shift(base_points, shift_map)
                curve_repo.save_shifted_points(session, snap.id, sc.id, shifted)
                log("4/5", f"  {sc.code}: {len(shifted)} points")

            curve_repo.mark_snapshot_status(session, snap.id, "built")
            log("5/5", f"done. snapshot id = {snap.id}")

        return 0
    except Exception:
        log("ERROR", "pipeline failed")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())