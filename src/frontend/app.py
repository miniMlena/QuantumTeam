"""
Витрина IRRBB: сценарии, кривая до/после сдвига, NPV/NII, ЭКпрбк, экспорт.
Запуск: streamlit run app.py
"""
import os

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1")

st.set_page_config(page_title="IRRBB: ЭКпрбк", layout="wide")


def load(path: str):
    """GET к API. При ошибке показываем сообщение и останавливаем страницу."""
    try:
        response = httpx.get(f"{API_URL}{path}", timeout=30)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as error:
        st.error(f"API вернул ошибку {error.response.status_code}: {error.response.text}")
    except httpx.HTTPError as error:
        st.error(f"Не удалось подключиться к API ({API_URL}): {error}")
    st.stop()


def to_csv(table: pd.DataFrame) -> bytes:
    return table.to_csv(index=False).encode("utf-8-sig")   # utf-8-sig: Excel читает кириллицу


st.title("Стресс-тестирование IRRBB: непараллельные сдвиги")

results = load("/results")
scenarios = results["scenarios"]
capital = results["economic_capital"]

# --- верхние показатели -------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Дата кривой", results["trade_date"])
col2.metric("NPV базовый", f"{results['base_npv']:,.1f}")
col3.metric("NII базовый (12 мес.)", f"{results['base_nii']:,.1f}")
if capital:
    col4.metric("ЭКпрбк (мин. ΔNPV)", f"{capital['value']:,.1f}", help=capital["scenario_name"])
    st.caption(f"Худший сценарий: **{capital['scenario_name']}** ({capital['scenario_code']})")

tab_scenarios, tab_curve, tab_portfolio = st.tabs(["Сценарии", "Кривая", "Портфель"])

# --- таблица сценариев --------------------------------------------------
with tab_scenarios:
    scenarios_table = pd.DataFrame([
        {
            "Код": item["code"],
            "Сценарий": item["name"],
            "Тип": item["scenario_type"],
            "NPV": item["npv"],
            "ΔNPV": item["delta_npv"],
            "NII": item["nii"],
            "ΔNII": item["delta_nii"],
        }
        for item in scenarios
    ])
    worst_code = capital["scenario_code"] if capital else None
    st.dataframe(
        scenarios_table.style
        .format({"NPV": "{:,.1f}", "ΔNPV": "{:,.1f}", "NII": "{:,.1f}", "ΔNII": "{:,.1f}"})
        .apply(lambda row: ["background-color: #ffe0e0"] * len(row)
               if row["Код"] == worst_code else [""] * len(row), axis=1),
        use_container_width=True, hide_index=True,
    )
    st.download_button(
        "Скачать результаты (CSV)", to_csv(scenarios_table),
        file_name="irrbb_results.csv", mime="text/csv",
    )

# --- кривая до/после сдвига --------------------------------------------
with tab_curve:
    names = {item["name"]: item for item in scenarios}
    chosen_name = st.selectbox("Сценарий", list(names), index=0)
    chosen = names[chosen_name]

    curve_table = pd.DataFrame(chosen["curve"])
    min_tenor = int(curve_table["tenor_months"].min())
    max_tenor = int(curve_table["tenor_months"].max())
    tenor_from, tenor_to = st.slider(
        "Фильтр по тенорам, мес.", min_tenor, max_tenor, (min_tenor, max_tenor)
    )
    curve_table = curve_table[curve_table["tenor_months"].between(tenor_from, tenor_to)]

    figure = go.Figure()
    figure.add_scatter(x=curve_table["tenor_months"], y=curve_table["base_rate"],
                       mode="lines+markers", name="Базовая кривая")
    figure.add_scatter(x=curve_table["tenor_months"], y=curve_table["shifted_rate"],
                       mode="lines+markers", name=f"После сдвига: {chosen_name}")
    figure.update_layout(xaxis_title="Тенор, мес.", yaxis_title="Ставка, %",
                         legend=dict(orientation="h"), height=450)
    st.plotly_chart(figure, use_container_width=True)

    curve_table["shift_bp"] = (curve_table["shifted_rate"] - curve_table["base_rate"]) * 100
    st.dataframe(
        curve_table.rename(columns={
            "tenor_months": "Тенор, мес.", "base_rate": "Базовая, %",
            "shifted_rate": "Сдвинутая, %", "shift_bp": "Сдвиг, б.п.",
        }),
        use_container_width=True, hide_index=True,
    )
    st.download_button(
        "Скачать кривую (CSV)", to_csv(curve_table),
        file_name=f"curve_{chosen['code']}.csv", mime="text/csv",
    )

# --- портфель -----------------------------------------------------------
with tab_portfolio:
    positions_table = pd.DataFrame(load("/portfolio")).rename(columns={
        "id": "ID", "name": "Позиция", "amount": "Сумма", "rate": "Ставка, %",
        "maturity_months": "Срок, мес.", "repricing_months": "Пересмотр, мес.",
    })
    st.dataframe(positions_table, use_container_width=True, hide_index=True)
