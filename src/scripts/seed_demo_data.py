"""
Заполнение БД для демо и разработки фронта:
  1. шесть стандартных сценариев IRRBB (старые придуманные сценарии удаляются);
  2. тестовый портфель банка (если портфель пустой);
  3. демо-кривая из Excel "3108" (только с флагом --demo-curve, без MOEX).

Запуск:  python -m scripts.seed_demo_data [--demo-curve]
"""
import sys
from datetime import date

from sqlalchemy import select

from db.engine import SessionLocal, init_db
from db.models import CurveSnapshot
from db.repositories import curve_repo, scenario_repo, portfolio_repo
from domain.curve.irrbb_scenarios import IRRBB_SCENARIOS, build_shifts

SCENARIO_MARKER = "IRRBB BCBS d368 (parallel=400, short=500, long=300 bp)"
OLD_DEMO_CODES = ["twist_steep", "curvature"]   # из старого demo_pipeline

# Тестовый портфель, суммы в млн руб. (актив "+", пассив "-")
DEMO_POSITIONS = [
    # name, amount, rate %, maturity_months, repricing_months
    ("Кредиты юрлицам (фикс)", 1000, 15.0, 60, 60),
    ("Ипотека", 800, 9.0, 120, 120),
    ("ОФЗ", 500, 12.0, 84, 84),
    ("Кредиты юрлицам (плавающая ставка)", 600, 17.0, 36, 3),
    ("Депозиты физлиц", -900, 12.0, 12, 12),
    ("Депозиты юрлиц", -500, 8.0, 6, 1),
    ("Выпущенные облигации", -400, 13.0, 36, 36),
    ("Межбанковские займы", -300, 15.0, 3, 3),
]

# Кривая из Excel "3108": (тенор в месяцах, ставка в %)
DEMO_CURVE = [
    (0, 13.27), (1, 13.27), (2, 13.27), (5, 13.30), (8, 13.44), (11, 13.63),
    (15, 14.04), (21, 14.45), (30, 15.04), (42, 15.35), (54, 15.66),
    (66, 15.92), (78, 15.92), (90, 15.94), (102, 15.96), (114, 16.04),
    (150, 16.13), (210, 16.20), (300, 16.34),
]


def seed_scenarios(session):
    for code in OLD_DEMO_CODES:
        old = scenario_repo.get_scenario_by_code(session, code)
        if old is not None:
            session.delete(old)
            session.commit()

    for code, name, scenario_type in IRRBB_SCENARIOS:
        existing = scenario_repo.get_scenario_by_code(session, code)
        if existing is not None and existing.description != SCENARIO_MARKER:
            session.delete(existing)   # старая версия из demo_pipeline
            session.commit()
            existing = None
        if existing is None:
            scenario_repo.create_scenario(
                session, code=code, name=name, scenario_type=scenario_type,
                is_regulatory=True, description=SCENARIO_MARKER,
                shifts=build_shifts(code),
            )
            print(f"[scenarios] created: {code}")


def seed_portfolio(session):
    if portfolio_repo.list_positions(session):
        print("[portfolio] already filled, skip")
        return
    for name, amount, rate, maturity_months, repricing_months in DEMO_POSITIONS:
        portfolio_repo.create_position(
            session, name=name, amount=amount, rate=rate,
            maturity_months=maturity_months, repricing_months=repricing_months,
        )
    print(f"[portfolio] created {len(DEMO_POSITIONS)} positions")


def seed_demo_curve(session):
    existing = session.scalar(
        select(CurveSnapshot).where(CurveSnapshot.source == "excel_demo")
    )
    if existing is not None:
        print(f"[curve] demo snapshot already exists (id={existing.id})")
        return
    snapshot = CurveSnapshot(
        trade_date=date(2026, 8, 31), source="excel_demo",
        b1=0, b2=0, b3=0, t1=0, status="built",
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    curve_repo.save_base_points(session, snapshot.id, [
        {"tenor_months": months, "rate": rate, "point_type": "observed"}
        for months, rate in DEMO_CURVE
    ])
    print(f"[curve] demo snapshot created (id={snapshot.id})")


def main() -> int:
    init_db()
    with SessionLocal() as session:
        seed_scenarios(session)
        seed_portfolio(session)
        if "--demo-curve" in sys.argv:
            seed_demo_curve(session)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
