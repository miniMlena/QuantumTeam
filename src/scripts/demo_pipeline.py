"""
Демо-пайплайн: загрузка MOEX и расчёт кривых через общий конвейер.
Запускается вручную, печатает прогресс в stdout.
"""
import sys
import traceback

from db.engine import SessionLocal, init_db
from db.repositories import portfolio_repo
from services.curve_pipeline import build_curves, load_curve


def log(step: str, msg: str = ""):
    print(f"[{step}] {msg}", flush=True)


def main() -> int:
    try:
        log("0/3", "init_db (create tables if missing)")
        init_db()

        with SessionLocal() as session:
            log("1/3", "fetching MOEX curve...")
            snap = load_curve(session)
            log("1/3", f"snapshot id = {snap.id}, trade_date = {snap.trade_date}")

            log("2/3", "building curves...")
            for code, points in build_curves(session, snap).items():
                log("2/3", f"  {code}: {points} points")

            created = portfolio_repo.ensure_demo_portfolio(session)
            log("3/3", f"demo portfolio: {created} positions created")
            log("3/3", f"done. snapshot id = {snap.id}")

        return 0
    except Exception:
        log("ERROR", "pipeline failed")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())