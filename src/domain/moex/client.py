"""Клиент MOEX ISS. Параметры B/G сохраняются в исходных базисных пунктах."""
from datetime import date
import httpx

from domain.curve.validation import finite_number

MOEX_ZCYC_URL = "https://iss.moex.com/iss/engines/stock/zcyc/securities.json"


def fetch_curve_from_moex(timeout: float = 15.0) -> dict:
    """Загрузить датированные параметры; не подменять дату старых данных сегодняшней."""
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(MOEX_ZCYC_URL, params={"iss.only": "params", "iss.meta": "off"})
        resp.raise_for_status()
        payload = resp.json()
    return parse_curve_params(payload)


def parse_curve_params(payload: dict) -> dict:
    block = _extract_params_block(payload)
    if block is None:
        raise ValueError("MOEX response does not contain curve params")
    trade_date = block.get("TRADEDATE") or block.get("TRADE_DATE")
    if not trade_date:
        raise ValueError("Missing TRADEDATE in MOEX response")
    result = {"trade_date": date.fromisoformat(trade_date)}
    for name in ("b1", "b2", "b3", "t1"):
        result[name] = finite_number(block.get(name.upper()), name)
    if result["t1"] <= 0:
        raise ValueError("t1 must be positive")
    for i in range(1, 10):
        value = block.get(f"G{i}")
        result[f"g{i}"] = 0.0 if value is None else finite_number(value, f"g{i}")
    return result


def _extract_params_block(payload: dict) -> dict | None:
    block = payload.get("params")
    if not block:
        return None
    columns, data = block.get("columns") or [], block.get("data") or []
    if not data:
        return None
    if len(columns) != len(data[0]):
        raise ValueError("MOEX params columns and row have different lengths")
    return {str(key).upper(): value for key, value in zip(columns, data[0])}
