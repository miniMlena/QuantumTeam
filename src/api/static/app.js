const API = "/api/v1";
const SVG_NS = "http://www.w3.org/2000/svg";
const CHART = { width: 960, height: 360, top: 14, right: 16, bottom: 34, left: 48 };

const SCENARIO_NAMES = {
  parallel_up: "Параллельный сдвиг вверх",
  parallel_down: "Параллельный сдвиг вниз",
  short_up: "Рост коротких ставок",
  short_down: "Снижение коротких ставок",
  steepener: "Steepener: короткие вниз, длинные вверх",
  flattener: "Flattener: короткие вверх, длинные вниз",
};

const el = (id) => document.getElementById(id);
const fmt = (value, digits = 2) => value.toLocaleString("ru-RU", {
  minimumFractionDigits: digits, maximumFractionDigits: digits,
});
const scenarioName = (scenario) => SCENARIO_NAMES[scenario.code] || scenario.name;

let snapshot = null;
let basePoints = [];
let requestId = 0;

async function request(path, options) {
  const response = await fetch(API + path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(body.detail || `Ошибка сервера: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function setMessage(text, isError = false) {
  el("message").textContent = text;
  el("message").classList.toggle("error", isError);
}

function svgNode(name, attrs = {}, parent = null) {
  const node = document.createElementNS(SVG_NS, name);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  if (parent) parent.append(node);
  return node;
}

function niceTicks(min, max) {
  const step = [0.5, 1, 2, 5].find((s) => (max - min) / s <= 6) || 10;
  const ticks = [];
  for (let t = Math.floor(min / step) * step; t <= Math.ceil(max / step) * step + 1e-9; t += step) {
    ticks.push(Number(t.toFixed(2)));
  }
  return ticks;
}

function renderChart(rows) {
  const container = el("chart");
  container.replaceChildren();
  const plotRight = CHART.width - CHART.right;
  const plotBottom = CHART.height - CHART.bottom;

  const values = rows.flatMap((r) => [r.base, r.scenario]);
  const ticks = niceTicks(Math.min(...values), Math.max(...values));
  const minY = ticks[0];
  const maxY = ticks[ticks.length - 1];
  // Бакеты разной длины идут равным шагом: иначе короткие сроки слились бы в одну точку
  const x = (i) => CHART.left + i * (plotRight - CHART.left) / (rows.length - 1);
  const y = (v) => plotBottom - (v - minY) * (plotBottom - CHART.top) / (maxY - minY);

  const svg = svgNode("svg", {
    viewBox: `0 0 ${CHART.width} ${CHART.height}`,
    role: "img",
    "aria-label": "График базовой кривой и кривой выбранного сценария по бакетам",
  }, container);

  ticks.forEach((tick) => {
    svgNode("line", {
      class: "grid-line", x1: CHART.left, x2: plotRight, y1: y(tick), y2: y(tick),
    }, svg);
    const label = svgNode("text", {
      class: "axis-text", x: CHART.left - 8, y: y(tick) + 4, "text-anchor": "end",
    }, svg);
    label.textContent = tick;
  });

  rows.forEach((row, i) => {
    const label = svgNode("text", {
      class: "axis-text", x: x(i), y: plotBottom + 20, "text-anchor": "middle",
    }, svg);
    label.textContent = row.code;
  });

  const path = (key) => rows
    .map((row, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(row[key]).toFixed(1)}`)
    .join("");
  svgNode("path", { class: "series series-base", d: path("base") }, svg);
  svgNode("path", { class: "series series-scenario", d: path("scenario") }, svg);

  const crosshair = svgNode("line", {
    class: "crosshair", y1: CHART.top, y2: plotBottom, visibility: "hidden",
  }, svg);
  const baseMarker = svgNode("circle", {
    class: "marker marker-base", r: 4, visibility: "hidden",
  }, svg);
  const scenarioMarker = svgNode("circle", {
    class: "marker marker-scenario", r: 4, visibility: "hidden",
  }, svg);

  const tooltip = el("tooltip");

  function showAt(clientX) {
    const box = svg.getBoundingClientRect();
    const svgX = (clientX - box.left) * CHART.width / box.width;
    const step = (plotRight - CHART.left) / (rows.length - 1);
    const i = Math.max(0, Math.min(rows.length - 1, Math.round((svgX - CHART.left) / step)));
    const row = rows[i];

    crosshair.setAttribute("x1", x(i));
    crosshair.setAttribute("x2", x(i));
    baseMarker.setAttribute("cx", x(i));
    baseMarker.setAttribute("cy", y(row.base));
    scenarioMarker.setAttribute("cx", x(i));
    scenarioMarker.setAttribute("cy", y(row.scenario));
    [crosshair, baseMarker, scenarioMarker].forEach((n) => n.setAttribute("visibility", "visible"));

    tooltip.replaceChildren();
    const title = document.createElement("div");
    title.className = "title";
    title.textContent = `Бакет ${row.code}, срок ${fmt(row.tenor, 2)} лет`;
    tooltip.append(title);
    [["key-base", row.base, "%, база"], ["key-scenario", row.scenario, "%, сценарий"]]
      .forEach(([keyClass, value, label]) => {
        const line = document.createElement("div");
        const key = document.createElement("span");
        key.className = `key ${keyClass}`;
        const strong = document.createElement("strong");
        strong.textContent = fmt(value);
        line.append(key, strong, label);
        tooltip.append(line);
      });
    tooltip.hidden = false;

    const section = tooltip.parentElement.getBoundingClientRect();
    const scale = box.width / CHART.width;
    const left = box.left - section.left + x(i) * scale;
    const flip = left + tooltip.offsetWidth + 18 > section.width;
    tooltip.style.left = `${flip ? left - tooltip.offsetWidth - 12 : left + 12}px`;
    tooltip.style.top = `${box.top - section.top + 8}px`;
  }

  svg.addEventListener("pointermove", (event) => showAt(event.clientX));
  svg.addEventListener("pointerleave", () => {
    tooltip.hidden = true;
    [crosshair, baseMarker, scenarioMarker].forEach((n) => n.setAttribute("visibility", "hidden"));
  });
}

function renderTable(rows) {
  el("rows").replaceChildren(...rows.map((row) => {
    const tr = document.createElement("tr");
    const cells = [
      row.code, fmt(row.tenor, 4), fmt(row.base), fmt(row.scenario),
      `${row.shift > 0 ? "+" : ""}${fmt(row.shift, 1)}`,
    ];
    cells.forEach((text, i) => {
      const td = document.createElement("td");
      if (i) td.className = "num";
      td.textContent = text;
      tr.append(td);
    });
    return tr;
  }));
}

async function showScenario() {
  const select = el("scenario");
  if (!snapshot || !select.value) return;
  const current = ++requestId;
  const shifted = await request(`/curves/${snapshot.id}/scenarios/${select.value}`);
  if (current !== requestId) return;

  const byCode = new Map(shifted.map((p) => [p.bucket_code, p]));
  const rows = basePoints.map((p) => ({
    code: p.bucket_code,
    tenor: Number(p.tenor_years),
    base: Number(p.rate),
    scenario: Number(byCode.get(p.bucket_code).shifted_rate),
    shift: Number(byCode.get(p.bucket_code).shift_bp),
  }));
  el("legend-scenario").textContent = select.options[select.selectedIndex].text;
  renderChart(rows);
  renderTable(rows);
}

async function loadScenarios() {
  const select = el("scenario");
  const selected = select.value;
  const scenarios = await request("/scenarios");
  select.replaceChildren(...scenarios.map((scenario) => {
    const option = document.createElement("option");
    option.value = scenario.id;
    option.textContent = scenarioName(scenario);
    return option;
  }));
  if ([...select.options].some((option) => option.value === selected)) select.value = selected;
  select.disabled = scenarios.length === 0;
}

async function loadLatest() {
  try {
    snapshot = await request("/curves/latest");
  } catch (error) {
    if (error.status !== 404) throw error;
    snapshot = null;
    el("snapshot").textContent = "Кривых пока нет";
    const hint = document.createElement("p");
    hint.textContent = "Нажмите «Рассчитать MOEX», чтобы загрузить кривую";
    el("chart").replaceChildren(hint);
    return;
  }
  const date = new Date(`${snapshot.trade_date}T00:00:00`).toLocaleDateString("ru-RU");
  el("snapshot").textContent = `Кривая MOEX на ${date}, 19 бакетов, сценарии Basel для рубля`;
  basePoints = await request(`/curves/${snapshot.id}/base`);
  await loadScenarios();
  await showScenario();
}

async function calculate() {
  const button = el("calculate");
  button.disabled = true;
  setMessage("Загружаем кривую и считаем сценарии…");
  try {
    await request("/curves/calculate", { method: "POST" });
    await loadLatest();
    setMessage("Готово");
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    button.disabled = false;
  }
}

el("calculate").addEventListener("click", calculate);
el("scenario").addEventListener("change", () => {
  showScenario().catch((error) => setMessage(error.message, true));
});
loadLatest().catch((error) => setMessage(error.message, true));
