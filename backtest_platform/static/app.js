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
const managerClusterOrder = ["进攻弹性", "核心稳健", "防守压仓", "未分类"];
const strategyRootTagOrder = ["基准中枢", "基金经理路径", "宽基增强路径"];
const stageNumbers = [1, 2, 3, 4, 5, 6, 7, 8];
const fallbackBenchmarkId = "index:000300.SH";
const expectedApiVersion = "2026.06.12.3";
const appBaseUrl = new URL(".", window.location.href);
const topbar = document.querySelector(".topbar");

function appUrl(path) {
  return new URL(String(path).replace(/^\/+/, ""), appBaseUrl).toString();
}

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
  defaultBenchmarkId: fallbackBenchmarkId,
  benchmarkId: fallbackBenchmarkId,
  defaultStageWeights: null,
  stageWeightProfiles: {},
  stageWeights: null,
  stageWeightProfile: "3",
  collapsedAssetSections: new Set(),
  attributionMode: "stage",
  pring: null,
  result: null,
  strategies: [],
  tags: [],
  activeStrategyId: null,
  lastSuccessfulConfigSignature: null,
  strategyModalMode: "save",
  editingStrategyId: null,
  selectedStrategyTagIds: new Set(),
  strategyFilterTagId: null,
};

const els = {
  assetCount: document.getElementById("assetCount"),
  assetList: document.getElementById("assetList"),
  searchInput: document.getElementById("searchInput"),
  benchmarkBtn: document.getElementById("benchmarkBtn"),
  benchmarkName: document.getElementById("benchmarkName"),
  benchmarkCode: document.getElementById("benchmarkCode"),
  benchmarkModal: document.getElementById("benchmarkModal"),
  closeBenchmarkModalBtn: document.getElementById("closeBenchmarkModalBtn"),
  benchmarkSearchInput: document.getElementById("benchmarkSearchInput"),
  benchmarkModuleFilter: document.getElementById("benchmarkModuleFilter"),
  benchmarkList: document.getElementById("benchmarkList"),
  runBtn: document.getElementById("runBtn"),
  resetBtn: document.getElementById("resetBtn"),
  clearBtn: document.getElementById("clearBtn"),
  stageSettingsBtn: document.getElementById("stageSettingsBtn"),
  stageSettingsModal: document.getElementById("stageSettingsModal"),
  closeStageSettingsBtn: document.getElementById("closeStageSettingsBtn"),
  cancelStageSettingsBtn: document.getElementById("cancelStageSettingsBtn"),
  applyStageSettingsBtn: document.getElementById("applyStageSettingsBtn"),
  resetStageWeightsBtn: document.getElementById("resetStageWeightsBtn"),
  stageProfileSwitch: document.getElementById("stageProfileSwitch"),
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
  navChartSubtitle: document.getElementById("navChartSubtitle"),
  annualReturnSubtitle: document.getElementById("annualReturnSubtitle"),
  annualContributionSubtitle: document.getElementById("annualContributionSubtitle"),
  stageAttributionHint: document.getElementById("stageAttributionHint"),
  stageAttributionTable: document.getElementById("stageAttributionTable"),
  annualTable: document.getElementById("annualTable"),
  efficiencyTable: document.getElementById("efficiencyTable"),
  tradeTable: document.getElementById("tradeTable"),
  riskTable: document.getElementById("riskTable"),
  workspaceView: document.getElementById("workspaceView"),
  strategyLibraryView: document.getElementById("strategyLibraryView"),
  saveStrategyBtn: document.getElementById("saveStrategyBtn"),
  strategyLibraryBtn: document.getElementById("strategyLibraryBtn"),
  workspaceNavBtn: document.getElementById("workspaceNavBtn"),
  strategyLibraryCount: document.getElementById("strategyLibraryCount"),
  strategySearchInput: document.getElementById("strategySearchInput"),
  strategyTagFilter: document.getElementById("strategyTagFilter"),
  strategyCards: document.getElementById("strategyCards"),
  tagManagerBtn: document.getElementById("tagManagerBtn"),
  strategyModal: document.getElementById("strategyModal"),
  strategyModalTitle: document.getElementById("strategyModalTitle"),
  strategyModalHint: document.getElementById("strategyModalHint"),
  closeStrategyModalBtn: document.getElementById("closeStrategyModalBtn"),
  cancelStrategyModalBtn: document.getElementById("cancelStrategyModalBtn"),
  strategyNameInput: document.getElementById("strategyNameInput"),
  strategyNotesInput: document.getElementById("strategyNotesInput"),
  strategyNotesCount: document.getElementById("strategyNotesCount"),
  strategyTagSelector: document.getElementById("strategyTagSelector"),
  strategyFormError: document.getElementById("strategyFormError"),
  saveAsStrategyBtn: document.getElementById("saveAsStrategyBtn"),
  submitStrategyBtn: document.getElementById("submitStrategyBtn"),
  tagManagerModal: document.getElementById("tagManagerModal"),
  closeTagManagerBtn: document.getElementById("closeTagManagerBtn"),
  tagManagerTree: document.getElementById("tagManagerTree"),
  addRootTagBtn: document.getElementById("addRootTagBtn"),
  tagEditorForm: document.getElementById("tagEditorForm"),
  tagEditorId: document.getElementById("tagEditorId"),
  tagNameInput: document.getElementById("tagNameInput"),
  tagParentSelect: document.getElementById("tagParentSelect"),
  tagActiveRow: document.getElementById("tagActiveRow"),
  tagActiveInput: document.getElementById("tagActiveInput"),
  tagEditorError: document.getElementById("tagEditorError"),
  deleteTagBtn: document.getElementById("deleteTagBtn"),
};

init();

async function init() {
  observeTopbarHeight();
  wireEvents();
  try {
    const res = await fetch(appUrl("api/assets"));
    if (!res.ok) throw new Error("资产库加载失败");
    const data = await res.json();
    if (data.apiVersion !== expectedApiVersion) {
      throw new Error(
        `服务版本不一致（页面 ${expectedApiVersion}，后端 ${data.apiVersion || "旧版本"}），请重新运行 start_backtest_platform.ps1。`,
      );
    }
    state.grouped = data.groups;
    state.defaults = data.defaults;
    state.defaultBenchmarkId = data.defaultBenchmarkId || fallbackBenchmarkId;
    state.benchmarkId = state.defaultBenchmarkId;
    state.defaultStageWeights = cloneWeights(data.defaultStageWeights);
    state.stageWeightProfiles = data.stageWeightProfiles || {};
    state.stageWeights = cloneWeights(data.defaultStageWeights);
    state.stageWeightProfile = detectStageWeightProfile(state.stageWeights);
    renderStageProfileSwitch();
    updateStageSettingsButton();
    state.pring = data.pring;
    Object.values(state.grouped).flat().forEach((asset) => state.assetsById.set(asset.id, asset));
    renderBenchmarkControl();
    resetDefaults();
    renderAssets();
    await loadStrategyLibrary();
    handleRoute();
    setStatus(
      `已加载 ${state.assetsById.size} 个资产；月度普林格信号 ${data.pring?.start || "-"} 至 ${data.pring?.end || "-"}，共 ${data.pring?.rows || 0} 条；数据源：${data.pring?.source || "-"}。`,
      "ok",
    );
  } catch (err) {
    setStatus(err.message || String(err), "error");
  }
}

function observeTopbarHeight() {
  const syncHeight = () => {
    document.documentElement.style.setProperty(
      "--topbar-height",
      `${topbar.offsetHeight}px`,
    );
  };
  syncHeight();
  if ("ResizeObserver" in window) {
    new ResizeObserver(syncHeight).observe(topbar);
  } else {
    window.addEventListener("resize", syncHeight);
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
  els.benchmarkBtn.addEventListener("click", openBenchmarkModal);
  els.closeBenchmarkModalBtn.addEventListener("click", closeBenchmarkModal);
  els.benchmarkSearchInput.addEventListener("input", renderBenchmarkList);
  els.benchmarkModuleFilter.addEventListener("change", renderBenchmarkList);
  els.benchmarkList.addEventListener("click", handleBenchmarkSelection);
  els.benchmarkModal.addEventListener("click", (event) => {
    if (event.target === els.benchmarkModal) closeBenchmarkModal();
  });
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
    if (event.key === "Escape" && !els.benchmarkModal.classList.contains("hidden")) {
      closeBenchmarkModal();
    }
  });
  els.runBtn.addEventListener("click", runBacktest);
  els.spliceToggle.addEventListener("change", () => {
    renderSplicePool();
    configChanged();
  });
  els.ma20Equity.addEventListener("change", configChanged);
  els.ma20Commodity.addEventListener("change", configChanged);
  els.startDate.addEventListener("change", () => {
    validateDateInputs();
    configChanged();
  });
  els.endDate.addEventListener("change", () => {
    validateDateInputs();
    configChanged();
  });
  wireStrategyEvents();
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
  state.benchmarkId = state.defaultBenchmarkId;
  renderBenchmarkControl();
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
  configChanged();
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
  configChanged();
}

function emptyBaskets() {
  return {
    equity: [],
    commodity: [],
    convertible: [],
    pure_bond: [],
  };
}

function renderBenchmarkControl() {
  const asset = state.assetsById.get(state.benchmarkId);
  if (!asset) {
    els.benchmarkName.textContent = "基准不可用";
    els.benchmarkCode.textContent = state.benchmarkId || "-";
    els.benchmarkBtn.classList.add("missing");
    return;
  }
  els.benchmarkName.textContent = asset.name;
  els.benchmarkCode.textContent = `${asset.code} · ${moduleLabels[asset.module]}`;
  els.benchmarkBtn.title = `${asset.name}（${asset.code}）`;
  els.benchmarkBtn.classList.remove("missing");
}

function openBenchmarkModal() {
  els.benchmarkSearchInput.value = "";
  els.benchmarkModuleFilter.value = "";
  renderBenchmarkList();
  openModal(els.benchmarkModal);
  els.benchmarkSearchInput.focus();
}

function closeBenchmarkModal() {
  els.benchmarkModal.classList.add("hidden");
  syncModalBodyState();
}

function renderBenchmarkList() {
  const query = els.benchmarkSearchInput.value.trim().toLowerCase();
  const moduleFilter = els.benchmarkModuleFilter.value;
  const assets = Object.values(state.grouped)
    .flat()
    .filter((asset) => {
      if (moduleFilter && asset.module !== moduleFilter) return false;
      const haystack = [
        asset.name,
        asset.code,
        asset.manager,
        asset.cluster,
        asset.roleLabel,
        asset.fullLabel,
        moduleLabels[asset.module],
        basketLabels[asset.category],
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return !query || haystack.includes(query);
    })
    .sort((left, right) => (
      left.module.localeCompare(right.module)
      || left.name.localeCompare(right.name, "zh-CN")
      || left.code.localeCompare(right.code)
    ));

  if (!assets.length) {
    els.benchmarkList.innerHTML = `<div class="empty-state">没有匹配的基准标的</div>`;
    return;
  }

  els.benchmarkList.innerHTML = assets.map((asset) => `
    <button
      class="benchmark-option${asset.id === state.benchmarkId ? " selected" : ""}"
      type="button"
      data-benchmark-id="${escapeHtml(asset.id)}"
    >
      <span class="benchmark-option-main">
        <strong>${escapeHtml(asset.name)}</strong>
        <small>${escapeHtml(asset.code)}${asset.manager ? ` · ${escapeHtml(asset.manager)}` : ""}</small>
      </span>
      <span class="benchmark-option-meta">
        <span>${escapeHtml(moduleLabels[asset.module])}${asset.category ? ` · ${escapeHtml(basketLabels[asset.category])}` : ""}</span>
        <small>${asset.start} 至 ${asset.end}</small>
      </span>
    </button>
  `).join("");
}

function handleBenchmarkSelection(event) {
  const option = event.target.closest("[data-benchmark-id]");
  if (!option) return;
  const assetId = option.dataset.benchmarkId;
  if (!state.assetsById.has(assetId)) return;
  state.benchmarkId = assetId;
  renderBenchmarkControl();
  closeBenchmarkModal();
  configChanged();
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
      basketLabels[asset.category],
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return !query || haystack.includes(query);
  });

  const categoryBreakdown = categoryOrder
    .map((category) => {
      const count = assets.filter((asset) => asset.category === category).length;
      return count ? `${basketLabels[category]} ${count}` : "";
    })
    .filter(Boolean)
    .join(" · ");
  const managerBreakdown = managerClusterOrder
    .map((cluster) => {
      const count = assets.filter(
        (asset) => (asset.cluster || "未分类") === cluster,
      ).length;
      return count ? `${cluster} ${count}` : "";
    })
    .filter(Boolean)
    .join(" · ");
  const breakdown = state.activeTab === "manager" ? managerBreakdown : categoryBreakdown;
  els.assetCount.textContent =
    `${moduleLabels[state.activeTab]} ${assets.length} 个标的${breakdown ? ` · ${breakdown}` : ""}`;

  if (!assets.length) {
    els.assetList.innerHTML = `<div class="empty-state">${state.activeTab === "enhanced" ? "增强模块等待接入数据" : "没有匹配的标的"}</div>`;
    return;
  }

  els.assetList.innerHTML = "";

  const appendAsset = (asset, container = els.assetList) => {
    const card = document.createElement("div");
    card.className = "asset-card";
    card.draggable = true;
    card.dataset.assetId = asset.id;
    card.innerHTML = `
      <div class="asset-name">
        <span>${escapeHtml(asset.name)}</span>
        <span class="asset-pills">
          ${asset.category ? `<span class="category-pill category-${asset.category}">${basketLabels[asset.category]}</span>` : ""}
          <span class="module-pill">${moduleLabels[asset.module]}</span>
        </span>
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
    container.appendChild(card);
  };

  const appendSection = (sectionKey, label, sectionAssets, className) => {
    const collapsed = !query && state.collapsedAssetSections.has(sectionKey);
    const section = document.createElement("section");
    section.className = `asset-section${collapsed ? " collapsed" : ""}`;

    const heading = document.createElement("button");
    heading.type = "button";
    heading.className = `asset-section-title ${className}`;
    heading.setAttribute("aria-expanded", String(!collapsed));
    heading.innerHTML = `
      <span class="asset-section-label">
        <span class="collapse-chevron" aria-hidden="true"></span>
        ${escapeHtml(label)}
      </span>
      <strong>${sectionAssets.length}</strong>
    `;

    const body = document.createElement("div");
    body.className = "asset-section-body";
    body.hidden = collapsed;
    sectionAssets.forEach((asset) => appendAsset(asset, body));

    heading.addEventListener("click", () => {
      const willCollapse = !section.classList.contains("collapsed");
      section.classList.toggle("collapsed", willCollapse);
      body.hidden = willCollapse;
      heading.setAttribute("aria-expanded", String(!willCollapse));
      if (willCollapse) {
        state.collapsedAssetSections.add(sectionKey);
      } else {
        state.collapsedAssetSections.delete(sectionKey);
      }
    });
    section.append(heading, body);
    els.assetList.appendChild(section);
  };

  if (state.activeTab === "manager") {
    managerClusterOrder.forEach((cluster, index) => {
      const clusterAssets = assets.filter(
        (asset) => (asset.cluster || "未分类") === cluster,
      );
      if (!clusterAssets.length) return;
      appendSection(
        `manager:${cluster}`,
        cluster,
        clusterAssets,
        `manager-cluster cluster-${index + 1}`,
      );
    });
    return;
  }

  categoryOrder.forEach((category) => {
    const categoryAssets = assets.filter((asset) => asset.category === category);
    if (!categoryAssets.length) return;
    appendSection(
      `${state.activeTab}:${category}`,
      basketLabels[category],
      categoryAssets,
      `category-${category}`,
    );
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
        configChanged();
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
        configChanged();
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
  configChanged();
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
  configChanged();
}

function currentConfig() {
  return {
    baskets: JSON.parse(JSON.stringify(state.baskets)),
    benchmarkId: state.benchmarkId || state.defaultBenchmarkId,
    spliceSimulation: {
      enabled: els.spliceToggle.checked,
      baskets: JSON.parse(JSON.stringify(state.spliceBaskets)),
    },
    ma20Controls: {
      equity: els.ma20Equity.checked,
      commodity: els.ma20Commodity.checked,
    },
    dateRange: {
      start: els.startDate.value || "",
      end: els.endDate.value || "",
    },
    stageWeights: cloneWeights(state.stageWeights),
    stageWeightProfile: state.stageWeightProfile || "custom",
  };
}

function currentConfigSignature() {
  return JSON.stringify(currentConfig());
}

function configChanged() {
  updateSaveStrategyState();
  if (state.result && state.lastSuccessfulConfigSignature !== currentConfigSignature()) {
    setStatus("当前配置已变化，请重新回测后再保存策略。", "");
  }
}

function updateSaveStrategyState() {
  const ready = Boolean(
    state.result
      && state.lastSuccessfulConfigSignature
      && state.lastSuccessfulConfigSignature === currentConfigSignature(),
  );
  els.saveStrategyBtn.disabled = !ready;
  els.saveStrategyBtn.title = ready ? "保存当前策略配置" : "请先完成与当前配置匹配的回测";
}

async function runBacktest() {
  if (!validateDateInputs()) return;
  setStatus("正在运行回测...", "");
  els.runBtn.disabled = true;
  try {
    const payload = currentConfig();
    const signature = JSON.stringify(payload);
    const res = await fetch(appUrl("api/backtest"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "回测失败");
    state.result = data;
    state.lastSuccessfulConfigSignature = signature;
    renderResult(data);
    updateSaveStrategyState();
    setStatus("回测完成。", "ok");
    return true;
  } catch (err) {
    setStatus(err.message || String(err), "error");
    return false;
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
                  step="0.01"
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
    input.addEventListener("input", (event) => {
      updateStageRowTotal(event);
    });
  });
}

function renderStageProfileSwitch() {
  const levels = ["5", "4", "3", "2", "1"];
  els.stageProfileSwitch.innerHTML = levels
    .map(
      (level) => {
        const profile = state.stageWeightProfiles[level];
        return `
        <button
          type="button"
          class="stage-tilt-point level-${level}"
          data-stage-profile="${level}"
          aria-label="${escapeHtml(profile.shortLabel)}"
          title="${escapeHtml(`${profile.label} · ${profile.shortLabel}：${profile.description}`)}"
        >
          <span></span>
        </button>
      `;
      },
    )
    .join("");
  els.stageProfileSwitch.querySelectorAll("[data-stage-profile]").forEach((button) => {
    button.addEventListener("click", () => applyStageWeightProfile(button.dataset.stageProfile));
  });
  updateStageProfileControls();
}

function applyStageWeightProfile(level) {
  const profile = state.stageWeightProfiles[level];
  if (!profile) return;
  state.stageWeights = cloneWeights(profile.weights);
  state.stageWeightProfile = level;
  updateStageProfileControls();
  updateStageSettingsButton();
  configChanged();
  setStatus(
    `Stage 资产比例已切换为${profile.label}（${profile.shortLabel}），请重新回测后保存。`,
    "ok",
  );
}

function updateStageProfileControls() {
  els.stageProfileSwitch.querySelectorAll("[data-stage-profile]").forEach((button) => {
    const active = button.dataset.stageProfile === state.stageWeightProfile;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  els.stageProfileSwitch.classList.toggle("custom", !state.stageWeightProfile);
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
    state.stageWeightProfile = detectStageWeightProfile(state.stageWeights);
    updateStageProfileControls();
    updateStageSettingsButton();
    configChanged();
    closeStageSettings();
    const appliedProfile = state.stageWeightProfiles[state.stageWeightProfile];
    setStatus(
      appliedProfile
        ? `Stage 资产比例已切换为${appliedProfile.label}（${appliedProfile.shortLabel}），请重新回测后保存。`
        : "Stage 资产比例已更新为自定义配置，请重新回测后保存。",
      "ok",
    );
  } catch (err) {
    els.stageWeightStatus.textContent = err.message || String(err);
  }
}

function resetStageWeights() {
  const profile = state.stageWeightProfiles["3"];
  renderStageWeightRows(profile.weights);
  els.stageWeightStatus.textContent = "已恢复第三档（均衡），点击“应用”生效";
}

function updateStageSettingsButton() {
  const profile = state.stageWeightProfiles[state.stageWeightProfile];
  const custom = !profile;
  els.stageSettingsBtn.classList.remove("active-setting", "tilt-equity", "tilt-bond", "tilt-neutral");
  if (custom) {
    els.stageSettingsBtn.classList.add("active-setting");
  } else if (["1", "2"].includes(state.stageWeightProfile)) {
    els.stageSettingsBtn.classList.add("tilt-equity");
  } else if (["4", "5"].includes(state.stageWeightProfile)) {
    els.stageSettingsBtn.classList.add("tilt-bond");
  } else {
    els.stageSettingsBtn.classList.add("tilt-neutral");
  }
  els.stageSettingsBtn.textContent = profile
    ? `Stage 比例 · ${profile.label}`
    : "Stage 比例 · 自定义";
}

function cloneWeights(weights) {
  return JSON.parse(JSON.stringify(weights || {}));
}

function detectStageWeightProfile(weights) {
  for (const [level, profile] of Object.entries(state.stageWeightProfiles)) {
    if (stageWeightsMatch(weights, profile.weights)) return level;
  }
  return null;
}

function stageWeightsMatch(left, right) {
  return stageNumbers.every((stage) =>
    categoryOrder.every(
      (category) =>
        Math.abs(Number(left?.[stage]?.[category]) - Number(right?.[stage]?.[category])) < 0.00001,
    ),
  );
}

function formatWeightInput(value) {
  return Number(value.toFixed(6)).toString();
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
  const benchmark = data.benchmark || {};
  const benchmarkName = benchmark.name || "对照基准";
  const activeControls = Object.entries(data.ma20Controls || {})
    .filter(([, enabled]) => enabled)
    .map(([key]) => basketLabels[key])
    .join("、");
  const spliceText = data.spliceContext?.enabled
    ? `；模拟拼接：${data.spliceContext.indexStart} 至 ${data.spliceContext.indexEnd} 用指数，${data.spliceContext.fundStart} 起用基金`
    : "";
  const stats = data.rebalanceStats || {};
  const rebalanceText = `策略调仓 ${stats.strategyTotal ?? 0} 次（Stage变化 ${stats.stageChanges ?? 0} 次，三个月再平衡 ${stats.threeMonth ?? 0} 次；分级风控动作 ${stats.riskActions ?? 0} 次）`;
  const benchmarkCoverage = benchmark.partial
    ? `局部对比 ${benchmark.comparisonStart} 至 ${benchmark.comparisonEnd}`
    : `完整覆盖 ${benchmark.comparisonStart} 至 ${benchmark.comparisonEnd}`;
  els.windowText.textContent = `${data.window.start} 至 ${data.window.end}，共 ${data.window.days} 个交易日；对照基准：${benchmarkName}（${benchmarkCoverage}）；${rebalanceText}；MA20 + KST 风控：${activeControls || "关闭"}${spliceText}。`;
  els.navChartSubtitle.textContent = `策略 / 理论无风控 / ${benchmarkName}`;
  els.annualReturnSubtitle.textContent = `策略 vs ${benchmarkName}`;
  els.annualContributionSubtitle.textContent = `四类资产驱动力 vs ${benchmarkName}`;
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
  const benchmarkName = data.benchmark?.name || "对照基准";
  drawLineChart("navChart", data.series, [
    { key: "strategy", label: "策略", color: colors.strategy },
    { key: "theory", label: "理论", color: colors.theory, dashed: true },
    { key: "benchmark", label: benchmarkName, color: colors.benchmark },
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
    { key: "benchmark", label: benchmarkName, color: "#9aa5b1" },
  ]);

  drawSignedStackedBarChart("annualContributionChart", data.annualAttribution, [
    { key: "equity", label: "股票", color: colors.equity },
    { key: "convertible", label: "可转债", color: colors.convertible },
    { key: "commodity", label: "商品", color: colors.commodity },
    { key: "pureBond", label: "纯债", color: colors.pureBond },
  ], {
    lineSeries: [
      { key: "strategy", label: "策略总收益", color: "#17202a" },
      { key: "benchmark", label: benchmarkName, color: "#9aa5b1" },
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
  const benchmarkName = data.benchmark?.name || "对照基准";

  els.annualTable.innerHTML = table(
    ["年份", "策略", benchmarkName, "股票贡献", "商品贡献", "转债贡献", "纯债贡献"],
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
    data.benchmark?.name || "对照基准",
  );
}

function renderStageAttribution(rows, benchmarkName) {
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
          <th rowspan="2">${escapeHtml(benchmarkName)}</th>
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
      const value = row[s.key];
      if (!Number.isFinite(value)) return;
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
  const lineValues = lineSeries.flatMap((line) =>
    rows.map((row) => row[line.key]).filter(Number.isFinite),
  );
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
    let started = false;
    rows.forEach((row, i) => {
      const center = pad.left + groupW * i + groupW / 2;
      const value = row[line.key];
      if (!Number.isFinite(value)) return;
      if (!started) {
        ctx.moveTo(center, y(value));
        started = true;
      } else {
        ctx.lineTo(center, y(value));
      }
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

function wireStrategyEvents() {
  window.addEventListener("hashchange", handleRoute);
  els.strategyLibraryBtn.addEventListener("click", () => {
    window.location.hash = "strategies";
  });
  els.workspaceNavBtn.addEventListener("click", () => {
    window.location.hash = "workspace";
  });
  els.saveStrategyBtn.addEventListener("click", openSaveStrategyModal);
  els.closeStrategyModalBtn.addEventListener("click", closeStrategyModal);
  els.cancelStrategyModalBtn.addEventListener("click", closeStrategyModal);
  els.strategyModal.addEventListener("click", (event) => {
    if (event.target === els.strategyModal) closeStrategyModal();
  });
  els.strategyNotesInput.addEventListener("input", () => {
    els.strategyNotesCount.textContent = `${els.strategyNotesInput.value.length} / 2000`;
  });
  els.strategyTagSelector.addEventListener("change", handleStrategyTagSelection);
  els.submitStrategyBtn.addEventListener("click", () => submitStrategy(false));
  els.saveAsStrategyBtn.addEventListener("click", () => submitStrategy(true));
  els.strategySearchInput.addEventListener("input", renderStrategyCards);
  els.strategyTagFilter.addEventListener("click", handleStrategyTagFilter);
  els.strategyCards.addEventListener("click", handleStrategyCardAction);
  els.tagManagerBtn.addEventListener("click", openTagManager);
  els.closeTagManagerBtn.addEventListener("click", closeTagManager);
  els.tagManagerModal.addEventListener("click", (event) => {
    if (event.target === els.tagManagerModal) closeTagManager();
  });
  els.addRootTagBtn.addEventListener("click", () => showTagEditor(null, null));
  els.tagManagerTree.addEventListener("click", handleTagManagerAction);
  els.tagEditorForm.addEventListener("submit", saveTagEditor);
  els.deleteTagBtn.addEventListener("click", deleteCurrentTag);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!els.strategyModal.classList.contains("hidden")) closeStrategyModal();
    if (!els.tagManagerModal.classList.contains("hidden")) closeTagManager();
  });
}

async function apiRequest(path, options = {}) {
  const request = { ...options };
  request.headers = { ...(options.headers || {}) };
  if (options.body && typeof options.body !== "string") {
    request.headers["Content-Type"] = "application/json";
    request.body = JSON.stringify(options.body);
  }
  const response = await fetch(appUrl(path), request);
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "操作失败");
  return data;
}

async function loadStrategyLibrary() {
  const data = await apiRequest("/api/strategies");
  state.strategies = data.strategies || [];
  state.tags = data.tags || [];
  if (
    state.strategyFilterTagId
    && !state.tags.some((tag) => tag.id === state.strategyFilterTagId)
  ) {
    state.strategyFilterTagId = null;
  }
  if (
    state.activeStrategyId
    && !state.strategies.some((strategy) => strategy.id === state.activeStrategyId)
  ) {
    state.activeStrategyId = null;
  }
  renderStrategyTagFilter();
  renderStrategyCards();
  renderTagManagerTree();
}

function handleRoute() {
  const showLibrary = window.location.hash === "#strategies";
  els.workspaceView.classList.toggle("hidden", showLibrary);
  els.strategyLibraryView.classList.toggle("hidden", !showLibrary);
  els.workspaceNavBtn.classList.toggle("hidden", !showLibrary);
  els.strategyLibraryBtn.classList.toggle("hidden", showLibrary);
  document.querySelectorAll(".workspace-only").forEach((element) => {
    element.classList.toggle("hidden", showLibrary);
  });
  if (showLibrary) {
    loadStrategyLibrary().catch((err) => {
      els.strategyLibraryCount.textContent = err.message || String(err);
    });
  }
}

function renderStrategyTagFilter() {
  const selected = state.tags.find((tag) => tag.id === state.strategyFilterTagId);
  const selectedPathIds = selected?.pathIds || [];
  const tagsByParent = new Map();
  state.tags.forEach((tag) => {
    const parentId = tag.parentId || "";
    if (!tagsByParent.has(parentId)) tagsByParent.set(parentId, []);
    tagsByParent.get(parentId).push(tag);
  });
  tagsByParent.forEach((tags, parentId) => {
    tags.sort((left, right) => {
      const leftRootOrder = strategyRootTagOrder.indexOf(left.name);
      const rightRootOrder = strategyRootTagOrder.indexOf(right.name);
      const rootOrder = parentId === ""
        ? (leftRootOrder < 0 ? strategyRootTagOrder.length : leftRootOrder)
          - (rightRootOrder < 0 ? strategyRootTagOrder.length : rightRootOrder)
        : 0;
      return (
        rootOrder
        || left.name.localeCompare(right.name, "zh-CN")
        || left.id.localeCompare(right.id)
      );
    });
  });

  const rows = [];
  const roots = tagsByParent.get("") || [];
  rows.push(renderStrategyFilterRow({
    depth: 1,
    label: "一级标签",
    tags: roots,
    resetLabel: "全部策略",
    resetTagId: "",
    resetActive: !state.strategyFilterTagId,
    selectedPathIds,
  }));

  const rootId = selectedPathIds[0];
  const secondLevel = rootId ? (tagsByParent.get(rootId) || []) : [];
  if (secondLevel.length) {
    rows.push(renderStrategyFilterRow({
      depth: 2,
      label: "二级标签",
      tags: secondLevel,
      resetLabel: "全部",
      resetTagId: rootId,
      resetActive: state.strategyFilterTagId === rootId,
      selectedPathIds,
    }));
  }

  const secondLevelId = selectedPathIds[1];
  const thirdLevel = secondLevelId ? (tagsByParent.get(secondLevelId) || []) : [];
  if (thirdLevel.length) {
    rows.push(renderStrategyFilterRow({
      depth: 3,
      label: "三级标签",
      tags: thirdLevel,
      resetLabel: "全部",
      resetTagId: secondLevelId,
      resetActive: state.strategyFilterTagId === secondLevelId,
      selectedPathIds,
    }));
  }
  els.strategyTagFilter.innerHTML = rows.join("");
}

function renderStrategyFilterRow({
  depth,
  label,
  tags,
  resetLabel,
  resetTagId,
  resetActive,
  selectedPathIds,
}) {
  const buttons = [
    `
      <button
        class="strategy-filter-chip reset${resetActive ? " active" : ""}"
        type="button"
        data-strategy-filter-tag-id="${escapeHtml(resetTagId)}"
      >${escapeHtml(resetLabel)}</button>
    `,
    ...tags.map((tag) => `
      <button
        class="strategy-filter-chip${selectedPathIds.includes(tag.id) ? " active" : ""}${tag.active ? "" : " inactive"}"
        type="button"
        data-strategy-filter-tag-id="${escapeHtml(tag.id)}"
        title="${escapeHtml(tag.path)}${tag.active ? "" : "（已停用）"}"
      >
        <span>${escapeHtml(tag.name)}</span>
        <small>${countStrategiesForTag(tag.id)}</small>
      </button>
    `),
  ].join("");
  return `
    <div class="strategy-filter-row depth-${depth}">
      <span class="strategy-filter-level">${label}</span>
      <div class="strategy-filter-options">${buttons}</div>
    </div>
  `;
}

function countStrategiesForTag(tagId) {
  return state.strategies.filter((strategy) => (
    (strategy.tagPaths || []).some((item) => item.pathIds.includes(tagId))
  )).length;
}

function handleStrategyTagFilter(event) {
  const button = event.target.closest("[data-strategy-filter-tag-id]");
  if (!button) return;
  state.strategyFilterTagId = button.dataset.strategyFilterTagId || null;
  renderStrategyTagFilter();
  renderStrategyCards();
}

function renderStrategyCards() {
  const query = els.strategySearchInput.value.trim().toLowerCase();
  const tagId = state.strategyFilterTagId;
  const filtered = state.strategies.filter((strategy) => {
    const tagText = (strategy.tagPaths || []).map((item) => item.path).join(" ");
    const haystack = `${strategy.name} ${strategy.notes || ""} ${tagText}`.toLowerCase();
    const matchesText = !query || haystack.includes(query);
    const matchesTag = !tagId || (strategy.tagPaths || []).some(
      (item) => item.pathIds.includes(tagId),
    );
    return matchesText && matchesTag;
  });
  els.strategyLibraryCount.textContent =
    `共保存 ${state.strategies.length} 个策略，当前显示 ${filtered.length} 个`;
  if (!filtered.length) {
    els.strategyCards.innerHTML = `
      <div class="strategy-empty">
        <h3>${state.strategies.length ? "没有符合筛选条件的策略" : "策略库还是空的"}</h3>
        <p>${state.strategies.length ? "调整搜索词或标签筛选后再看。" : "完成一次回测后，可从工作台保存当前策略。"}</p>
      </div>
    `;
    return;
  }
  els.strategyCards.innerHTML = filtered.map(renderStrategyCard).join("");
}

function renderStrategyCard(strategy) {
  const summary = strategy.summary || {};
  const windowInfo = summary.window || {};
  const tags = (strategy.tagPaths || []).length
    ? strategy.tagPaths.map((item) => (
      `<span class="strategy-tag${item.active ? "" : " inactive"}">${escapeHtml(item.path)}</span>`
    )).join("")
    : `<span class="strategy-tag empty">未设置标签</span>`;
  const missing = (strategy.missingAssets || []).length;
  const missingBenchmark = Boolean(strategy.missingBenchmark);
  return `
    <article class="strategy-card${missing || missingBenchmark ? " has-missing-assets" : ""}">
      <header class="strategy-card-head">
        <div>
          <h3>${escapeHtml(strategy.name)}</h3>
          <p>更新于 ${escapeHtml(formatDateTime(strategy.updatedAt))}</p>
        </div>
        <span class="asset-count-badge">${strategy.assetCount || 0} 个标的</span>
      </header>
      <div class="strategy-tags">${tags}</div>
      <p class="strategy-notes">${escapeHtml(strategy.notes || "暂无备注")}</p>
      ${missing ? `<p class="missing-warning">有 ${missing} 个标的已失效，暂时不能载入</p>` : ""}
      ${missingBenchmark ? `<p class="missing-warning">对照基准 ${escapeHtml(strategy.missingBenchmark.id)} 已失效，暂时不能载入</p>` : ""}
      <div class="strategy-metrics">
        <div><span>回测区间</span><strong>${escapeHtml(windowInfo.start || "-")}<br>${escapeHtml(windowInfo.end || "-")}</strong></div>
        <div><span>累计收益</span><strong>${pct(summary.totalReturn)}</strong></div>
        <div><span>年化收益</span><strong>${pct(summary.annualReturn)}</strong></div>
        <div><span>最大回撤</span><strong>${pct(summary.maxDrawdown)}</strong></div>
        <div><span>夏普</span><strong>${num(summary.sharpe)}</strong></div>
      </div>
      <footer class="strategy-card-actions">
        <button class="ghost-btn" type="button" data-strategy-action="load" data-id="${strategy.id}">载入</button>
        <button class="primary-btn" type="button" data-strategy-action="rerun" data-id="${strategy.id}">载入并回测</button>
        <button class="ghost-btn" type="button" data-strategy-action="edit" data-id="${strategy.id}">编辑</button>
        <button class="ghost-btn" type="button" data-strategy-action="duplicate" data-id="${strategy.id}">复制</button>
        <button class="ghost-btn danger-btn" type="button" data-strategy-action="delete" data-id="${strategy.id}">删除</button>
      </footer>
    </article>
  `;
}

async function handleStrategyCardAction(event) {
  const button = event.target.closest("[data-strategy-action]");
  if (!button) return;
  const strategy = state.strategies.find((item) => item.id === button.dataset.id);
  if (!strategy) return;
  const action = button.dataset.strategyAction;
  if (action === "load" || action === "rerun") {
    const loaded = loadStrategyIntoWorkspace(strategy);
    if (loaded && action === "rerun") {
      button.disabled = true;
      setStatus(`正在重新回测策略“${strategy.name}”...`, "");
      try {
        const data = await apiRequest(`/api/strategies/${strategy.id}/rerun`, {
          method: "POST",
          body: {},
        });
        state.result = data.result;
        state.lastSuccessfulConfigSignature = currentConfigSignature();
        renderResult(data.result);
        updateSaveStrategyState();
        await loadStrategyLibrary();
        setStatus(`策略“${strategy.name}”重新回测完成，核心指标已更新。`, "ok");
      } catch (err) {
        setStatus(err.message || String(err), "error");
      } finally {
        button.disabled = false;
      }
    }
    return;
  }
  if (action === "edit") {
    openMetadataEditor(strategy);
    return;
  }
  if (action === "duplicate") {
    button.disabled = true;
    try {
      const duplicate = await apiRequest(`/api/strategies/${strategy.id}/duplicate`, {
        method: "POST",
        body: {},
      });
      await loadStrategyLibrary();
      setLibraryNotice(`已复制为“${duplicate.name}”。`);
    } catch (err) {
      setLibraryNotice(err.message || String(err), true);
    } finally {
      button.disabled = false;
    }
    return;
  }
  if (action === "delete") {
    if (!window.confirm(`确定删除策略“${strategy.name}”吗？此操作不能撤销。`)) return;
    try {
      await apiRequest(`/api/strategies/${strategy.id}`, { method: "DELETE" });
      await loadStrategyLibrary();
      setLibraryNotice("策略已删除。");
    } catch (err) {
      setLibraryNotice(err.message || String(err), true);
    }
  }
}

function strategyAssetIds(strategy) {
  const config = strategy.config || {};
  const ids = [];
  categoryOrder.forEach((category) => {
    ids.push(...(config.baskets?.[category] || []));
    if (config.spliceSimulation?.enabled) {
      ids.push(...(config.spliceSimulation?.baskets?.[category] || []));
    }
  });
  return [...new Set(ids)];
}

function loadStrategyIntoWorkspace(strategy) {
  const snapshotMap = new Map(
    (strategy.assetSnapshots || []).map((asset) => [asset.id, asset]),
  );
  const missing = strategyAssetIds(strategy)
    .filter((id) => !state.assetsById.has(id))
    .map((id) => snapshotMap.get(id) || { id, name: id, code: id });
  if (missing.length) {
    const detail = missing.map((asset) => `${asset.name}（${asset.code}）`).join("\n");
    window.alert(`以下标的已失效，策略未载入：\n${detail}`);
    return false;
  }

  const config = strategy.config;
  const benchmarkId = config.benchmarkId || state.defaultBenchmarkId;
  if (!state.assetsById.has(benchmarkId)) {
    window.alert(`对照基准已失效，策略未载入：\n${benchmarkId}`);
    return false;
  }
  const nextBaskets = {};
  const nextSpliceBaskets = {};
  categoryOrder.forEach((category) => {
    nextBaskets[category] = [...(config.baskets?.[category] || [])];
    nextSpliceBaskets[category] = [...(config.spliceSimulation?.baskets?.[category] || [])];
  });
  state.baskets = nextBaskets;
  state.spliceBaskets = nextSpliceBaskets;
  state.benchmarkId = benchmarkId;
  state.stageWeights = cloneWeights(config.stageWeights);
  state.stageWeightProfile = config.stageWeightProfile === "custom"
    ? detectStageWeightProfile(state.stageWeights)
    : String(config.stageWeightProfile || detectStageWeightProfile(state.stageWeights));
  els.spliceToggle.checked = Boolean(config.spliceSimulation?.enabled);
  els.ma20Equity.checked = Boolean(config.ma20Controls?.equity);
  els.ma20Commodity.checked = Boolean(config.ma20Controls?.commodity);
  renderBenchmarkControl();
  renderBaskets();
  renderSplicePool();
  els.startDate.value = config.dateRange?.start || "";
  els.endDate.value = config.dateRange?.end || "";
  validateDateInputs();
  updateStageProfileControls();
  updateStageSettingsButton();
  state.activeStrategyId = strategy.id;
  state.result = null;
  state.lastSuccessfulConfigSignature = null;
  els.results.classList.add("hidden");
  updateSaveStrategyState();
  window.location.hash = "workspace";
  setStatus(`已载入策略“${strategy.name}”，请重新回测后保存或更新。`, "ok");
  return true;
}

function openSaveStrategyModal() {
  if (els.saveStrategyBtn.disabled) {
    setStatus("请先完成与当前配置匹配的成功回测。", "error");
    return;
  }
  const strategy = state.strategies.find((item) => item.id === state.activeStrategyId);
  state.strategyModalMode = "save";
  state.editingStrategyId = strategy?.id || null;
  state.selectedStrategyTagIds = new Set(strategy?.tagIds || []);
  els.strategyModalTitle.textContent = strategy ? "保存策略变更" : "保存策略";
  els.strategyModalHint.textContent = strategy
    ? `当前载入策略：${strategy.name}`
    : "保存当前已完成回测的配置和核心指标。";
  els.strategyNameInput.value = strategy?.name || `策略 ${new Date().toLocaleDateString("zh-CN")}`;
  els.strategyNotesInput.value = strategy?.notes || "";
  els.strategyNotesCount.textContent = `${els.strategyNotesInput.value.length} / 2000`;
  els.saveAsStrategyBtn.classList.toggle("hidden", !strategy);
  els.submitStrategyBtn.textContent = strategy ? "更新当前策略" : "保存策略";
  els.strategyFormError.textContent = "";
  renderStrategyTagSelector();
  openModal(els.strategyModal);
  els.strategyNameInput.focus();
}

function openMetadataEditor(strategy) {
  state.strategyModalMode = "metadata";
  state.editingStrategyId = strategy.id;
  state.selectedStrategyTagIds = new Set(strategy.tagIds || []);
  els.strategyModalTitle.textContent = "编辑策略信息";
  els.strategyModalHint.textContent = "仅修改策略名、标签和备注，不重新运行回测。";
  els.strategyNameInput.value = strategy.name;
  els.strategyNotesInput.value = strategy.notes || "";
  els.strategyNotesCount.textContent = `${els.strategyNotesInput.value.length} / 2000`;
  els.saveAsStrategyBtn.classList.add("hidden");
  els.submitStrategyBtn.textContent = "保存元数据";
  els.strategyFormError.textContent = "";
  renderStrategyTagSelector();
  openModal(els.strategyModal);
  els.strategyNameInput.focus();
}

function renderStrategyTagSelector() {
  const selected = state.selectedStrategyTagIds;
  const sorted = state.tags.slice().sort((a, b) => a.path.localeCompare(b.path, "zh-CN"));
  if (!sorted.length) {
    els.strategyTagSelector.innerHTML = `
      <div class="tag-selector-empty">尚未创建标签，可在策略库的“标签管理”中添加。</div>
    `;
    return;
  }
  els.strategyTagSelector.innerHTML = sorted.map((tag) => {
    const checked = selected.has(tag.id);
    const disabled = !tag.active && !checked;
    return `
      <label class="tag-select-row depth-${tag.depth}${tag.active ? "" : " inactive"}">
        <input type="checkbox" value="${tag.id}" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""} />
        <span>${escapeHtml(tag.name)}</span>
        <small>${escapeHtml(tag.path)}</small>
      </label>
    `;
  }).join("");
}

function handleStrategyTagSelection(event) {
  const input = event.target.closest('input[type="checkbox"]');
  if (!input) return;
  if (input.checked) {
    state.selectedStrategyTagIds.add(input.value);
  } else {
    state.selectedStrategyTagIds.delete(input.value);
  }
  normalizeSelectedStrategyTags();
  renderStrategyTagSelector();
}

function normalizeSelectedStrategyTags() {
  const selected = state.selectedStrategyTagIds;
  const selectedTags = state.tags.filter((tag) => selected.has(tag.id));
  selectedTags.forEach((candidate) => {
    const isAncestor = selectedTags.some(
      (other) => other.id !== candidate.id && other.pathIds.slice(0, -1).includes(candidate.id),
    );
    if (isAncestor) selected.delete(candidate.id);
  });
}

async function submitStrategy(forceNew) {
  const name = els.strategyNameInput.value.trim();
  if (!name) {
    els.strategyFormError.textContent = "请输入策略名。";
    return;
  }
  normalizeSelectedStrategyTags();
  const metadata = {
    name,
    notes: els.strategyNotesInput.value.trim(),
    tagIds: [...state.selectedStrategyTagIds],
  };
  const button = forceNew ? els.saveAsStrategyBtn : els.submitStrategyBtn;
  button.disabled = true;
  els.strategyFormError.textContent = "";
  try {
    let saved;
    if (state.strategyModalMode === "metadata") {
      saved = await apiRequest(`/api/strategies/${state.editingStrategyId}`, {
        method: "PATCH",
        body: metadata,
      });
    } else {
      if (
        !state.result
        || state.lastSuccessfulConfigSignature !== currentConfigSignature()
      ) {
        throw new Error("当前配置已变化，请重新回测后再保存。");
      }
      const payload = { ...metadata, config: currentConfig() };
      if (state.editingStrategyId && !forceNew) {
        saved = await apiRequest(`/api/strategies/${state.editingStrategyId}`, {
          method: "PUT",
          body: payload,
        });
      } else {
        saved = await apiRequest("/api/strategies", {
          method: "POST",
          body: payload,
        });
      }
      state.activeStrategyId = saved.id;
    }
    await loadStrategyLibrary();
    closeStrategyModal();
    if (window.location.hash === "#strategies") {
      setLibraryNotice(`策略“${saved.name}”已保存。`);
    } else {
      setStatus(`策略“${saved.name}”已保存。`, "ok");
    }
  } catch (err) {
    els.strategyFormError.textContent = err.message || String(err);
  } finally {
    button.disabled = false;
  }
}

function closeStrategyModal() {
  els.strategyModal.classList.add("hidden");
  syncModalBodyState();
}

function openTagManager() {
  renderTagManagerTree();
  els.tagEditorForm.classList.add("hidden");
  openModal(els.tagManagerModal);
}

function closeTagManager() {
  els.tagManagerModal.classList.add("hidden");
  syncModalBodyState();
}

function renderTagManagerTree() {
  if (!els.tagManagerTree) return;
  const sorted = state.tags.slice().sort((a, b) => a.path.localeCompare(b.path, "zh-CN"));
  if (!sorted.length) {
    els.tagManagerTree.innerHTML = `<div class="tag-selector-empty">还没有标签，先新增一个一级标签。</div>`;
    return;
  }
  els.tagManagerTree.innerHTML = sorted.map((tag) => `
    <div class="tag-manager-row depth-${tag.depth}${tag.active ? "" : " inactive"}">
      <button type="button" class="tag-manager-main" data-tag-edit="${tag.id}">
        <span>${escapeHtml(tag.name)}</span>
        <small>${tag.active ? `第 ${tag.depth} 级` : "已停用"}</small>
      </button>
      ${tag.depth < 3 ? `<button type="button" class="tag-child-btn" data-tag-child="${tag.id}">新增下级</button>` : ""}
    </div>
  `).join("");
}

function handleTagManagerAction(event) {
  const editButton = event.target.closest("[data-tag-edit]");
  if (editButton) {
    const tag = state.tags.find((item) => item.id === editButton.dataset.tagEdit);
    if (tag) showTagEditor(tag, tag.parentId);
    return;
  }
  const childButton = event.target.closest("[data-tag-child]");
  if (childButton) showTagEditor(null, childButton.dataset.tagChild);
}

function showTagEditor(tag, parentId) {
  els.tagEditorForm.classList.remove("hidden");
  els.tagEditorId.value = tag?.id || "";
  els.tagNameInput.value = tag?.name || "";
  els.tagActiveInput.checked = tag?.active ?? true;
  els.tagActiveRow.classList.toggle("hidden", !tag);
  els.deleteTagBtn.classList.toggle("hidden", !tag);
  els.tagEditorError.textContent = "";
  renderTagParentOptions(tag, parentId);
  els.tagNameInput.focus();
}

function renderTagParentOptions(tag, parentId) {
  const excluded = new Set();
  if (tag) {
    state.tags.forEach((candidate) => {
      if (candidate.pathIds.includes(tag.id)) excluded.add(candidate.id);
    });
  }
  const options = state.tags
    .filter((candidate) => candidate.depth < 3 && !excluded.has(candidate.id))
    .sort((a, b) => a.path.localeCompare(b.path, "zh-CN"))
    .map((candidate) => (
      `<option value="${candidate.id}">${escapeHtml(candidate.path)}</option>`
    ))
    .join("");
  els.tagParentSelect.innerHTML = `<option value="">无（一级标签）</option>${options}`;
  els.tagParentSelect.value = parentId || "";
}

async function saveTagEditor(event) {
  event.preventDefault();
  const tagId = els.tagEditorId.value;
  const payload = {
    name: els.tagNameInput.value.trim(),
    parentId: els.tagParentSelect.value || null,
    active: els.tagActiveInput.checked,
  };
  els.tagEditorError.textContent = "";
  try {
    await apiRequest(tagId ? `/api/tags/${tagId}` : "/api/tags", {
      method: tagId ? "PATCH" : "POST",
      body: payload,
    });
    await loadStrategyLibrary();
    renderTagManagerTree();
    els.tagEditorForm.classList.add("hidden");
  } catch (err) {
    els.tagEditorError.textContent = err.message || String(err);
  }
}

async function deleteCurrentTag() {
  const tagId = els.tagEditorId.value;
  const tag = state.tags.find((item) => item.id === tagId);
  if (!tag) return;
  if (!window.confirm(`确定彻底删除标签“${tag.path}”吗？`)) return;
  try {
    await apiRequest(`/api/tags/${tagId}`, { method: "DELETE" });
    await loadStrategyLibrary();
    els.tagEditorForm.classList.add("hidden");
  } catch (err) {
    els.tagEditorError.textContent = err.message || String(err);
  }
}

function openModal(modal) {
  modal.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function syncModalBodyState() {
  const anyOpen = [...document.querySelectorAll(".modal")].some(
    (modal) => !modal.classList.contains("hidden"),
  );
  document.body.classList.toggle("modal-open", anyOpen);
}

function setLibraryNotice(text, isError = false) {
  els.strategyLibraryCount.textContent = text;
  els.strategyLibraryCount.classList.toggle("error-copy", isError);
  window.setTimeout(() => {
    els.strategyLibraryCount.classList.remove("error-copy");
    renderStrategyCards();
  }, 2200);
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
