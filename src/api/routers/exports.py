
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from api.deps import get_db
from services.curve_export import (
    export_moex_curves,
    export_calculator_demo,
)

router = APIRouter(prefix="/exports", tags=["exports"])


def _csv_response(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
            "Cache-Control": "no-store",
        },
    )


@router.get("/curves/{snapshot_id}/moex.csv")
def download_moex_curves(
    snapshot_id: int,
    db: Session = Depends(get_db),
):
    """
    Реальные базовая и стрессовые кривые MOEX.
    Данные по тенорам, не прогноз индикатора.
    """
    try:
        content = export_moex_curves(db, snapshot_id)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 409
        raise HTTPException(
            status_code=status, detail=message
        ) from exc

    return _csv_response(
        content,
        f"moex_curves_{snapshot_id}.csv",
    )


@router.get("/curves/{snapshot_id}/calculator-demo.csv")
def download_calculator_demo(
    snapshot_id: int,
    months: int = Query(default=12, ge=1, le=360),
    db: Session = Depends(get_db),
):
    """
    DEMO ONLY: CSV-контракт калькулятора.

    TODO: заменить временную методику прогноза
    после согласования с командами.
    """
    try:
        content = export_calculator_demo(
            db, snapshot_id, months
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 409
        raise HTTPException(
            status_code=status, detail=message
        ) from exc

    return _csv_response(
        content,
        f"calculator_DEMO_{snapshot_id}.csv",
    )
