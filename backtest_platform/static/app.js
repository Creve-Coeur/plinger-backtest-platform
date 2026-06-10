const basketLabels = {
  equity: "股票",
  commodity: "商品",
  convertible: "可转债",
  pure_bond: "纯债",
};

const moduleLabels = {
  fund: "基金",
  index: "指数",
  enhanced: "增强",
};

const rebalanceTypeLabels = {
  initial: "初始建仓",
  stage_change: "Stage变化",
  three_month: "三个月再平衡",
  ma20_exit: "MA20退出",
  ma20_reentry: "MA20恢复",
  splice_switch: "拼接切换",
};

const colors = {
  strategy: "#c94a4a",
  theory: "#7a8795",
  benchmark: "#17202a",
  equity: "#c94a4a",
  commodity: "#b78318",
  convertible: "#7758a6",
  pureBond: "#4f7896",
  pure_bond: "#4f7896",
};

const state = {
  grouped: { fund: [], index: [], enhanced: [] },
  assetsById: new Map(),
  activeTab: "fund",
  baskets: {
    equity: [],
    commodity: [],
    convertible: [],
    pure_bond: [],
  },
  spliceBaskets: {
    equity: [],
    commodity: [],
    convertible: [],
    pure_bond: [],
  },
  defaults: null,
  result: null,
};

const els = {
  assetCount: document.getElementById("assetCount"),
  assetList: document.getElementById("assetList"),
  searchInput: document.getElementById("searchInput"),
  runBtn: document.getElementById("runBtn"),
  resetBtn: document.getElementById("resetBtn"),
  clearBtn: document.getElementById("clearBtn"),
  ma20Equity: document.getElementById("ma20Equity"),
  ma20Commodity: document.getElementById("ma20Commodity"),
  ma20Convertible: document.getElementById("ma20Convertible"),
  ma20ThreeDay: document.getElementById("ma20ThreeDay"),
  spliceToggle: document.getElementById("spliceToggle"),
  splicePool: document.getElementById("splicePool"),
  splicePanel: document.getElementById("splicePanel"),
  status: document.getElementById("status"),
  results: document.getElementById("results"),
  metrics: document.getElementById("metrics"),
  windowText: document.getElementById("windowText"),
  annualTable: document.getElementById("annualTable"),
  efficiencyTable: document.getElementById("efficiencyTable"),
  tradeTable: document.getElementById("tradeTable"),
  escapeTable: document.getElementById("escapeTable"),
};

init();

async function init() {
  wireEvents();
  try {
    const res = await fetch("/api/assets");
    if (!res.ok) throw new Error("资产库加载失败");
    const data = await res.json();
    state.grouped = data.groups;
    state.defaults = data.defaults;
    Object.values(state.grouped).flat().forEach((asset) => state.assetsById.set(asset.id, asset));
    resetDefaults();
    renderAssets();
    setStatus(
      `已加载 ${state.assetsById.size} 个资产；月度普林格信号 ${data.pring?.start || "-"} 至 ${data.pring?.end || "-"}，共 ${data.pring?.rows || 0} 条；数据源：${data.pring?.source || "-"}。`,
      "ok",
    );
  } catch (err) {
    setStatus(err.message || String(err), "error");
  }
}

function wireEvents() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.activeTab = tab.dataset.tab;
      document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab));
      renderAssets();
    });
  });

  els.searchInput.addEventListener("input", renderAssets);
  els.resetBtn.addEventListener("click", resetDefaults);
  els.clearBtn.addEventListener("click", clearBaskets);
  els.runBtn.addEventListener("click", runBacktest);
  els.spliceToggle.addEventListener("change", renderSplicePool);

  document.querySelectorAll(".dropzone").forEach((zone) => {
    zone.addEventListener("dragover", (event) => {
      event.preventDefault();
      zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("drag-over");
      const id = event.dataTransfer.getData("text/plain");
      if (id) addToBasket(id, zone.dataset.basket);
    });
  });

  document.querySelectorAll(".splice-dropzone").forEach((zone) => {
    zone.addEventListener("dragover", (event) => {
      event.preventDefault();
      zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("drag-over");
      const id = event.dataTransfer.getData("text/plain");
      if (id) addToSpliceBasket(id, zone.dataset.spliceBasket);
    });
  });

  window.addEventListener("resize", () => {
    if (state.result) renderCharts(state.result);
  });
}

function resetDefaults() {
  if (!state.defaults) return;
  els.spliceToggle.checked = false;
  state.spliceBaskets = emptyBaskets();
  state.baskets = {
    equity: (state.defaults.equity || []).filter(Boolean),
    commodity: (state.defaults.commodity || []).filter(Boolean),
    convertible: (state.defaults.convertible || []).filter(Boolean),
    pure_bond: (state.defaults.pure_bond || []).filter(Boolean),
  };
  renderBaskets();
  renderSplicePool();
}

function clearBaskets() {
  state.baskets = emptyBaskets();
  state.spliceBaskets = emptyBaskets();
  renderBaskets();
  renderSplicePool();
  setStatus("四类资产篮子已清空。", "");
}

function emptyBaskets() {
  return {
    equity: [],
    commodity: [],
    convertible: [],
    pure_bond: [],
  };
}

function renderAssets() {
  const query = els.searchInput.value.trim().toLowerCase();
  const assets = (state.grouped[state.activeTab] || []).filter((asset) => {
    const haystack = `${asset.code} ${asset.name}`.toLowerCase();
    return !query || haystack.includes(query);
  });

  els.assetCount.textContent = `${moduleLabels[state.activeTab]} ${assets.length} 个标的`;

  if (!assets.length) {
    els.assetList.innerHTML = `<div class="empty-state">${state.activeTab === "enhanced" ? "增强模块等待接入数据" : "没有匹配的标的"}</div>`;
    return;
  }

  els.assetList.innerHTML = "";
  assets.forEach((asset) => {
    const card = document.createElement("div");
    card.className = "asset-card";
    card.draggable = true;
    card.dataset.assetId = asset.id;
    card.innerHTML = `
      <div class="asset-name">
        <span>${escapeHtml(asset.name)}</span>
        <span class="module-pill">${moduleLabels[asset.module]}</span>
      </div>
      <div class="asset-code">${escapeHtml(asset.code)}</div>
      <div class="asset-dates">${asset.start} 至 ${asset.end}</div>
    `;
    card.addEventListener("dragstart", (event) => {
      card.classList.add("dragging");
      event.dataTransfer.setData("text/plain", asset.id);
    });
    card.addEventListener("dragend", () => card.classList.remove("dragging"));
    els.assetList.appendChild(card);
  });
}

function renderBaskets() {
  Object.entries(state.baskets).forEach(([basket, ids]) => {
    const zone = document.querySelector(`.dropzone[data-basket="${basket}"]`);
    zone.innerHTML = "";
    ids.forEach((id) => {
      const asset = state.assetsById.get(id);
      if (!asset) return;
      const item = document.createElement("div");
      item.className = "basket-item";
      item.draggable = true;
      item.innerHTML = `
        <div class="basket-main">
          <strong>${escapeHtml(asset.name)}</strong>
          <span>${escapeHtml(asset.code)} · ${moduleLabels[asset.module]}</span>
        </div>
        <button class="remove-btn" type="button" title="移除">×</button>
      `;
      item.addEventListener("dragstart", (event) => {
        event.dataTransfer.setData("text/plain", id);
      });
      item.querySelector("button").addEventListener("click", () => {
        state.baskets[basket] = state.baskets[basket].filter((assetId) => assetId !== id);
        renderBaskets();
      });
      zone.appendChild(item);
    });
  });
}

function renderSplicePool() {
  const enabled = els.spliceToggle.checked;
  els.splicePool.classList.toggle("hidden", !enabled);
  els.splicePanel.classList.toggle("active", enabled);
  document.querySelectorAll(".splice-dropzone").forEach((zone) => {
    const basket = zone.dataset.spliceBasket;
    zone.innerHTML = "";
    state.spliceBaskets[basket].forEach((id) => {
      const asset = state.assetsById.get(id);
      if (!asset) return;
      const item = document.createElement("div");
      item.className = "basket-item splice-item";
      item.draggable = true;
      item.innerHTML = `
        <div class="basket-main">
          <strong>${escapeHtml(asset.name)}</strong>
          <span>${escapeHtml(asset.code)} · ${moduleLabels[asset.module]}</span>
        </div>
        <button class="remove-btn" type="button" title="移除">×</button>
      `;
      item.addEventListener("dragstart", (event) => {
        event.dataTransfer.setData("text/plain", id);
      });
      item.querySelector("button").addEventListener("click", () => {
        state.spliceBaskets[basket] = state.spliceBaskets[basket].filter((assetId) => assetId !== id);
        renderSplicePool();
      });
      zone.appendChild(item);
    });
  });
}

function addToBasket(id, basket) {
  if (!state.assetsById.has(id)) return;
  Object.keys(state.baskets).forEach((key) => {
    state.baskets[key] = state.baskets[key].filter((assetId) => assetId !== id);
  });
  Object.keys(state.spliceBaskets).forEach((key) => {
    state.spliceBaskets[key] = state.spliceBaskets[key].filter((assetId) => assetId !== id);
  });
  state.baskets[basket].push(id);
  renderBaskets();
  renderSplicePool();
}

function addToSpliceBasket(id, basket) {
  const asset = state.assetsById.get(id);
  if (!asset) return;
  if (asset.module !== "index") {
    setStatus("模拟拼接池只接受指数标的。", "error");
    return;
  }
  Object.keys(state.spliceBaskets).forEach((key) => {
    state.spliceBaskets[key] = state.spliceBaskets[key].filter((assetId) => assetId !== id);
  });
  state.spliceBaskets[basket].push(id);
  renderSplicePool();
}

async function runBacktest() {
  setStatus("正在运行回测...", "");
  els.runBtn.disabled = true;
  try {
    const payload = {
      baskets: state.baskets,
      spliceSimulation: {
        enabled: els.spliceToggle.checked,
        baskets: state.spliceBaskets,
      },
      ma20Controls: {
        equity: els.ma20Equity.checked,
        commodity: els.ma20Commodity.checked,
        convertible: els.ma20Convertible.checked,
      },
      ma20ThreeDay: els.ma20ThreeDay.checked,
    };
    const res = await fetch("/api/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "回测失败");
    state.result = data;
    renderResult(data);
    setStatus("回测完成。", "ok");
  } catch (err) {
    setStatus(err.message || String(err), "error");
  } finally {
    els.runBtn.disabled = false;
  }
}

function renderResult(data) {
  els.results.classList.remove("hidden");
  const activeControls = Object.entries(data.ma20Controls || {})
    .filter(([, enabled]) => enabled)
    .map(([key]) => basketLabels[key])
    .join("、");
  const spliceText = data.spliceContext?.enabled
    ? `；模拟拼接：${data.spliceContext.indexStart} 至 ${data.spliceContext.indexEnd} 用指数，${data.spliceContext.fundStart} 起用基金`
    : "";
  const ma20Mode = data.ma20ThreeDay ? "连续3日确认" : "单日确认";
  const stats = data.rebalanceStats || {};
  const rebalanceText = `策略调仓 ${stats.strategyTotal ?? 0} 次（Stage变化 ${stats.stageChanges ?? 0} 次，三个月再平衡 ${stats.threeMonth ?? 0} 次；不含初始建仓和MA20）`;
  els.windowText.textContent = `${data.window.start} 至 ${data.window.end}，共 ${data.window.days} 个交易日；${rebalanceText}；MA20 风控：${activeControls || "关闭"}${activeControls ? `（${ma20Mode}）` : ""}${spliceText}。`;
  renderMetrics(data.metrics);
  renderCharts(data);
  renderTables(data);
}

function renderMetrics(metrics) {
  els.metrics.innerHTML = metrics
    .map(
      (item) => `
        <article class="metric">
          <h3>${escapeHtml(item.name)}</h3>
          <div class="metric-grid">
            ${metricCell("累计收益", pct(item.totalReturn))}
            ${metricCell("年化", pct(item.annualReturn))}
            ${metricCell("最大回撤", pct(item.maxDrawdown))}
            ${metricCell("波动率", pct(item.volatility))}
            ${metricCell("夏普", num(item.sharpe))}
            ${metricCell("卡玛", num(item.calmar))}
          </div>
        </article>
      `,
    )
    .join("");
}

function metricCell(label, value) {
  return `
    <div>
      <div class="metric-label">${label}</div>
      <div class="metric-value">${value}</div>
    </div>
  `;
}

function renderCharts(data) {
  drawLineChart("navChart", data.series, [
    { key: "strategy", label: "策略", color: colors.strategy },
    { key: "theory", label: "理论", color: colors.theory, dashed: true },
    { key: "benchmark", label: "沪深300", color: colors.benchmark },
  ]);

  drawLineChart(
    "drawdownChart",
    data.series,
    [
      { key: "drawdown", label: "策略回撤", color: colors.strategy, fill: true },
      { key: "benchmarkDrawdown", label: "基准回撤", color: colors.benchmark },
    ],
    { percentAxis: true, zeroLine: true },
  );

  drawStackedArea("weightChart", data.series, [
    { key: "equityWeight", label: "股票", color: colors.equity },
    { key: "convertibleWeight", label: "可转债", color: colors.convertible },
    { key: "commodityWeight", label: "商品", color: colors.commodity },
    { key: "pureBondWeight", label: "纯债", color: colors.pureBond },
  ]);

  drawGroupedBarChart("annualReturnChart", data.annualAttribution, [
    { key: "strategy", label: "策略", color: colors.strategy },
    { key: "benchmark", label: "沪深300", color: "#9aa5b1" },
  ]);

  drawSignedStackedBarChart("annualContributionChart", data.annualAttribution, [
    { key: "equity", label: "股票", color: colors.equity },
    { key: "convertible", label: "可转债", color: colors.convertible },
    { key: "commodity", label: "商品", color: colors.commodity },
    { key: "pureBond", label: "纯债", color: colors.pureBond },
  ], {
    lineSeries: [
      { key: "strategy", label: "策略总收益", color: "#17202a" },
      { key: "benchmark", label: "沪深300", color: "#9aa5b1" },
    ],
  });

  drawSignedStackedArea("contributionChart", data.contributionSummary.series, [
    { key: "equity", label: "股票", color: colors.equity },
    { key: "commodity", label: "商品", color: colors.commodity },
    { key: "convertible", label: "可转债", color: colors.convertible },
    { key: "pureBond", label: "纯债", color: colors.pureBond },
  ], { percentAxis: true, zeroLine: true });
}

function renderTables(data) {
  els.annualTable.innerHTML = table(
    ["年份", "策略", "沪深300", "股票贡献", "商品贡献", "转债贡献", "纯债贡献"],
    data.annualAttribution.map((row) => [
      row.year,
      pct(row.strategy),
      pct(row.benchmark),
      pct(row.equity),
      pct(row.commodity),
      pct(row.convertible),
      pct(row.pureBond),
    ]),
  );

  els.efficiencyTable.innerHTML = table(
    ["资产", "活跃天数", "日均仓位", "资金占用", "利润贡献", "效率"],
    data.efficiency.map((row) => [
      basketLabels[row.key] || row.key,
      row.activeDays,
      pct(row.avgWeight),
      pct(row.capitalShare),
      pct(row.profitShare),
      num(row.efficiency),
    ]),
  );

  els.tradeTable.innerHTML = table(
    ["日期", "类型", "Stage", "优势资产", "逻辑", "股票", "商品", "转债", "纯债"],
    data.tradeLogs.slice(-20).reverse().map((row) => [
      row.start,
      rebalanceTypeLabels[row.rebalanceType] || row.rebalanceType || "-",
      Number.isFinite(row.stage) ? `Stage ${row.stage}` : "-",
      basketLabels[row.dominantAsset] || row.dominantAsset || "-",
      row.reason,
      pct(row.equityWeight),
      pct(row.commodityWeight),
      pct(row.convertibleWeight),
      pct(row.pureBondWeight),
    ]),
  );

  const escapes = [
    ...(data.escapeDiagnostics.equity || []).map((row) => ({ ...row, asset: "股票" })),
    ...(data.escapeDiagnostics.commodity || []).map((row) => ({ ...row, asset: "商品" })),
    ...(data.escapeDiagnostics.convertible || []).map((row) => ({ ...row, asset: "可转债" })),
  ];
  els.escapeTable.innerHTML = escapes.length
    ? table(
        ["资产", "开始", "结束", "天数", "躲过下跌", "错过反弹", "底层涨跌", "纯债收益"],
        escapes.map((row) => [
          row.asset,
          row.start,
          row.end,
          row.days,
          pct(row.avoidedDrawdown),
          pct(row.missedRunup),
          pct(row.assetReturn),
          pct(row.pureBondReturn),
        ]),
      )
    : `<div class="empty-state">未检测到完整的 MA20 逃逸区间</div>`;
}

function table(headers, rows) {
  if (!rows.length) return `<div class="empty-state">暂无数据</div>`;
  return `
    <table>
      <thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows
          .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(String(cell ?? "-"))}</td>`).join("")}</tr>`)
          .join("")}
      </tbody>
    </table>
  `;
}

function drawLineChart(canvasId, rows, series, options = {}) {
  const canvas = document.getElementById(canvasId);
  const { ctx, width, height } = prepareCanvas(canvas);
  const pad = { left: 54, right: 18, top: 24, bottom: 68 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const values = [];
  series.forEach((s) => rows.forEach((row) => Number.isFinite(row[s.key]) && values.push(row[s.key])));
  if (!values.length) return;
  let minY = Math.min(...values);
  let maxY = Math.max(...values);
  if (options.zeroLine) {
    minY = Math.min(minY, 0);
    maxY = Math.max(maxY, 0);
  }
  const span = maxY - minY || 1;
  minY -= span * 0.08;
  maxY += span * 0.08;

  drawAxes(ctx, width, height, pad, minY, maxY, options.percentAxis);
  drawTimeAxis(ctx, rows, width, height, pad);
  drawLegend(ctx, series, pad.left, 14);

  const x = (i) => pad.left + (rows.length <= 1 ? 0 : (i / (rows.length - 1)) * plotW);
  const y = (v) => pad.top + ((maxY - v) / (maxY - minY)) * plotH;

  series.forEach((s) => {
    ctx.save();
    ctx.strokeStyle = s.color;
    ctx.lineWidth = s.key === "strategy" ? 2.6 : 1.8;
    if (s.dashed) ctx.setLineDash([7, 5]);
    ctx.beginPath();
    let started = false;
    rows.forEach((row, i) => {
      const v = row[s.key];
      if (!Number.isFinite(v)) return;
      if (!started) {
        ctx.moveTo(x(i), y(v));
        started = true;
      } else {
        ctx.lineTo(x(i), y(v));
      }
    });
    ctx.stroke();
    ctx.restore();
  });
}

function drawStackedArea(canvasId, rows, series) {
  const canvas = document.getElementById(canvasId);
  const { ctx, width, height } = prepareCanvas(canvas);
  const pad = { left: 48, right: 16, top: 24, bottom: 68 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  drawAxes(ctx, width, height, pad, 0, 1, true);
  drawTimeAxis(ctx, rows, width, height, pad);
  drawLegend(ctx, series, pad.left, 14);

  const x = (i) => pad.left + (rows.length <= 1 ? 0 : (i / (rows.length - 1)) * plotW);
  const y = (v) => pad.top + (1 - v) * plotH;
  let lower = new Array(rows.length).fill(0);

  series.forEach((s) => {
    const upper = rows.map((row, i) => lower[i] + (Number(row[s.key]) || 0));
    ctx.beginPath();
    upper.forEach((v, i) => {
      if (i === 0) ctx.moveTo(x(i), y(v));
      else ctx.lineTo(x(i), y(v));
    });
    for (let i = rows.length - 1; i >= 0; i -= 1) {
      ctx.lineTo(x(i), y(lower[i]));
    }
    ctx.closePath();
    ctx.fillStyle = hexToRgba(s.color, 0.78);
    ctx.fill();
    lower = upper;
  });
}

function drawSignedStackedArea(canvasId, rows, series, options = {}) {
  const canvas = document.getElementById(canvasId);
  const { ctx, width, height } = prepareCanvas(canvas);
  const pad = { left: 54, right: 18, top: 24, bottom: 68 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const posTotals = rows.map((row) => series.reduce((sum, s) => sum + Math.max(0, Number(row[s.key]) || 0), 0));
  const negTotals = rows.map((row) => series.reduce((sum, s) => sum + Math.min(0, Number(row[s.key]) || 0), 0));
  let minY = Math.min(0, ...negTotals);
  let maxY = Math.max(0, ...posTotals);
  const span = maxY - minY || 1;
  minY -= span * 0.08;
  maxY += span * 0.08;

  drawAxes(ctx, width, height, pad, minY, maxY, options.percentAxis);
  drawTimeAxis(ctx, rows, width, height, pad);
  drawLegend(ctx, series, pad.left, 14);

  const x = (i) => pad.left + (rows.length <= 1 ? 0 : (i / (rows.length - 1)) * plotW);
  const y = (v) => pad.top + ((maxY - v) / (maxY - minY)) * plotH;
  const posLower = new Array(rows.length).fill(0);
  const negLower = new Array(rows.length).fill(0);

  series.forEach((s) => {
    const lower = [];
    const upper = [];
    rows.forEach((row, i) => {
      const value = Number(row[s.key]) || 0;
      if (value >= 0) {
        lower[i] = posLower[i];
        upper[i] = posLower[i] + value;
        posLower[i] = upper[i];
      } else {
        lower[i] = negLower[i];
        upper[i] = negLower[i] + value;
        negLower[i] = upper[i];
      }
    });
    ctx.beginPath();
    upper.forEach((v, i) => {
      if (i === 0) ctx.moveTo(x(i), y(v));
      else ctx.lineTo(x(i), y(v));
    });
    for (let i = rows.length - 1; i >= 0; i -= 1) {
      ctx.lineTo(x(i), y(lower[i]));
    }
    ctx.closePath();
    ctx.fillStyle = hexToRgba(s.color, 0.78);
    ctx.fill();
  });
}

function drawGroupedBarChart(canvasId, rows, series) {
  const canvas = document.getElementById(canvasId);
  const { ctx, width, height } = prepareCanvas(canvas);
  const pad = { left: 54, right: 18, top: 24, bottom: 42 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const values = [];
  series.forEach((s) => rows.forEach((row) => Number.isFinite(row[s.key]) && values.push(row[s.key])));
  let minY = Math.min(0, ...values);
  let maxY = Math.max(0, ...values);
  const span = maxY - minY || 1;
  minY -= span * 0.08;
  maxY += span * 0.08;

  drawAxes(ctx, width, height, pad, minY, maxY, true);
  drawCategoryAxis(ctx, rows.map((row) => row.year), width, height, pad);
  drawLegend(ctx, series, pad.left, 14);

  const groupW = plotW / Math.max(1, rows.length);
  const barW = Math.min(28, (groupW * 0.68) / series.length);
  const y = (v) => pad.top + ((maxY - v) / (maxY - minY)) * plotH;
  const zeroY = y(0);

  rows.forEach((row, i) => {
    const center = pad.left + groupW * i + groupW / 2;
    series.forEach((s, j) => {
      const value = Number(row[s.key]) || 0;
      const x = center - (barW * series.length) / 2 + j * barW;
      const top = Math.min(y(value), zeroY);
      const h = Math.max(1, Math.abs(zeroY - y(value)));
      ctx.fillStyle = s.color;
      ctx.fillRect(x, top, barW * 0.82, h);
    });
  });
}

function drawSignedStackedBarChart(canvasId, rows, series, options = {}) {
  const canvas = document.getElementById(canvasId);
  const { ctx, width, height } = prepareCanvas(canvas);
  const pad = { left: 54, right: 18, top: 24, bottom: 42 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const posTotals = rows.map((row) => series.reduce((sum, s) => sum + Math.max(0, Number(row[s.key]) || 0), 0));
  const negTotals = rows.map((row) => series.reduce((sum, s) => sum + Math.min(0, Number(row[s.key]) || 0), 0));
  const lineSeries = options.lineSeries || [];
  const lineValues = lineSeries.flatMap((line) => rows.map((row) => Number(row[line.key]) || 0));
  let minY = Math.min(0, ...negTotals, ...lineValues);
  let maxY = Math.max(0, ...posTotals, ...lineValues);
  const span = maxY - minY || 1;
  minY -= span * 0.08;
  maxY += span * 0.08;

  drawAxes(ctx, width, height, pad, minY, maxY, true);
  drawCategoryAxis(ctx, rows.map((row) => row.year), width, height, pad);
  drawLegend(ctx, [...series, ...lineSeries], pad.left, 14);

  const groupW = plotW / Math.max(1, rows.length);
  const barW = Math.min(44, groupW * 0.52);
  const y = (v) => pad.top + ((maxY - v) / (maxY - minY)) * plotH;
  const zeroY = y(0);

  rows.forEach((row, i) => {
    const x = pad.left + groupW * i + (groupW - barW) / 2;
    let pos = 0;
    let neg = 0;
    series.forEach((s) => {
      const value = Number(row[s.key]) || 0;
      if (value >= 0) {
        const top = y(pos + value);
        const bottom = y(pos);
        ctx.fillStyle = s.color;
        ctx.fillRect(x, top, barW, Math.max(1, bottom - top));
        pos += value;
      } else {
        const top = y(neg);
        const bottom = y(neg + value);
        ctx.fillStyle = s.color;
        ctx.fillRect(x, top, barW, Math.max(1, bottom - top));
        neg += value;
      }
    });
  });

  lineSeries.forEach((line, lineIndex) => {
    ctx.save();
    ctx.strokeStyle = line.color;
    ctx.lineWidth = 2;
    ctx.setLineDash(lineIndex === 0 ? [3, 4] : [8, 5]);
    ctx.beginPath();
    rows.forEach((row, i) => {
      const center = pad.left + groupW * i + groupW / 2;
      const value = Number(row[line.key]) || 0;
      if (i === 0) ctx.moveTo(center, y(value));
      else ctx.lineTo(center, y(value));
    });
    ctx.stroke();
    ctx.restore();
  });
}

function prepareCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const cssWidth = Math.max(1, rect.width || canvas.parentElement?.clientWidth || 600);
  const cssHeight = Number(canvas.dataset.chartHeight || canvas.getAttribute("height")) || 260;
  canvas.dataset.chartHeight = String(cssHeight);
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  canvas.width = Math.max(1, Math.floor(cssWidth * dpr));
  canvas.height = Math.floor(cssHeight * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.font = "12px Microsoft YaHei, Arial";
  return { ctx, width: cssWidth, height: cssHeight };
}

function drawAxes(ctx, width, height, pad, minY, maxY, percentAxis) {
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  ctx.strokeStyle = "#dce3ea";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#657282";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let i = 0; i <= 4; i += 1) {
    const ratio = i / 4;
    const y = pad.top + ratio * plotH;
    const value = maxY - ratio * (maxY - minY);
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + plotW, y);
    ctx.stroke();
    ctx.fillText(percentAxis ? pct(value, 0) : value.toFixed(2), pad.left - 8, y);
  }
  ctx.strokeStyle = "#aeb8c2";
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, pad.top + plotH);
  ctx.lineTo(pad.left + plotW, pad.top + plotH);
  ctx.stroke();

  if (minY < 0 && maxY > 0) {
    const zeroY = pad.top + ((maxY - 0) / (maxY - minY)) * plotH;
    ctx.strokeStyle = "#7f8b97";
    ctx.beginPath();
    ctx.moveTo(pad.left, zeroY);
    ctx.lineTo(pad.left + plotW, zeroY);
    ctx.stroke();
  }
}

function drawTimeAxis(ctx, rows, width, height, pad) {
  if (!rows.length) return;
  const plotW = width - pad.left - pad.right;
  const ticks = buildQuarterTicks(rows);
  ctx.fillStyle = "#657282";
  ctx.strokeStyle = "#c5ced8";
  ticks.forEach((tick) => {
    const x = pad.left + (rows.length <= 1 ? 0 : (tick.index / (rows.length - 1)) * plotW);
    const axisY = height - pad.bottom;
    ctx.beginPath();
    ctx.moveTo(x, axisY);
    ctx.lineTo(x, axisY + 5);
    ctx.stroke();
    ctx.save();
    ctx.translate(x + 4, axisY + 9);
    ctx.rotate(Math.PI / 2);
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(tick.label, 0, 0);
    ctx.restore();
  });
}

function drawCategoryAxis(ctx, labels, width, height, pad) {
  const plotW = width - pad.left - pad.right;
  const groupW = plotW / Math.max(1, labels.length);
  ctx.fillStyle = "#657282";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  labels.forEach((label, i) => {
    const x = pad.left + groupW * i + groupW / 2;
    ctx.fillText(label, x, height - pad.bottom + 10);
  });
}

function buildQuarterTicks(rows) {
  const candidates = [];
  let lastQuarter = "";
  rows.forEach((row, index) => {
    const date = new Date(row.date);
    if (Number.isNaN(date.getTime())) return;
    const quarter = `${date.getFullYear()}Q${Math.floor(date.getMonth() / 3) + 1}`;
    if (quarter !== lastQuarter) {
      candidates.push({ index, label: quarter });
      lastQuarter = quarter;
    }
  });
  if (!candidates.length) return [];
  if (candidates[0].index !== 0) {
    const first = new Date(rows[0].date);
    candidates.unshift({ index: 0, label: `${first.getFullYear()}Q${Math.floor(first.getMonth() / 3) + 1}` });
  }
  const lastRowIndex = rows.length - 1;
  const last = new Date(rows[lastRowIndex].date);
  const lastLabel = `${last.getFullYear()}Q${Math.floor(last.getMonth() / 3) + 1}`;
  if (candidates[candidates.length - 1].index !== lastRowIndex) {
    if (candidates[candidates.length - 1].label === lastLabel) {
      candidates[candidates.length - 1] = { index: lastRowIndex, label: lastLabel };
    } else {
      candidates.push({ index: lastRowIndex, label: lastLabel });
    }
  }
  return candidates;
}

function drawLegend(ctx, series, x, y) {
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  let cursor = x;
  series.forEach((s) => {
    ctx.fillStyle = s.color;
    ctx.fillRect(cursor, y - 5, 10, 10);
    ctx.fillStyle = "#46515d";
    ctx.fillText(s.label, cursor + 16, y);
    cursor += Math.max(70, ctx.measureText(s.label).width + 34);
  });
}

function setStatus(text, type) {
  els.status.textContent = text;
  els.status.className = `status ${type || ""}`.trim();
}

function pct(value, digits = 2) {
  if (!Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}

function num(value) {
  if (!Number.isFinite(value)) return "-";
  return Number(value).toFixed(2);
}

function hexToRgba(hex, alpha) {
  const clean = hex.replace("#", "");
  const bigint = parseInt(clean, 16);
  const r = (bigint >> 16) & 255;
  const g = (bigint >> 8) & 255;
  const b = bigint & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
