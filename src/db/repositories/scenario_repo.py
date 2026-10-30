from sqlalchemy import select
from sqlalchemy.orm import Session
from db.models import Scenario, ScenarioShift


def list_scenarios(session: Session, only_active: bool = True) -> list[Scenario]:
    stmt = select(Scenario)
    if only_active:
        stmt = stmt.where(Scenario.is_active.is_(True))
    return list(session.scalars(stmt))


def get_scenario(session: Session, scenario_id: int) -> Scenario | None:
    return session.get(Scenario, scenario_id)


def get_scenario_by_code(session: Session, code: str) -> Scenario | None:
    return session.scalar(select(Scenario).where(Scenario.code == code))


def create_scenario(
    session: Session,
    *,
    code: str,
    name: str,
    scenario_type: str,
    is_regulatory: bool,
    description: str | None,
    shifts: list[dict],
) -> Scenario:
    scenario = Scenario(
        code=code, name=name, scenario_type=scenario_type,
        is_regulatory=is_regulatory, description=description,
    )
    scenario.shifts = [
        ScenarioShift(tenor_months=s["tenor_months"], shift_bp=s["shift_bp"])
        for s in shifts
    ]
    session.add(scenario)
    session.commit()
    session.refresh(scenario)
    return scenario


def get_shift_map(session: Session, scenario_id: int) -> dict[int, float]:
    """Возвращает {tenor_months: shift_bp} для сценария."""
    rows = session.scalars(
        select(ScenarioShift).where(ScenarioShift.scenario_id == scenario_id)
    )
    return {r.tenor_months: float(r.shift_bp) for r in rows}

def ensure_default_scenarios(session: Session) -> None:
    """Создать отсутствующие IRRBB RUB сценарии, сохраняя пользовательские."""
    from domain.curve.scenarios import default_scenarios

    for definition in default_scenarios():
        if get_scenario_by_code(session, definition["code"]) is None:
            create_scenario(session, **definition)
