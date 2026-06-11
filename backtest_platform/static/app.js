const basketLabels = {
  equity: "股票",
  commodity: "商品",
  convertible: "可转债",
  pure_bond: "纯债",
};

const moduleLabels = {
  fund: "基金",
  manager: "基金经理",
  index: "指数",
  enhanced: "增强",
};

const rebalanceTypeLabels = {
  initial: "初始建仓",
  stage_change: "Stage变化",
  three_month: "三个月再平衡",
  risk_tier: "分级风控",
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

const categoryOrder = ["equity", "commodity", "convertible", "pure_bond"];
const stageNumbers = [1, 2, 3, 4, 5, 6, 7, 8];

const state = {
  grouped: { fund: [], manager: [], index: [], enhanced: [] },
  assetsById: new Map(),
  activeTab: "index",
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
  defaultStageWeights: null,
  stageWeights: null,
  attributionMode: "stage",
  pring: null,
  result: null,
};

const els = {
  assetCount: document.getElementById("assetCount"),
  assetList: document.getElementById("assetList"),
  searchInput: document.getElementById("searchInput"),
  runBtn: document.getElementById("runBtn"),
  resetBtn: document.getElementById("resetBtn"),
  clearBtn: document.getElementById("clearBtn"),
  stageSettingsBtn: document.getElementById("stageSettingsBtn"),
  stageSettingsModal: document.getElementById("stageSettingsModal"),
  closeStageSettingsBtn: document.getElementById("closeStageSettingsBtn"),
  cancelStageSettingsBtn: document.getElementById("cancelStageSettingsBtn"),
  applyStageSettingsBtn: document.getElementById("applyStageSettingsBtn"),
  resetStageWeightsBtn: document.getElementById("resetStageWeightsBtn"),
  stageWeightRows: document.getElementById("stageWeightRows"),
  stageWeightStatus: document.getElementById("stageWeightStatus"),
  ma20Equity: document.getElementById("ma20Equity"),
  ma20Commodity: document.getElementById("ma20Commodity"),
  startDate: document.getElementById("startDate"),
  endDate: document.getElementById("endDate"),
  dateRangeHint: document.getElementById("dateRangeHint"),
  spliceToggle: document.getElementById("spliceToggle"),
  splicePool: document.getElementById("splicePool"),
  splicePanel: document.getElementById("splicePanel"),
  status: document.getElementById("status"),
  results: document.getElementById("results"),
  metrics: document.getElementById("metrics"),
  windowText: document.getElementById("windowText"),
  stageAttributionHint: document.getElementById("stageAttributionHint"),
  stageAttributionTable: document.getElementById("stageAttributionTable"),
  annualTable: document.getElementById("annualTable"),
  efficiencyTable: document.getElementById("efficiencyTable"),
  tradeTable: document.getElementById("tradeTable"),
  riskTable: document.getElementById("riskTable"),
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
    state.defaultStageWeights = cloneWeights(data.defaultStageWeights);
    state.stageWeights = cloneWeights(data.defaultStageWeights);
    updateStageSettingsButton();
    state.pring = data.pring;
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
  els.stageSettingsBtn.addEventListener("click", openStageSettings);
  els.closeStageSettingsBtn.addEventListener("click", closeStageSettings);
  els.cancelStageSettingsBtn.addEventListener("click", closeStageSettings);
  els.applyStageSettingsBtn.addEventListener("click", applyStageSettings);
  els.resetStageWeightsBtn.addEventListener("click", resetStageWeights);
  els.stageSettingsModal.addEventListener("click", (event) => {
    if (event.target === els.stageSettingsModal) closeStageSettings();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !els.stageSettingsModal.classList.contains("hidden")) {
      closeStageSettings();
    }
  });
  els.runBtn.addEventListener("click", runBacktest);
  els.spliceToggle.addEventListener("change", renderSplicePool);
  els.startDate.addEventListener("change", validateDateInputs);
  els.endDate.addEventListener("change", validateDateInputs);
  document.querySelectorAll("[data-attribution-mode]").forEach((button) => {
    button.addEventListener("click", () => setAttributionMode(button.dataset.attributionMode));
  });

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
  updateDateRangeBounds(true);
}

function clearBaskets() {
  state.baskets = emptyBaskets();
  state.spliceBaskets = emptyBaskets();
  renderBaskets();
  renderSplicePool();
  els.startDate.value = "";
  els.endDate.value = "";
  els.dateRangeHint.textContent = "请先为四类资产选择标的";
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
    const haystack = [
      asset.code,
      asset.name,
      asset.manager,
      asset.roleLabel,
      asset.fullLabel,
      asset.cluster,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
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
      <div class="asset-code">${escapeHtml(asset.code)}${asset.manager ? ` · ${escapeHtml(asset.manager)}` : ""}</div>
      ${
        asset.cluster || asset.roleLabel
          ? `<div class="asset-tags" title="${escapeHtml(asset.fullLabel || asset.roleLabel || asset.cluster)}">
              ${asset.cluster ? `<span>${escapeHtml(asset.cluster)}</span>` : ""}
              ${asset.roleLabel ? `<span>${escapeHtml(asset.roleLabel)}</span>` : ""}
            </div>`
          : ""
      }
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
  updateDateRangeBounds();
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
  updateDateRangeBounds();
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
  if (!validateDateInputs()) return;
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
      },
      dateRange: {
        start: els.startDate.value || null,
        end: els.endDate.value || null,
      },
      stageWeights: state.stageWeights,
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

function openStageSettings() {
  renderStageWeightRows(state.stageWeights);
  els.stageWeightStatus.textContent = "";
  els.stageSettingsModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeStageSettings() {
  els.stageSettingsModal.classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function renderStageWeightRows(weights) {
  els.stageWeightRows.innerHTML = stageNumbers
    .map((stage) => {
      const row = weights[stage];
      const dominant = dominantCategory(row);
      const cells = categoryOrder
        .map(
          (category) => `
            <td>
              <label class="weight-input">
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value="${formatWeightInput(row[category] * 100)}"
                  data-stage="${stage}"
                  data-category="${category}"
                  aria-label="Stage ${stage} ${basketLabels[category]}比例"
                />
                <span>%</span>
              </label>
            </td>
          `,
        )
        .join("");
      return `
        <tr data-stage-row="${stage}">
          <td>Stage ${stage}</td>
          <td class="stage-dominant-cell" data-stage-dominant>
            <span class="dominant-badge">${basketLabels[dominant]}</span>
          </td>
          ${cells}
          <td class="stage-total">100%</td>
        </tr>
      `;
    })
    .join("");

  els.stageWeightRows.querySelectorAll("input").forEach((input) => {
    input.addEventListener("input", updateStageRowTotal);
  });
}

function updateStageRowTotal(event) {
  const row = event.target.closest("tr");
  const total = Array.from(row.querySelectorAll("input")).reduce(
    (sum, input) => sum + (Number(input.value) || 0),
    0,
  );
  const totalCell = row.querySelector(".stage-total");
  totalCell.textContent = `${formatWeightInput(total)}%`;
  totalCell.classList.toggle("invalid", Math.abs(total - 100) > 0.001);
  updateStageRowDominant(row);
}

function updateStageRowDominant(row) {
  const weights = {};
  categoryOrder.forEach((category) => {
    const input = row.querySelector(`input[data-category="${category}"]`);
    weights[category] = Number(input?.value) || 0;
  });
  const dominant = dominantCategory(weights);
  row.querySelector("[data-stage-dominant]").innerHTML =
    `<span class="dominant-badge">${basketLabels[dominant]}</span>`;
}

function dominantCategory(weights) {
  return categoryOrder.reduce((best, category) => {
    const bestWeight = Number(weights?.[best]) || 0;
    const categoryWeight = Number(weights?.[category]) || 0;
    return categoryWeight > bestWeight ? category : best;
  }, categoryOrder[0]);
}

function readStageWeights() {
  const weights = {};
  for (const stage of stageNumbers) {
    const row = els.stageWeightRows.querySelector(`tr[data-stage-row="${stage}"]`);
    const values = {};
    let total = 0;
    for (const category of categoryOrder) {
      const input = row.querySelector(`input[data-category="${category}"]`);
      const value = Number(input.value);
      if (!Number.isFinite(value) || value < 0 || value > 100) {
        throw new Error(`Stage ${stage} 的${basketLabels[category]}比例必须在 0% 至 100% 之间`);
      }
      values[category] = value / 100;
      total += value;
    }
    if (Math.abs(total - 100) > 0.001) {
      throw new Error(`Stage ${stage} 四类资产比例合计必须为 100%，当前为 ${formatWeightInput(total)}%`);
    }
    weights[stage] = values;
  }
  return weights;
}

function applyStageSettings() {
  try {
    state.stageWeights = readStageWeights();
    updateStageSettingsButton();
    closeStageSettings();
    setStatus("Stage 资产比例已更新。", "ok");
  } catch (err) {
    els.stageWeightStatus.textContent = err.message || String(err);
  }
}

function resetStageWeights() {
  state.stageWeights = cloneWeights(state.defaultStageWeights);
  renderStageWeightRows(state.stageWeights);
  updateStageSettingsButton();
  els.stageWeightStatus.textContent = "已恢复默认比例";
}

function updateStageSettingsButton() {
  const custom = JSON.stringify(state.stageWeights) !== JSON.stringify(state.defaultStageWeights);
  els.stageSettingsBtn.classList.toggle("active-setting", custom);
  els.stageSettingsBtn.textContent = custom ? "Stage 比例 · 自定义" : "Stage 比例";
}

function cloneWeights(weights) {
  return JSON.parse(JSON.stringify(weights || {}));
}

function formatWeightInput(value) {
  return Number(value.toFixed(4)).toString();
}

function updateDateRangeBounds(reset = false) {
  if (!els.startDate || !state.pring) return;
  const mainIds = Object.values(state.baskets).flat();
  if (!mainIds.length) {
    els.startDate.removeAttribute("min");
    els.startDate.removeAttribute("max");
    els.endDate.removeAttribute("min");
    els.endDate.removeAttribute("max");
    return;
  }

  const spliceComplete =
    els.spliceToggle.checked &&
    Object.values(state.spliceBaskets).every((ids) => ids.length > 0);
  const startIds = spliceComplete ? Object.values(state.spliceBaskets).flat() : mainIds;
  const startCandidates = startIds
    .map((id) => state.assetsById.get(id)?.start)
    .filter(Boolean);
  const endCandidates = mainIds
    .map((id) => state.assetsById.get(id)?.end)
    .filter(Boolean);
  if (!startCandidates.length || !endCandidates.length) return;

  const signalFloor = addDays(state.pring.start, 1);
  const commonStart = [signalFloor, ...startCandidates].sort().at(-1);
  const commonEnd = endCandidates.sort()[0];
  if (!commonStart || !commonEnd || commonStart > commonEnd) {
    els.dateRangeHint.textContent = "当前选择没有共同可用区间";
    return;
  }

  els.startDate.min = commonStart;
  els.startDate.max = commonEnd;
  els.endDate.min = commonStart;
  els.endDate.max = commonEnd;
  if (reset || !els.startDate.value || els.startDate.value < commonStart || els.startDate.value > commonEnd) {
    els.startDate.value = commonStart;
  }
  if (reset || !els.endDate.value || els.endDate.value < commonStart || els.endDate.value > commonEnd) {
    els.endDate.value = commonEnd;
  }
  els.dateRangeHint.textContent = `可用共同区间 ${commonStart} 至 ${commonEnd}`;
}

function validateDateInputs() {
  const start = els.startDate.value;
  const end = els.endDate.value;
  if (start && end && start > end) {
    setStatus("回测开始日期不能晚于结束日期。", "error");
    return false;
  }
  return true;
}

function addDays(dateText, days) {
  const date = new Date(`${dateText}T00:00:00`);
  date.setDate(date.getDate() + days);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
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
  const stats = data.rebalanceStats || {};
  const rebalanceText = `策略调仓 ${stats.strategyTotal ?? 0} 次（Stage变化 ${stats.stageChanges ?? 0} 次，三个月再平衡 ${stats.threeMonth ?? 0} 次；分级风控动作 ${stats.riskActions ?? 0} 次）`;
  els.windowText.textContent = `${data.window.start} 至 ${data.window.end}，共 ${data.window.days} 个交易日；${rebalanceText}；MA20 + KST 风控：${activeControls || "关闭"}${spliceText}。`;
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
  renderSelectedAttribution(data);

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
    ["日期", "类型", "Stage", "优势资产", "风险档位", "切档", "逻辑", "股票", "商品", "转债", "纯债"],
    data.tradeLogs.slice(-20).reverse().map((row) => [
      row.start,
      rebalanceTypeLabels[row.rebalanceType] || row.rebalanceType || "-",
      Number.isFinite(row.stage) ? `Stage ${row.stage}` : "-",
      basketLabels[row.dominantAsset] || row.dominantAsset || "-",
      pct(row.riskTier),
      row.riskTransition || "-",
      row.reason,
      pct(row.equityWeight),
      pct(row.commodityWeight),
      pct(row.convertibleWeight),
      pct(row.pureBondWeight),
    ]),
  );

  const diagnostics = data.riskDiagnostics || [];
  els.riskTable.innerHTML = diagnostics.length
    ? table(
        ["执行日", "信号日", "资产", "切档", "MA20", "KST", "Signal", "10日斜率", "KST状态", "原因"],
        diagnostics.slice().reverse().map((row) => [
          row.date,
          row.signalDate || "-",
          basketLabels[row.asset] || row.asset,
          row.transition || "-",
          row.ma20Above === null ? "-" : row.ma20Above ? "上方" : "下方",
          num(row.kst),
          num(row.kstSignal),
          num(row.kstSlope10),
          row.kstReady ? (row.kstWeak ? "弱" : "不弱") : "预热中",
          row.reason,
        ]),
      )
    : `<div class="empty-state">未发生 MA20 + KST 风险档位切换</div>`;
}

function setAttributionMode(mode) {
  state.attributionMode = mode === "year" ? "year" : "stage";
  document.querySelectorAll("[data-attribution-mode]").forEach((button) => {
    const active = button.dataset.attributionMode === state.attributionMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  if (state.result) renderSelectedAttribution(state.result);
}

function renderSelectedAttribution(data) {
  const yearMode = state.attributionMode === "year";
  els.stageAttributionHint.textContent = yearMode
    ? "连续 Stage 在每个自然年末截断；区间收益与贡献重新计算"
    : "连续相同 Stage 合并；贡献点按每日真实持仓计算";
  renderStageAttribution(
    yearMode ? data.yearStageAttribution || [] : data.stageAttribution || [],
  );
}

function renderStageAttribution(rows) {
  if (!rows.length) {
    els.stageAttributionTable.innerHTML = `<div class="empty-state">暂无阶段归因数据</div>`;
    return;
  }
  const yearMode = state.attributionMode === "year";
  const yearCounts = yearMode
    ? rows.reduce((counts, row) => {
        const year = row.start.slice(0, 4);
        counts[year] = (counts[year] || 0) + 1;
        return counts;
      }, {})
    : {};
  const renderedYears = new Set();

  els.stageAttributionTable.innerHTML = `
    <table class="stage-attribution-table">
      <thead>
        <tr>
          ${yearMode ? '<th class="year-header" rowspan="2">年份</th>' : ""}
          <th rowspan="2">持有区间</th>
          <th rowspan="2">阶段</th>
          <th rowspan="2">优势资产</th>
          <th rowspan="2">优势排名</th>
          <th rowspan="2">连续判断月数</th>
          <th rowspan="2">交易日</th>
          <th rowspan="2">策略实际收益</th>
          <th rowspan="2">沪深300</th>
          <th class="return-group-header" colspan="4">四类资产区间收益</th>
          <th class="contribution-group-header" colspan="4">实际贡献点</th>
          <th rowspan="2">策略调仓</th>
          <th rowspan="2">风控动作</th>
        </tr>
        <tr>
          <th class="asset-return-header group-start">股票收益</th>
          <th class="asset-return-header">商品收益</th>
          <th class="asset-return-header">可转债收益</th>
          <th class="asset-return-header group-end">纯债收益</th>
          <th class="contribution-header group-start">股票贡献</th>
          <th class="contribution-header">商品贡献</th>
          <th class="contribution-header">可转债贡献</th>
          <th class="contribution-header group-end">纯债贡献</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map((row) => {
            const year = row.start.slice(0, 4);
            const startsYear = yearMode && !renderedYears.has(year);
            const separatesYear = startsYear && renderedYears.size > 0;
            const yearCell =
              startsYear
                ? `<td class="year-cell" rowspan="${yearCounts[year]}">${year}</td>`
                : "";
            renderedYears.add(year);
            return stageAttributionRow(
              row,
              yearCell,
              separatesYear ? "year-group-start" : "",
            );
          })
          .join("")}
      </tbody>
    </table>
  `;
}

function stageAttributionRow(row, yearCell = "", rowClass = "") {
  const assetReturnCell = (category) => {
    const dominant = row.dominantAsset === category;
    const position = category === "equity" ? "group-start" : category === "pure_bond" ? "group-end" : "";
    return `
      <td class="asset-return-cell ${position} ${dominant ? "dominant-cell" : ""} ${returnTone(row[`${category}Return`])}">
        ${pct(row[`${category}Return`])}
        ${dominant ? '<span class="advantage-tag">优势</span>' : ""}
      </td>
    `;
  };
  const contributionCell = (category) => {
    const dominant = row.dominantAsset === category;
    const position = category === "equity" ? "group-start" : category === "pure_bond" ? "group-end" : "";
    return `
      <td class="contribution-cell ${position} ${dominant ? "dominant-cell" : ""} ${returnTone(row[`${category}Contribution`])}">
        ${pct(row[`${category}Contribution`])}
      </td>
    `;
  };
  const rebalanceBreakdown = `${row.strategyRebalances}（${row.stageChanges}+${row.threeMonthRebalances}）`;
  return `
    <tr class="${rowClass}">
      ${yearCell}
      <td class="period-cell">${escapeHtml(row.period)}</td>
      <td><span class="stage-chip">Stage ${row.stage}</span></td>
      <td>
        <span class="dominant-badge">${escapeHtml(basketLabels[row.dominantAsset] || row.dominantAsset)}</span>
        <span class="dominant-weight">${pct(row.dominantWeight)}</span>
      </td>
      <td><span class="rank-badge">${row.dominantRank}</span></td>
      <td>${row.consecutiveMonths}</td>
      <td>${row.tradingDays}</td>
      <td class="strategy-return-cell ${returnTone(row.strategyReturn)}">${pct(row.strategyReturn)}</td>
      <td class="${returnTone(row.benchmarkReturn)}">${pct(row.benchmarkReturn)}</td>
      ${assetReturnCell("equity")}
      ${assetReturnCell("commodity")}
      ${assetReturnCell("convertible")}
      ${assetReturnCell("pure_bond")}
      ${contributionCell("equity")}
      ${contributionCell("commodity")}
      ${contributionCell("convertible")}
      ${contributionCell("pure_bond")}
      <td>${rebalanceBreakdown}</td>
      <td>${row.riskActions}</td>
    </tr>
  `;
}

function returnTone(value) {
  if (!Number.isFinite(value) || value === 0) return "";
  return value > 0 ? "positive-value" : "negative-value";
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
