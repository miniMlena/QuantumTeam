"""
Демо-пайплайн: fetch MOEX → build base curve → apply scenarios → save.
Загружает данные за день, предшествующий самому раннему trade_date
в таблице curve_snapshot (или вчерашний день, если таблица пуста).
Запускается вручную, печатает прогресс в stdout.
"""
import sys
import traceback
from datetime import date, timedelta

import httpx
from sqlalchemy import func, select

from db.engine import SessionLocal, init_db
from db.models import CurveSnapshot
from db.repositories import curve_repo, scenario_repo
from domain.moex.client import MOEX_ZCYC_URL, _extract_params_block
from domain.curve.builder import build_base_curve
from domain.curve.shifts import apply_shift


def log(step: str, msg: str = ""):
    print(f"[{step}] {msg}", flush=True)


def ensure_default_scenarios(session):
    """Создаёт 4 базовых сценария, если их ещё нет."""
    defaults = [
        {
            "code": "parallel_up", "name": "Parallel +100 bp",
            "scenario_type": "parallel", "is_regulatory": True,
            "shifts": [{"tenor_months": t, "shift_bp": 100}
                       for t in (1, 3, 6, 12, 24, 60, 120, 240, 360)],
        },
        {
            "code": "parallel_down", "name": "Parallel -100 bp",
            "scenario_type": "parallel", "is_regulatory": True,
            "shifts": [{"tenor_months": t, "shift_bp": -100}
                       for t in (1, 3, 6, 12, 24, 60, 120, 240, 360)],
        },
        {
            "code": "twist_steep", "name": "Steepener (short -50, long +50)",
            "scenario_type": "twist", "is_regulatory": False,
            "shifts": [
                {"tenor_months": 1,   "shift_bp": -50},
                {"tenor_months": 12,  "shift_bp": -25},
                {"tenor_months": 60,  "shift_bp": 0},
                {"tenor_months": 120, "shift_bp": 25},
                {"tenor_months": 360, "shift_bp": 50},
            ],
        },
        {
            "code": "curvature", "name": "Curvature (belly +50)",
            "scenario_type": "curvature", "is_regulatory": False,
            "shifts": [
                {"tenor_months": 1,   "shift_bp": 0},
                {"tenor_months": 24,  "shift_bp": 50},
                {"tenor_months": 60,  "shift_bp": 50},
                {"tenor_months": 120, "shift_bp": 0},
                {"tenor_months": 360, "shift_bp": 0},
            ],
        },
    ]
    for d in defaults:
        if scenario_repo.get_scenario_by_code(session, d["code"]) is None:
            scenario_repo.create_scenario(
                session,
                code=d["code"], name=d["name"],
                scenario_type=d["scenario_type"],
                is_regulatory=d["is_regulatory"],
                description=None, shifts=d["shifts"],
            )
            log("scenarios", f"created: {d['code']}")


def _pick_target_date(session) -> date:
    """
    Возвращает день, предшествующий самому раннему trade_date в curve_snapshot.
    Если таблица пуста — вчерашний день.
    """
    min_trade_date = session.scalar(
        select(func.min(CurveSnapshot.trade_date))
    )
    if min_trade_date is None:
        return date.today() - timedelta(days=1)
    return min_trade_date - timedelta(days=1)


def _fetch_curve_for_date(target_date: date, timeout: float = 15.0) -> dict:
    """
    Скачивает параметры кривой MOEX на конкретную дату через
    ?date=YYYY-MM-DD. Возвращает тот же словарь, что и
    fetch_curve_from_moex, плюс проверяет, что MOEX вернул именно
    запрошенную дату (иначе — ValueError, чтобы не сохранить дубликат).
    """
    url = f"{MOEX_ZCYC_URL}?date={target_date.isoformat()}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
        payload = resp.json()

    params_block = _extract_params_block(payload)
    if params_block is None:
        raise ValueError(
            f"MOEX returned no curve params for {target_date.isoformat()}"
        )

    trade_date_str = params_block.get("TRADEDATE") or params_block.get("tradedate") or params_block.get("trade_date")
    if not trade_date_str:
        raise ValueError(
            f"MOEX response has no TRADEDATE for {target_date.isoformat()}"
        )
    from datetime import datetime
    trade_date = datetime.strptime(trade_date_str, "%Y-%m-%d").date()
    if trade_date != target_date:
        raise ValueError(
            f"MOEX has no curve for {target_date.isoformat()} "
            f"(returned trade_date={trade_date.isoformat()})"
        )

    result = {"trade_date": trade_date}
    for name in ("b1", "b2", "b3", "t1"):
        key = name.upper()
        if key not in params_block:
            raise ValueError(f"Missing param {key} in MOEX response")
        result[name] = float(params_block[key])

    for i in range(1, 10):
        key = f"G{i}"
        if key in params_block and params_block[key] is not None:
            result[f"g{i}"] = float(params_block[key])

    return result


def main() -> int:
    try:
        log("0/5", "init_db (create tables if missing)")
        init_db()

        with SessionLocal() as session:
            log("0/5", "ensure default scenarios")
            ensure_default_scenarios(session)

            target_date = _pick_target_date(session)
            log("1/5", f"target_date = {target_date}")

            log("2/5", "fetching MOEX curve...")
            params = _fetch_curve_for_date(target_date)
            trade_date = params.pop("trade_date")
            log("2/5", f"trade_date = {trade_date}")
            log("2/5", f"params = b1={params['b1']}, b2={params['b2']}, "
                       f"b3={params['b3']}, t1={params['t1']}")

            log("3/5", "creating snapshot...")
            snap = curve_repo.create_snapshot(
                session, trade_date=trade_date, params=params
            )
            log("3/5", f"snapshot id = {snap.id}")

            log("4/5", "building base curve (Nelson-Siegel)...")
            base_points = build_base_curve(params)
            curve_repo.save_base_points(session, snap.id, base_points)
            types = {}
            for p in base_points:
                types[p["point_type"]] = types.get(p["point_type"], 0) + 1
            log("4/5", f"{len(base_points)} points saved")
            log("4/5", f"point_types: {types}")

            log("5/5", "applying scenarios...")
            scenarios = scenario_repo.list_scenarios(session, only_active=True)
            for sc in scenarios:
                shift_map = scenario_repo.get_shift_map(session, sc.id)
                shifted = apply_shift(base_points, shift_map)
                curve_repo.save_shifted_points(session, snap.id, sc.id, shifted)
                log("5/5", f"  {sc.code}: {len(shifted)} points")

            curve_repo.mark_snapshot_status(session, snap.id, "built")
            log("5/5", f"done. snapshot id = {snap.id}, trade_date = {trade_date}")

        return 0
    except Exception:
        log("ERROR", "pipeline failed")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())