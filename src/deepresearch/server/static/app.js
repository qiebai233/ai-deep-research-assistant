/* DeepResearch web UI — vanilla JavaScript, no frameworks, no external assets. */
"use strict";

(function () {
  // ------------------------------------------------------------------ //
  // i18n                                                                //
  // ------------------------------------------------------------------ //
  const I18N = {
    zh: {
      title: "DeepResearch · AI 深度调研助手",
      status_connecting: "连接后端…",
      status_ready: "就绪",
      status_ready_offline: "就绪 · 离线 mock",
      status_error: "后端不可用",
      eyebrow: "AI 深度调研助手",
      hero_title: "一个提问，一份带引用的深度报告。",
      hero_sub:
        "自动拆解问题、多轮检索、抓取正文、反思补检，最后写成分节 Markdown 报告 — 全程在本地运行，零第三方依赖。",
      meta_llm: "模型",
      meta_search: "搜索",
      meta_mode_offline: "离线模式",
      meta_mode_online: "在线模式",
      question_label: "研究问题",
      question_placeholder:
        "例如：固态电池在 2025 年的产业化进展如何？主要玩家和瓶颈是什么？",
      depth_label: "调研深度",
      depth_quick: "快速",
      depth_quick_desc: "3 子问题 · 1 轮",
      depth_standard: "标准",
      depth_standard_desc: "5 子问题 · 2 轮",
      depth_deep: "深度",
      depth_deep_desc: "7 子问题 · 3 轮",
      examples_label: "试试：",
      submit_hint: "Ctrl + Enter 快速提交 · 全部在本地运行",
      start: "开始调研",
      running: "调研中…",
      progress_waiting: "准备中…",
      research_kicker: "正在调研",
      result_kicker: "调研完成",
      download_md: "report.md",
      download_json: "result.json",
      copy: "复制 Markdown",
      new_research: "新建调研",
      footer_note: "零第三方依赖 · 本地运行 · 报告由 AI 生成，请核实关键数据",
      error_required: "请输入研究问题。",
      error_network: "无法连接后端服务，请确认 deepresearch serve 正在运行。",
      error_http: "请求失败，请稍后重试。",
      error_stream: "当前浏览器不支持流式响应。",
      error_no_result: "调研结束但未收到结果。",
      run_error_title: "调研中断了",
      retry: "重试",
      stage_done: "调研完成",
      stage_run_start: "启动调研",
      stage_plan_ready: "问题拆解完成",
      stage_search_start: "检索资料",
      stage_search_done: "检索完成",
      stage_fetch_start: "抓取正文",
      stage_source_ready: "读取来源",
      stage_findings_ready: "提炼发现",
      stage_gap_found: "发现证据缺口",
      stage_round_start: "补充检索",
      stage_outline_ready: "生成大纲",
      stage_section_ready: "撰写章节",
      stage_report_ready: "报告生成完成",
      stage_run_end: "完成",
      stage_warning: "提示",
      stage_error: "错误",
      stat_refs: "参考文献",
      stat_llm: "LLM 调用",
      stat_search: "检索次数",
      stat_fetch: "抓取次数",
      stat_tokens: "tokens",
      stat_elapsed: "耗时",
      stat_cost: "估算成本",
      report_untitled: "未命名报告",
      report_empty: "报告内容为空。",
      toast_copied: "已复制 Markdown",
      toast_copy_failed: "复制失败，请改用下载。",
      toast_download_failed: "下载失败，请稍后重试。",
    },
    en: {
      title: "DeepResearch · AI research assistant",
      status_connecting: "Connecting…",
      status_ready: "Ready",
      status_ready_offline: "Ready · offline mock",
      status_error: "Backend unavailable",
      eyebrow: "AI research assistant",
      hero_title: "One question. One cited, in-depth report.",
      hero_sub:
        "It plans sub-questions, searches in rounds, fetches full pages, reflects on gaps and writes a sectioned Markdown report — entirely on your machine, with zero dependencies.",
      meta_llm: "Model",
      meta_search: "Search",
      meta_mode_offline: "Offline mode",
      meta_mode_online: "Online mode",
      question_label: "Research question",
      question_placeholder:
        "e.g. How far has solid-state battery commercialisation progressed in 2025, and who are the key players?",
      depth_label: "Research depth",
      depth_quick: "Quick",
      depth_quick_desc: "3 sub-questions · 1 round",
      depth_standard: "Standard",
      depth_standard_desc: "5 sub-questions · 2 rounds",
      depth_deep: "Deep",
      depth_deep_desc: "7 sub-questions · 3 rounds",
      examples_label: "Try:",
      submit_hint: "Ctrl + Enter to submit · runs entirely locally",
      start: "Start research",
      running: "Researching…",
      progress_waiting: "Preparing…",
      research_kicker: "Researching",
      result_kicker: "Research complete",
      download_md: "report.md",
      download_json: "result.json",
      copy: "Copy Markdown",
      new_research: "New research",
      footer_note:
        "Zero dependencies · runs locally · AI-generated content, verify key facts",
      error_required: "Please enter a research question.",
      error_network: "Cannot reach the backend. Is deepresearch serve running?",
      error_http: "Request failed, please try again.",
      error_stream: "Streaming responses are not supported by this browser.",
      error_no_result: "The run finished without a result.",
      run_error_title: "Research interrupted",
      retry: "Retry",
      stage_done: "Research complete",
      stage_run_start: "Starting research",
      stage_plan_ready: "Plan ready",
      stage_search_start: "Searching",
      stage_search_done: "Search complete",
      stage_fetch_start: "Fetching pages",
      stage_source_ready: "Source ready",
      stage_findings_ready: "Findings ready",
      stage_gap_found: "Gap found",
      stage_round_start: "Extra round",
      stage_outline_ready: "Outline ready",
      stage_section_ready: "Writing section",
      stage_report_ready: "Report ready",
      stage_run_end: "Finished",
      stage_warning: "Notice",
      stage_error: "Error",
      stat_refs: "references",
      stat_llm: "LLM calls",
      stat_search: "searches",
      stat_fetch: "fetches",
      stat_tokens: "tokens",
      stat_elapsed: "elapsed",
      stat_cost: "est. cost",
      report_untitled: "Untitled report",
      report_empty: "This report is empty.",
      toast_copied: "Markdown copied",
      toast_copy_failed: "Copy failed — use the download button instead.",
      toast_download_failed: "Download failed, please try again.",
    },
  };

  const EXAMPLES = {
    zh: [
      "固态电池在 2025 年的产业化进展如何？主要玩家和瓶颈是什么？",
      "RAG（检索增强生成）技术最近两年有哪些关键演进？",
      "中国新能源汽车出口的增长趋势与主要海外市场",
      "室温超导研究目前有哪些可信进展与争议？",
    ],
    en: [
      "How far has solid-state battery commercialisation progressed in 2025?",
      "How has retrieval-augmented generation (RAG) evolved in the last two years?",
      "China's NEV export growth and its main overseas markets",
      "What credible progress and controversy exist in room-temperature superconductor research?",
    ],
  };

  const EVENT_ICONS = {
    run_start: "▶",
    plan_ready: "◈",
    search_start: "⌕",
    search_done: "⌕",
    fetch_start: "↓",
    source_ready: "✓",
    findings_ready: "◈",
    gap_found: "?",
    round_start: "↻",
    outline_ready: "☰",
    section_ready: "✎",
    report_ready: "★",
    run_end: "■",
    warning: "!",
    error: "✗",
  };

  const LANG_KEY = "deepresearch.lang";
  const MAX_LOG_ITEMS = 400;

  // ------------------------------------------------------------------ //
  // State + elements                                                    //
  // ------------------------------------------------------------------ //
  const state = {
    lang: loadLang(),
    health: null,
    config: null,
    running: false,
    lastPercent: 0,
    result: null,
    lastRequest: null,
  };

  const $ = (id) => document.getElementById(id);

  const els = {
    version: $("version"),
    footerVersion: $("footer-version"),
    statusBadge: $("status-badge"),
    statusText: $("status-text"),
    langToggle: $("lang-toggle"),
    metaProvider: $("meta-provider"),
    metaModel: $("meta-model"),
    metaSearch: $("meta-search"),
    metaMode: $("meta-mode"),
    compose: $("compose"),
    question: $("question"),
    submit: $("submit"),
    submitLabel: $("submit").querySelector("span"),
    formError: $("form-error"),
    examples: $("examples"),
    research: $("research"),
    researchQuestion: $("research-question"),
    researchDepth: $("research-depth"),
    progressTrack: $("progress-track"),
    progressBar: $("progress-bar"),
    progressStage: $("progress-stage"),
    progressPercent: $("progress-percent"),
    log: $("log"),
    runError: $("run-error"),
    runErrorText: $("run-error-text"),
    retry: $("retry"),
    result: $("result"),
    reportTitle: $("report-title"),
    summaryText: $("summary-text"),
    takeaways: $("takeaways"),
    stats: $("stats"),
    report: $("report"),
    newResearch: $("new-research"),
    toast: $("toast"),
  };

  // ------------------------------------------------------------------ //
  // Small helpers                                                       //
  // ------------------------------------------------------------------ //
  function t(key) {
    const table = I18N[state.lang] || I18N.zh;
    if (Object.prototype.hasOwnProperty.call(table, key)) return table[key];
    return Object.prototype.hasOwnProperty.call(I18N.zh, key) ? I18N.zh[key] : key;
  }

  function loadLang() {
    try {
      const saved = localStorage.getItem(LANG_KEY);
      if (saved === "zh" || saved === "en") return saved;
    } catch (error) {
      /* storage can be disabled — fall through to the default */
    }
    return "zh";
  }

  function saveLang() {
    try {
      localStorage.setItem(LANG_KEY, state.lang);
    } catch (error) {
      /* ignore */
    }
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function pad2(value) {
    return String(value).padStart(2, "0");
  }

  function formatTime(value) {
    const date = value ? new Date(value) : new Date();
    if (Number.isNaN(date.getTime())) return "";
    return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
  }

  function formatDuration(seconds) {
    if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return "—";
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m ${Math.round(seconds % 60)}s`;
  }

  function formatNumber(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "0";
    return value.toLocaleString(state.lang === "zh" ? "zh-CN" : "en-US");
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function friendlyError(error) {
    if (!error) return t("error_http");
    if (error.name === "AbortError") return t("error_network");
    if (error instanceof TypeError) return t("error_network");
    return error.message || t("error_http");
  }

  // ------------------------------------------------------------------ //
  // Language / static text                                              //
  // ------------------------------------------------------------------ //
  function applyLang() {
    const html = document.documentElement;
    html.setAttribute("lang", state.lang === "zh" ? "zh-CN" : "en");
    html.setAttribute("data-lang", state.lang);
    document.title = t("title");
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      node.textContent = t(node.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
      node.setAttribute("placeholder", t(node.getAttribute("data-i18n-placeholder")));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((node) => {
      node.setAttribute("title", t(node.getAttribute("data-i18n-title")));
    });
    els.langToggle.textContent = state.lang === "zh" ? "EN" : "中文";
    els.langToggle.setAttribute(
      "aria-label",
      state.lang === "zh" ? "Switch to English" : "切换到中文"
    );
    renderExamples();
    renderStatus();
    renderMeta();
    updateSubmitLabel();
    if (state.result) renderStats(state.result);
  }

  function toggleLang() {
    state.lang = state.lang === "zh" ? "en" : "zh";
    saveLang();
    applyLang();
  }

  // ------------------------------------------------------------------ //
  // Backend health / config                                             //
  // ------------------------------------------------------------------ //
  async function fetchJson(url, options) {
    const settings = options || {};
    const timeout = settings.timeout || 8000;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, {
        method: settings.method || "GET",
        headers: settings.headers || {},
        body: settings.body,
        signal: controller.signal,
      });
      const text = await response.text();
      let data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch (error) {
        data = { error: text };
      }
      if (!response.ok) {
        const message = (data && data.error) || `${response.status} ${response.statusText}`;
        const failure = new Error(message);
        failure.status = response.status;
        throw failure;
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  async function loadBackend() {
    try {
      state.health = await fetchJson("/api/health", { timeout: 4000 });
    } catch (error) {
      state.health = null;
    }
    try {
      state.config = await fetchJson("/api/config", { timeout: 4000 });
    } catch (error) {
      state.config = null;
    }
    renderStatus();
    renderMeta();
    applyConfigDefaults();
  }

  function applyConfigDefaults() {
    const depth = state.config && state.config.depth;
    if (depth === "quick" || depth === "standard" || depth === "deep") {
      setDepth(depth);
    }
  }

  function renderStatus() {
    const badge = els.statusBadge;
    badge.classList.remove("status--ok", "status--warn", "status--error", "status--pending");
    if (state.health && state.health.ok) {
      const offline = Boolean(state.health.offline);
      badge.classList.add(offline ? "status--ok" : "status--warn");
      els.statusText.textContent = offline ? t("status_ready_offline") : t("status_ready");
      const parts = [`v${state.health.version || "0.1.0"}`];
      const config = state.config;
      if (config) {
        parts.push(`${t("meta_llm")}: ${config.llm_provider}/${config.llm_model}`);
        parts.push(`${t("meta_search")}: ${config.search_provider}`);
      }
      badge.title = parts.join(" · ");
      els.version.textContent = `v${state.health.version || "0.1.0"}`;
      els.footerVersion.textContent = `v${state.health.version || "0.1.0"}`;
    } else {
      badge.classList.add("status--error");
      els.statusText.textContent = t("status_error");
      badge.title = t("error_network");
    }
  }

  function renderMeta() {
    const config = state.config;
    if (!config) {
      els.metaProvider.textContent = "—";
      els.metaModel.textContent = "—";
      els.metaSearch.textContent = "—";
      els.metaMode.textContent = "—";
      els.metaMode.className = "meta-item pill";
      return;
    }
    els.metaProvider.textContent = `${t("meta_llm")}: ${config.llm_provider}`;
    els.metaModel.textContent = config.llm_model || "—";
    els.metaSearch.textContent = `${t("meta_search")}: ${config.search_provider}`;
    const offline = Boolean(config.offline);
    els.metaMode.textContent = offline ? t("meta_mode_offline") : t("meta_mode_online");
    els.metaMode.className = offline ? "meta-item pill pill--offline" : "meta-item pill";
  }

  // ------------------------------------------------------------------ //
  // Examples + depth                                                    //
  // ------------------------------------------------------------------ //
  function renderExamples() {
    els.examples.replaceChildren();
    (EXAMPLES[state.lang] || EXAMPLES.zh).forEach((example) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip";
      chip.textContent = example;
      chip.title = example;
      chip.addEventListener("click", () => {
        els.question.value = example;
        clearFormError();
        els.question.focus();
      });
      els.examples.appendChild(chip);
    });
  }

  function getDepth() {
    const checked = document.querySelector('input[name="depth"]:checked');
    return checked ? checked.value : "quick";
  }

  function setDepth(value) {
    document.querySelectorAll('input[name="depth"]').forEach((radio) => {
      radio.checked = radio.value === value;
    });
  }

  function depthLabel(value) {
    return t(`depth_${value}`);
  }

  // ------------------------------------------------------------------ //
  // Form + submit                                                       //
  // ------------------------------------------------------------------ //
  function showFormError(message) {
    els.formError.textContent = message;
    els.formError.hidden = false;
  }

  function clearFormError() {
    els.formError.hidden = true;
    els.formError.textContent = "";
  }

  function updateSubmitLabel() {
    els.submitLabel.textContent = state.running ? t("running") : t("start");
  }

  function setSubmitEnabled(enabled) {
    els.submit.disabled = !enabled;
    els.submit.setAttribute("aria-busy", enabled ? "false" : "true");
    updateSubmitLabel();
  }

  function handleSubmit() {
    if (state.running) return;
    const question = els.question.value.trim();
    if (!question) {
      showFormError(t("error_required"));
      els.question.focus();
      return;
    }
    clearFormError();
    startResearch(question, getDepth());
  }

  async function startResearch(question, depth) {
    state.running = true;
    state.lastPercent = 0;
    state.result = null;
    state.lastRequest = { question, depth };
    setSubmitEnabled(false);
    resetResearchView(question, depth);
    els.compose.hidden = true;
    els.research.hidden = false;
    els.result.hidden = true;
    els.research.setAttribute("aria-busy", "true");
    scrollToElement(els.research);
    try {
      await streamResearch(question, depth);
    } catch (error) {
      showRunError(friendlyError(error));
    } finally {
      state.running = false;
      setSubmitEnabled(true);
      els.research.setAttribute("aria-busy", "false");
    }
  }

  function resetResearchView(question, depth) {
    els.research.classList.remove("is-done");
    els.researchQuestion.textContent = question;
    els.researchDepth.textContent = depthLabel(depth);
    els.log.replaceChildren();
    els.runError.hidden = true;
    els.runErrorText.textContent = "";
    els.progressBar.classList.remove("progress-bar--error");
    setProgress(0, t("progress_waiting"));
    els.reportTitle.textContent = "";
    els.summaryText.textContent = "";
    els.summaryText.hidden = false;
    els.takeaways.replaceChildren();
    els.stats.replaceChildren();
    els.report.replaceChildren();
  }

  function scrollToElement(element) {
    const top = element.getBoundingClientRect().top + window.scrollY - 76;
    window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }

  // ------------------------------------------------------------------ //
  // SSE streaming                                                       //
  // ------------------------------------------------------------------ //
  async function streamResearch(question, depth) {
    const response = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question: question, depth: depth, language: state.lang }),
    });
    if (!response.ok) {
      let message = t("error_http");
      try {
        const data = await response.json();
        if (data && data.error) message = data.error;
      } catch (error) {
        /* keep the generic message */
      }
      throw new Error(message);
    }
    if (!response.body) throw new Error(t("error_stream"));

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      for (;;) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        buffer = processSseBuffer(buffer);
      }
      buffer += decoder.decode();
      if (buffer.trim()) processSseBuffer(`${buffer}\n\n`);
    } finally {
      try {
        reader.releaseLock();
      } catch (error) {
        /* already released */
      }
    }
    if (!state.result) throw new Error(t("error_no_result"));
  }

  function processSseBuffer(buffer) {
    let index = buffer.indexOf("\n\n");
    while (index !== -1) {
      const block = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      if (block.trim()) dispatchSseBlock(block);
      index = buffer.indexOf("\n\n");
    }
    return buffer;
  }

  function dispatchSseBlock(block) {
    let eventName = "message";
    const dataLines = [];
    block.split("\n").forEach((raw) => {
      const line = raw.replace(/\r$/, "");
      if (!line || line.startsWith(":")) return;
      const colon = line.indexOf(":");
      const field = colon === -1 ? line : line.slice(0, colon);
      let value = colon === -1 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") eventName = value;
      else if (field === "data") dataLines.push(value);
    });
    if (!dataLines.length) return;
    let payload;
    try {
      payload = JSON.parse(dataLines.join("\n"));
    } catch (error) {
      return;
    }
    if (eventName === "result") handleResult(payload);
    else if (eventName === "error") handleRunError(payload);
    else if (payload && typeof payload === "object") handleProgress(payload);
  }

  function normalizePercent(event) {
    const raw = event.percent;
    if (typeof raw === "number" && Number.isFinite(raw)) {
      return Math.max(0, Math.min(100, raw));
    }
    if (typeof raw === "string" && raw.trim() !== "") {
      const parsed = Number(raw);
      if (Number.isFinite(parsed)) return Math.max(0, Math.min(100, parsed));
    }
    return Math.min(96, state.lastPercent + 1.5);
  }

  function handleProgress(event) {
    const type = typeof event.type === "string" ? event.type : "message";
    const percent = normalizePercent(event);
    state.lastPercent = Math.max(state.lastPercent, percent);
    setProgress(state.lastPercent, stageLabel(type, event.message));
    appendLog(event, type);
  }

  function stageLabel(type, fallback) {
    const key = `stage_${type}`;
    const label = t(key);
    if (label !== key) return label;
    return fallback || "";
  }

  function setProgress(percent, stage) {
    const value = Math.max(0, Math.min(100, Number(percent) || 0));
    els.progressBar.style.width = `${value}%`;
    els.progressPercent.textContent = `${Math.round(value)}%`;
    els.progressTrack.setAttribute("aria-valuenow", String(Math.round(value)));
    if (typeof stage === "string") els.progressStage.textContent = stage;
  }

  function appendLog(event, type) {
    if (els.log.children.length >= MAX_LOG_ITEMS) {
      els.log.removeChild(els.log.firstChild);
    }
    const item = document.createElement("li");
    item.className = `log-item log-item--${type}`;

    const icon = document.createElement("span");
    icon.className = "log-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = EVENT_ICONS[type] || "·";

    const time = document.createElement("span");
    time.className = "log-time";
    time.textContent = formatTime(event.at);

    const message = document.createElement("span");
    message.className = "log-msg";
    message.textContent = event.message || stageLabel(type, "");

    item.append(icon, time, message);
    els.log.appendChild(item);
    els.log.scrollTop = els.log.scrollHeight;
  }

  function handleResult(payload) {
    state.result = payload;
    state.lastPercent = 100;
    els.research.classList.add("is-done");
    els.progressBar.classList.remove("progress-bar--error");
    setProgress(100, t("stage_done"));
    renderResult(payload);
  }

  function handleRunError(payload) {
    const message =
      payload && typeof payload.message === "string" ? payload.message : t("error_http");
    showRunError(message);
  }

  function showRunError(message) {
    els.runError.hidden = false;
    els.runErrorText.textContent = message;
    els.result.hidden = true;
    els.research.classList.remove("is-done");
    els.progressBar.classList.add("progress-bar--error");
    setProgress(state.lastPercent, t("run_error_title"));
    appendLog({ type: "error", message: message, at: new Date().toISOString() }, "error");
  }

  // ------------------------------------------------------------------ //
  // Result rendering                                                    //
  // ------------------------------------------------------------------ //
  function renderResult(payload) {
    const markdown = typeof payload.markdown === "string" ? payload.markdown : "";
    const title = payload.title || t("report_untitled");
    els.reportTitle.textContent = title;

    const summary = payload.summary || extractSummary(markdown);
    els.summaryText.textContent = summary || "";
    els.summaryText.hidden = !summary;

    renderTakeaways(payload.key_takeaways);
    renderStats(payload);

    els.report.innerHTML = markdown
      ? markdownToHtml(markdown)
      : `<p>${escapeHtml(t("report_empty"))}</p>`;
    els.result.hidden = false;
    scrollToElement(els.result);
  }

  function renderTakeaways(items) {
    els.takeaways.replaceChildren();
    (Array.isArray(items) ? items : []).forEach((item) => {
      if (!item) return;
      const li = document.createElement("li");
      li.textContent = String(item);
      els.takeaways.appendChild(li);
    });
  }

  function renderStats(payload) {
    const usage = payload.usage || {};
    const prompt = Number(usage.prompt_tokens) || 0;
    const completion = Number(usage.completion_tokens) || 0;
    const entries = [
      ["stat_refs", formatNumber(Number(payload.source_count) || 0)],
      ["stat_llm", formatNumber(Number(usage.llm_calls) || 0)],
      ["stat_search", formatNumber(Number(usage.search_calls) || 0)],
      ["stat_fetch", formatNumber(Number(usage.fetches) || 0)],
      ["stat_tokens", formatNumber(prompt + completion)],
      ["stat_elapsed", formatDuration(Number(usage.elapsed_seconds))],
    ];
    const cost = Number(usage.est_cost_usd) || 0;
    if (cost > 0) entries.push(["stat_cost", `$${cost.toFixed(4)}`]);

    els.stats.replaceChildren();
    entries.forEach(([key, value]) => {
      const li = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = t(key);
      const strong = document.createElement("span");
      strong.className = "stat-value";
      strong.textContent = value;
      li.append(label, strong);
      els.stats.appendChild(li);
    });
  }

  function extractSummary(markdown) {
    const lines = String(markdown || "").split(/\r?\n/);
    const collected = [];
    let collecting = false;
    for (const raw of lines) {
      const line = raw.trim();
      const heading = line.match(/^##\s+(.+)$/);
      if (heading) {
        if (collecting) break;
        if (/^(摘要|概要|总结|Summary|Abstract|Executive summary)$/i.test(heading[1].trim())) {
          collecting = true;
        }
        continue;
      }
      if (!collecting) continue;
      if (!line) {
        if (collected.length) break;
        continue;
      }
      collected.push(line);
    }
    return collected
      .join(" ")
      .replace(/\*\*/g, "")
      .replace(/`/g, "")
      .trim();
  }

  // ------------------------------------------------------------------ //
  // Minimal, safe Markdown -> HTML                                      //
  // ------------------------------------------------------------------ //
  function renderInline(text) {
    let escaped = escapeHtml(text);
    const codes = [];
    escaped = escaped.replace(/`([^`]+)`/g, (match, code) => {
      codes.push(code);
      return `\u0000CODE${codes.length - 1}\u0000`;
    });
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    escaped = escaped.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    escaped = escaped.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    escaped = escaped.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+|#[^\s)]*)\)/g,
      (match, label, url) =>
        `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`
    );
    escaped = escaped.replace(
      /(^|[\s(])(https?:\/\/[^\s<)]+)/g,
      (match, prefix, url) =>
        `${prefix}<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
    );
    escaped = escaped.replace(/\[(S\d+)\]/g, '<span class="cite">[$1]</span>');
    escaped = escaped.replace(/\u0000CODE(\d+)\u0000/g, (match, index) => {
      const code = codes[Number(index)];
      return `<code>${code === undefined ? "" : code}</code>`;
    });
    return escaped;
  }

  function markdownToHtml(markdown) {
    const lines = String(markdown || "")
      .replace(/\r\n?/g, "\n")
      .split("\n");
    const html = [];
    let paragraph = [];
    let listType = null;
    let listItems = [];
    let quoteLines = [];
    let codeBlock = null;

    const flushParagraph = () => {
      if (!paragraph.length) return;
      html.push(`<p>${renderInline(paragraph.join(" ").trim())}</p>`);
      paragraph = [];
    };
    const flushList = () => {
      if (listType && listItems.length) {
        const items = listItems.map((item) => `<li>${item}</li>`).join("");
        html.push(`<${listType}>${items}</${listType}>`);
      }
      listType = null;
      listItems = [];
    };
    const flushQuote = () => {
      if (!quoteLines.length) return;
      html.push(`<blockquote>${markdownToHtml(quoteLines.join("\n"))}</blockquote>`);
      quoteLines = [];
    };
    const flushAll = () => {
      flushParagraph();
      flushList();
      flushQuote();
    };

    lines.forEach((rawLine) => {
      const line = rawLine.trim();

      if (codeBlock !== null) {
        if (/^```/.test(line)) {
          const language = codeBlock.language
            ? ` class="language-${escapeHtml(codeBlock.language)}"`
            : "";
          html.push(
            `<pre><code${language}>${escapeHtml(codeBlock.lines.join("\n"))}</code></pre>`
          );
          codeBlock = null;
        } else {
          codeBlock.lines.push(rawLine);
        }
        return;
      }

      const fence = line.match(/^```(\w*)/);
      if (fence) {
        flushAll();
        codeBlock = { language: fence[1], lines: [] };
        return;
      }

      if (!line) {
        flushAll();
        return;
      }

      const heading = line.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        flushAll();
        const level = heading[1].length;
        html.push(`<h${level}>${renderInline(heading[2].trim())}</h${level}>`);
        return;
      }

      if (/^(-{3,}|\*{3,}|_{3,})$/.test(line)) {
        flushAll();
        html.push("<hr>");
        return;
      }

      const quote = line.match(/^>\s?(.*)$/);
      if (quote) {
        flushParagraph();
        flushList();
        quoteLines.push(quote[1]);
        return;
      }

      const ordered = line.match(/^\d+[.)]\s+(.*)$/);
      const unordered = line.match(/^[-*+]\s+(.*)$/);
      if (ordered || unordered) {
        flushParagraph();
        flushQuote();
        const type = ordered ? "ol" : "ul";
        if (listType && listType !== type) flushList();
        listType = type;
        listItems.push(renderInline((ordered ? ordered[1] : unordered[1]).trim()));
        return;
      }

      flushList();
      flushQuote();
      paragraph.push(line);
    });

    if (codeBlock !== null) {
      html.push(`<pre><code>${escapeHtml(codeBlock.lines.join("\n"))}</code></pre>`);
    }
    flushAll();
    return html.join("\n");
  }

  // ------------------------------------------------------------------ //
  // Downloads / copy / toast                                            //
  // ------------------------------------------------------------------ //
  function safeFilename(title, fallback) {
    const cleaned = String(title || "")
      .replace(/[\\/:*?"<>|\u0000-\u001f]+/g, "-")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 64);
    return cleaned || fallback;
  }

  function downloadText(filename, text, mime) {
    const blob = new Blob([text], { type: mime || "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  async function downloadMarkdown() {
    const result = state.result;
    if (!result) return;
    const markdown = typeof result.markdown === "string" ? result.markdown : "";
    downloadText(
      `${safeFilename(result.title, "report")}.md`,
      markdown,
      "text/markdown;charset=utf-8"
    );
  }

  async function downloadResultJson() {
    const result = state.result;
    if (!result) return;
    try {
      const url = result.json_url || `/api/runs/${encodeURIComponent(result.run_id || "")}/result.json`;
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const text = await response.text();
      downloadText(
        `${safeFilename(result.title, "result")}.json`,
        text,
        "application/json;charset=utf-8"
      );
    } catch (error) {
      const fallback = JSON.stringify(
        {
          run_id: result.run_id,
          question: result.question,
          title: result.title,
          created_at: result.created_at,
          summary: result.summary,
          key_takeaways: result.key_takeaways,
          limitations: result.limitations,
          markdown: result.markdown,
          usage: result.usage,
          source_count: result.source_count,
        },
        null,
        2
      );
      downloadText(
        `${safeFilename(result.title, "result")}.json`,
        fallback,
        "application/json;charset=utf-8"
      );
    }
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    document.body.appendChild(area);
    area.select();
    let copied = false;
    try {
      copied = document.execCommand ? document.execCommand("copy") : false;
    } finally {
      area.remove();
    }
    if (!copied) throw new Error("copy failed");
  }

  async function copyMarkdown() {
    const result = state.result;
    if (!result) return;
    try {
      await copyText(typeof result.markdown === "string" ? result.markdown : "");
      showToast(t("toast_copied"));
    } catch (error) {
      showToast(t("toast_copy_failed"));
    }
  }

  let toastTimer = null;
  function showToast(message) {
    els.toast.textContent = message;
    els.toast.hidden = false;
    requestAnimationFrame(() => els.toast.classList.add("is-visible"));
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      els.toast.classList.remove("is-visible");
      setTimeout(() => {
        els.toast.hidden = true;
      }, 220);
    }, 2200);
  }

  // ------------------------------------------------------------------ //
  // Reset                                                               //
  // ------------------------------------------------------------------ //
  function resetToCompose() {
    state.result = null;
    state.lastPercent = 0;
    els.compose.hidden = false;
    els.research.hidden = true;
    els.result.hidden = true;
    els.log.replaceChildren();
    els.runError.hidden = true;
    els.progressBar.classList.remove("progress-bar--error");
    setProgress(0, t("progress_waiting"));
    els.report.replaceChildren();
    els.question.value = "";
    els.research.classList.remove("is-done");
    clearFormError();
    window.scrollTo({ top: 0, behavior: "smooth" });
    els.question.focus();
  }

  // ------------------------------------------------------------------ //
  // Events                                                              //
  // ------------------------------------------------------------------ //
  function bindEvents() {
    els.submit.addEventListener("click", handleSubmit);
    els.langToggle.addEventListener("click", toggleLang);
    els.newResearch.addEventListener("click", resetToCompose);
    els.retry.addEventListener("click", () => {
      if (state.lastRequest) {
        startResearch(state.lastRequest.question, state.lastRequest.depth);
      }
    });
    els.question.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        handleSubmit();
      }
    });
    els.question.addEventListener("input", clearFormError);
    document.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.getAttribute("data-action");
        if (action === "download-md") downloadMarkdown();
        else if (action === "download-json") downloadResultJson();
        else if (action === "copy") copyMarkdown();
      });
    });
  }

  // ------------------------------------------------------------------ //
  // Boot                                                                //
  // ------------------------------------------------------------------ //
  function init() {
    applyLang();
    bindEvents();
    setProgress(0, t("progress_waiting"));
    loadBackend();
  }

  init();
})();
