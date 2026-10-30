"use strict";

const byId = (id) => document.getElementById(id);
const snapshotSelect = byId("snapshot"), scenarioSelect = byId("scenario");
const controls = [snapshotSelect, scenarioSelect, byId("refresh"), byId("calculate")];
const number = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const names = {
  parallel_up: "Параллельный вверх", parallel_down: "Параллельный вниз",
  steepener: "Увеличение наклона", flattener: "Уменьшение наклона",
  short_up: "Короткие ставки вверх", short_down: "Короткие ставки вниз",
};

async function request(path, options) {
  const response = await fetch("/api/v1" + path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "Ошибка сервера (" + response.status + ")");
  }
  return response.json();
}

function setOptions(select, items, label, emptyLabel, preferred) {
  select.replaceChildren(...items.map((item) => new Option(label(item), item.id)));
  if (!items.length) select.add(new Option(emptyLabel, ""));
  if (items.some((item) => String(item.id) === String(preferred))) select.value = preferred;
}

async function busy(message, action) {
  controls.forEach((control) => { control.disabled = true; });
  byId("status").textContent = message;
  byId("error").hidden = true;
  try {
    await action();
  } catch (error) {
    render([], []);
    byId("status").textContent = "Не удалось обновить данные";
    byId("error").textContent = error.message === "Failed to fetch"
      ? "Нет соединения с сервером. Попробуйте обновить страницу." : error.message;
    byId("error").hidden = false;
  } finally {
    controls.forEach((control) => { control.disabled = false; });
    snapshotSelect.disabled = !snapshotSelect.value;
    scenarioSelect.disabled = !scenarioSelect.value;
  }
}

async function loadOptions(preferredSnapshot) {
  const [snapshots, scenarios] = await Promise.all([request("/curves"), request("/scenarios")]);
  setOptions(snapshotSelect, snapshots, (s) => s.trade_date + " · № " + s.id,
    "Нет расчётов", preferredSnapshot ?? snapshotSelect.value);
  setOptions(scenarioSelect, scenarios, (s) => s.code.startsWith("irrbb_rub_")
    ? (names[s.scenario_type] ?? s.name) + " · RUB" : s.name, "Нет сценариев", scenarioSelect.value);
}

async function loadPoints() {
  if (!snapshotSelect.value) {
    render([], []);
    byId("status").textContent = "Пока нет расчётов. Нажмите «Рассчитать MOEX».";
    return;
  }
  const root = "/curves/" + snapshotSelect.value;
  const [base, shifted] = await Promise.all([
    request(root + "/base"), scenarioSelect.value ? request(root + "/scenarios/" + scenarioSelect.value) : Promise.resolve([]),
  ]);
  render(base, shifted);
  byId("status").textContent = base.length + " точек · " + snapshotSelect.selectedOptions[0].textContent
    + (scenarioSelect.value && !shifted.length ? " · Для этого сценария ещё нет сохранённых точек" : "");
}

function render(base, shifted) {
  const shiftedByTenor = new Map(shifted.map((p) => [p.tenor_months, p]));
  const rows = base.map((point) => {
    const scenario = shiftedByTenor.get(point.tenor_months), row = document.createElement("tr");
    const values = [
      point.tenor_months + " мес.", number.format(Number(point.rate) * 100),
      scenario ? number.format(Number(scenario.shifted_rate) * 100) : "—",
      scenario ? (Number(scenario.shift_bp) > 0 ? "+" : "") + number.format(Number(scenario.shift_bp)) : "—",
    ];
    values.forEach((value, index) => {
      const cell = document.createElement("td"); cell.textContent = value;
      if (index === 3 && scenario) cell.className = Number(scenario.shift_bp) >= 0 ? "positive" : "negative";
      row.append(cell);
    });
    return row;
  });
  byId("points").replaceChildren(...rows);
  if (!rows.length) {
    const row = document.createElement("tr"), cell = document.createElement("td");
    cell.colSpan = 4; cell.textContent = "Нет данных"; cell.className = "muted";
    row.append(cell); byId("points").append(row);
  }
  drawChart(base, shifted);
}

function svgNode(tag, attributes, text) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  if (text !== undefined) element.textContent = text;
  return element;
}

function drawChart(base, shifted) {
  const svg = byId("chart"); svg.replaceChildren();
  svg.toggleAttribute("hidden", !base.length); byId("empty").hidden = Boolean(base.length);
  if (!base.length) return;
  const values = [...base.map((p) => Number(p.rate) * 100), ...shifted.map((p) => Number(p.shifted_rate) * 100)];
  const min = Math.min(...values), max = Math.max(...values);
  const padding = Math.max((max - min) * 0.15, 0.2), low = min - padding, high = max + padding;
  const maxTenor = Math.max(...base.map((p) => p.tenor_months), ...shifted.map((p) => p.tenor_months), 1);
  const x = (months) => 64 + Number(months) / maxTenor * 810;
  const y = (rate) => 280 - (Number(rate) * 100 - low) / (high - low) * 250;
  for (let i = 0; i <= 5; i++) {
    const value = low + (high - low) * i / 5, pos = y(value / 100);
    svg.append(svgNode("line", { x1: 64, y1: pos, x2: 874, y2: pos, stroke: "#e5ebf0" }));
    svg.append(svgNode("text", { x: 53, y: pos + 4, "text-anchor": "end", fill: "#637484", "font-size": 12 }, number.format(value)));
  }
  for (let i = 0; i <= 6; i++) {
    const months = maxTenor * i / 6;
    svg.append(svgNode("text", { x: x(months), y: 304, "text-anchor": "middle", fill: "#637484", "font-size": 12 },
      new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(months / 12)));
  }
  svg.append(svgNode("text", { x: 874, y: 327, "text-anchor": "end", fill: "#637484", "font-size": 12 }, "Срок, лет"));
  svg.append(svgNode("text", { x: 64, y: 15, fill: "#637484", "font-size": 12 }, "% годовых"));
  [[base, "rate", "#2469a8", "Базовая"], [shifted, "shifted_rate", "#d67a28", "Сценарий"]].forEach(([points, key, color, label]) => {
    const ordered = [...points].sort((a, b) => a.tenor_months - b.tenor_months);
    if (!ordered.length) return;
    svg.append(svgNode("polyline", { points: ordered.map((p) => x(p.tenor_months) + "," + y(p[key])).join(" "), fill: "none", stroke: color, "stroke-width": 2.5 }));
    ordered.forEach((p) => {
      const circle = svgNode("circle", { cx: x(p.tenor_months), cy: y(p[key]), r: 4, fill: color, stroke: "white", "stroke-width": 1.5 });
      circle.append(svgNode("title", {}, label + ": " + p.tenor_months + " мес. — " + number.format(Number(p[key]) * 100) + "%"));
      svg.append(circle);
    });
  });
}

byId("refresh").addEventListener("click", () => busy("Загрузка данных…", async () => { await loadOptions(); await loadPoints(); }));
byId("calculate").addEventListener("click", () => busy("Загрузка MOEX и расчёт сценариев…", async () => {
  const result = await request("/curves/rebuild", { method: "POST" });
  if (result.status !== "ok") throw new Error("Расчёт не завершён. Попробуйте ещё раз.");
  await loadOptions(result.snapshot_id); await loadPoints();
}));
[snapshotSelect, scenarioSelect].forEach((select) => select.addEventListener("change", () => busy("Загрузка кривых…", loadPoints)));
busy("Загрузка данных…", async () => { await loadOptions(); await loadPoints(); });
