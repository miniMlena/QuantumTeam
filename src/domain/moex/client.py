"""
Клиент MOEX ISS. Скачивает параметры кривой бескупонной доходности (ZCYC).
"""
from datetime import datetime
import httpx

MOEX_ZCYC_URL = "https://iss.moex.com/iss/engines/stock/zcyc/securities.json"
CONNECT_TIMEOUT_SECONDS = 3.0
CONNECT_RETRIES = 3


def fetch_curve_from_moex(timeout: float = 15.0) -> dict:
    """
    Возвращает словарь:
      {
        "trade_date": date,
        "b1": float, "b2": float, "b3": float, "t1": float,
        "g1": float, ..., "g9": float,
      }
    Бросает httpx.HTTPError при сетевых проблемах,
    ValueError — если ответ не содержит ожидаемых полей.
    """
    # Соединение с MOEX иногда зависает: ждём его недолго и подключаемся заново
    with httpx.Client(
        timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT_SECONDS),
        transport=httpx.HTTPTransport(retries=CONNECT_RETRIES),
    ) as client:
        resp = client.get(MOEX_ZCYC_URL, params={"iss.only": "params", "iss.meta": "off"})
        resp.raise_for_status()
        payload = resp.json()

    params_block = _extract_params_block(payload)
    if params_block is None:
        raise ValueError("MOEX response does not contain curve params")

    trade_date_str = params_block.get("tradedate")
    if not trade_date_str:
        raise ValueError("Missing tradedate in MOEX response")

    result = {"trade_date": datetime.strptime(trade_date_str, "%Y-%m-%d").date()}
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


def _extract_params_block(payload: dict) -> dict | None:
    """
    MOEX ISS возвращает данные в формате: {"params": {"columns": [...], "data": [[...]]}}
    Превращаем первую строку data в словарь по columns.
    """
    block = payload.get("params")
    if not block:
        return None
    columns = block.get("columns") or []
    data = block.get("data") or []
    if not data:
        return None
    return dict(zip(columns, data[0]))