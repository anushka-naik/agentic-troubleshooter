const AGENTS = [
  { id: "triage", label: "Triage", kind: "LLM", text: "Parses the traceback deterministically, then plans the investigation: search queries, whether to analyse code, whether GitHub is worth searching." },
  { id: "supervisor", label: "Supervisor", kind: "Deterministic router", text: "Runs planned specialists, escalates to GitHub when documentation coverage is insufficient, enforces the revision budget and decides when to stop." },
  { id: "doc_researcher", label: "Docs", kind: "Hybrid RAG + LLM grader", text: "FAISS dense search and BM25 fused with reciprocal rank fusion, then an LLM grades each chunk and reports coverage." },
  { id: "code_analyst", label: "Code", kind: "Tools + LLM", text: "AST and pyflakes static analysis plus a sandboxed run to reproduce the reported error before anyone guesses at a fix." },
  { id: "github_researcher", label: "GitHub", kind: "External tool", text: "Searches GitHub issues for library and version problems. Failures are logged, never fatal." },
  { id: "diagnostician", label: "Diagnose", kind: "LLM", text: "Writes the root cause and fixes with citations to evidence IDs. Receives sandbox feedback when a previous fix failed." },
  { id: "validator", label: "Validate", kind: "Sandbox + checks", text: "A fix is verified only if the original fails and the patch passes. Also flags citations to evidence that does not exist." },
  { id: "reporter", label: "Report", kind: "Deterministic", text: "Assembles the report from state, so validation labels and warnings cannot be paraphrased away." },
];
const AGENT_IDS = new Set(AGENTS.map((a) => a.id));
const STATUS_LABELS = {
  verified: "Verified in sandbox",
  failed: "Failed validation",
  not_verifiable: "Not verifiable",
  not_run: "Not executed",
};
const KIND_LABELS = {
  documentation: "documentation",
  github_issue: "github issue",
  code_analysis: "code analysis",
  execution: "execution",
};

const $ = (id) => document.getElementById(id);
let health = null;
let lastReport = null;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

/* ---------- Setup ---------- */

async function loadHealth() {
  try {
    health = await (await fetch("/api/health")).json();
  } catch {
    return;
  }
  const pills = [
    [health.llm_configured ? `model: ${health.model}` : "no API key", health.llm_configured ? "ok" : "warn"],
    [`${health.indexed_chunks} doc chunks`, "ok"],
    [`sandbox ${health.code_execution ? "on" : "off"}`, health.code_execution ? "ok" : "warn"],
    [`GitHub ${health.github_search ? "on" : "off"}`, health.github_search ? "ok" : ""],
    [`LangSmith ${health.langsmith_tracing ? "tracing" : "off"}`, health.langsmith_tracing ? "ok" : ""],
  ];
  $("status").replaceChildren(...pills.map(([text, cls]) => el("span", { class: `pill ${cls}` }, text)));
  $("key-name").textContent = health.api_key_name;
  $("key-banner").classList.toggle("hidden", health.llm_configured);
}

async function loadScenarios() {
  const scenarios = await (await fetch("/api/scenarios")).json();
  const chips = scenarios.map((s) =>
    el("button", {
      class: "chip",
      type: "button",
      onclick: (event) => {
        $("query").value = s.query;
        $("code").value = s.code || "";
        document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
        event.currentTarget.classList.add("active");
      },
    }, s.title),
  );
  $("scenarios").replaceChildren(...chips);
  if (scenarios.length) chips[0].click();
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((tab) =>
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab.dataset.tab}`));
      if (tab.dataset.tab === "architecture") renderArchitecture();
    }),
  );
}

let architectureRendered = false;
async function renderArchitecture() {
  if (architectureRendered) return;
  architectureRendered = true;
  $("agent-grid").replaceChildren(
    ...AGENTS.map((a) =>
      el("div", { class: "agent-card" },
        el("h3", { class: `agent-${a.id}` }, a.id),
        el("div", { class: "kind" }, a.kind),
        el("p", {}, a.text)),
    ),
  );
  const data = await (await fetch("/api/graph")).json();
  const source = data.mermaid.replace(/^\s*classDef .*$/gm, "").replace(/<\/?p>/g, "") +
    "\tclassDef default fill:#1b222c,stroke:#5b7cfa,color:#e6edf3\n" +
    "\tclassDef first fill:#151b23,stroke:#8b96a5\n\tclassDef last fill:#151b23,stroke:#8b96a5\n";
  const target = $("mermaid");
  if (!window.mermaid) {
    target.replaceChildren(el("pre", {}, source));
    return;
  }
  window.mermaid.initialize({
    startOnLoad: false,
    theme: "dark",
    securityLevel: "strict",
    fontFamily: "JetBrains Mono, monospace",
    flowchart: { htmlLabels: false, nodeSpacing: 28, rankSpacing: 60 },
  });
  const { svg } = await window.mermaid.render("graph-svg", source);
  target.innerHTML = svg;

  // Mermaid occasionally offsets the viewBox from the drawn content; refit it.
  const graphSvg = target.querySelector("svg");
  const box = graphSvg.querySelector("g").getBBox();
  const pad = 16;
  graphSvg.setAttribute("viewBox", `${box.x - pad} ${box.y - pad} ${box.width + 2 * pad} ${box.height + 2 * pad}`);
  graphSvg.style.maxWidth = `${box.width + 2 * pad}px`;
}

/* ---------- Pipeline and timeline ---------- */

const pipelineState = {};

function renderPipeline() {
  $("pipeline").replaceChildren(
    ...AGENTS.map((a) => {
      const state = pipelineState[a.id] || {};
      const cls = ["node", state.active ? "active" : "", state.count ? "done" : ""].join(" ");
      return el("li", { class: cls },
        el("span", { class: "dot" }),
        a.label,
        state.count > 1 ? el("span", { class: "count" }, `×${state.count}`) : null);
    }),
  );
}

function resetRun() {
  for (const key of Object.keys(pipelineState)) delete pipelineState[key];
  pipelineState.triage = { active: true };
  renderPipeline();
  $("timeline").replaceChildren();
  $("report").classList.add("hidden");
  $("run-meta").textContent = "";
}

function markActive(nodeId) {
  for (const id of AGENT_IDS) {
    pipelineState[id] = { ...(pipelineState[id] || {}), active: id === nodeId };
  }
}

function onStep(step) {
  const current = pipelineState[step.node] || {};
  pipelineState[step.node] = { ...current, count: (current.count || 0) + 1, active: false };
  if (step.node === "supervisor" && step.details && step.details.next) markActive(step.details.next);
  else if (step.node !== "reporter") markActive("supervisor");
  else markActive(null);
  renderPipeline();

  const hasDetails = step.details && Object.keys(step.details).length > 0;
  const item = el("li", { class: `step ${step.node}` },
    el("details", {},
      el("summary", {},
        el("span", { class: `agent agent-${step.node}` }, step.agent),
        el("span", { class: "text" }, step.summary),
        el("span", { class: "ms" }, `${step.duration_ms} ms`)),
      hasDetails ? el("pre", {}, JSON.stringify(step.details, null, 2)) : null));
  $("timeline").append(item);
}

/* ---------- Report ---------- */

function withCitations(text) {
  const parts = text.split(/\[?\b([DCEG]\d+)\b\]?/g);
  return parts.map((part, i) => (i % 2 === 1 ? citeChip(part) : part));
}

function citeChip(id) {
  return el("button", { class: "cite", type: "button", onclick: () => focusSource(id) }, id);
}

function focusSource(id) {
  const target = document.querySelector(`[data-source="${id}"]`);
  if (!target) return;
  target.open = true;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.classList.add("flash");
  setTimeout(() => target.classList.remove("flash"), 1400);
}

function codeBlock(text, isDiff) {
  const lines = text.replace(/\n$/, "").split("\n").map((line) => {
    let cls = "line";
    if (isDiff) {
      if (line.startsWith("+++") || line.startsWith("---")) cls += " meta";
      else if (line.startsWith("@@")) cls += " hunk";
      else if (line.startsWith("+")) cls += " add";
      else if (line.startsWith("-")) cls += " del";
    }
    return el("span", { class: cls }, line);
  });
  return el("pre", { class: "code-block" }, lines);
}

function copyButton(label, getText) {
  return el("button", {
    class: "ghost",
    type: "button",
    onclick: async (event) => {
      const button = event.currentTarget;
      await navigator.clipboard.writeText(getText());
      button.textContent = "Copied";
      setTimeout(() => (button.textContent = label), 1200);
    },
  }, label);
}

function renderFix(fix, index) {
  const status = fix.validation.status;
  const body = el("div", { class: "fix-body" },
    el("p", {}, fix.explanation),
    el("p", { class: "validation-detail" }, fix.validation.detail),
    fix.citations.length ? el("p", { class: "validation-detail" }, "Sources: ", ...fix.citations.map(citeChip)) : null,
    fix.diff ? codeBlock(fix.diff, true) : null,
    fix.test_code ? el("div", {}, el("p", { class: "validation-detail", style: "margin-top:10px" }, "Regression check"), codeBlock(fix.test_code, false)) : null);

  if (fix.patched_code) {
    const full = codeBlock(fix.patched_code, false);
    full.classList.add("hidden");
    body.append(
      full,
      el("div", { class: "fix-actions" },
        el("button", { class: "ghost", type: "button", onclick: () => full.classList.toggle("hidden") }, "Toggle full patched code"),
        copyButton("Copy patched code", () => fix.patched_code)));
  }

  return el("div", { class: "fix" },
    el("div", { class: "fix-head" },
      el("h3", {}, `${index + 1}. ${fix.title}`),
      el("span", { class: `badge ${status}` }, STATUS_LABELS[status])),
    body);
}

function renderReport(report) {
  lastReport = report;
  const reproduced = report.reproduced === null ? null
    : el("span", { class: `badge ${report.reproduced ? "yes" : "no"}` }, report.reproduced ? "Reproduced" : "Not reproduced");

  const sections = [
    el("div", { class: "report-head" },
      el("h2", {}, "Debugging report"),
      report.error_type ? el("span", { class: "badge" }, report.error_type) : null,
      el("span", { class: "badge" }, report.category.replaceAll("_", " ")),
      el("span", { class: `badge ${report.confidence}` }, `${report.confidence} confidence`),
      reproduced,
      copyButton("Copy Markdown", () => report.markdown)),
    el("p", { class: "problem" }, report.problem_summary),
    el("div", { class: "root-cause" }, el("h3", {}, "Root cause"), el("p", {}, report.root_cause)),
    el("p", { class: "reasoning" }, withCitations(report.reasoning)),
    el("h2", { class: "section-title" }, "Suggested fixes"),
    report.fixes.map(renderFix),
  ];

  if (report.warnings.length) {
    sections.push(el("h2", { class: "section-title" }, "Warnings"),
      el("ul", { class: "warnings" }, report.warnings.map((w) => el("li", {}, w))));
  }
  if (report.open_questions.length) {
    sections.push(el("h2", { class: "section-title" }, "Open questions"),
      el("ul", { class: "questions" }, report.open_questions.map((q) => el("li", {}, q))));
  }

  sections.push(el("h2", { class: "section-title" }, "Evidence"),
    el("div", { class: "sources" }, report.sources.map((s) => {
      const isLink = /^https?:\/\//.test(s.source);
      return el("details", { class: "source", "data-source": s.id },
        el("summary", {},
          el("span", { class: "sid" }, s.id),
          el("span", { class: "kind" }, KIND_LABELS[s.kind] || s.kind),
          el("span", { class: "stitle" }, s.title),
          isLink ? el("a", { href: s.source, target: "_blank", rel: "noopener" }, "open ↗") : el("span", { class: "muted" }, s.source)),
        el("pre", {}, s.snippet));
    })));

  sections.push(el("div", { class: "stats" },
    `${report.steps.length} steps · ${report.llm_calls} LLM calls · ${report.revisions} revision(s) · ${(report.duration_ms / 1000).toFixed(1)}s`));

  const container = $("report");
  container.replaceChildren(...sections.flat());
  container.classList.remove("hidden");
  container.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderError(message) {
  const container = $("report");
  container.replaceChildren(el("div", { class: "error-box" }, message));
  container.classList.remove("hidden");
  markActive(null);
  renderPipeline();
}

/* ---------- Streaming ---------- */

async function investigate() {
  const query = $("query").value.trim();
  if (query.length < 3) {
    $("query").focus();
    return;
  }
  const button = $("run");
  button.disabled = true;
  button.textContent = "Investigating…";
  resetRun();
  const started = performance.now();

  try {
    const response = await fetch("/api/troubleshoot/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, code: $("code").value.trim() || null, enable_github: $("github").checked }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        handleEvent(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
      }
    }
  } catch (error) {
    renderError(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Investigate";
    $("run-meta").textContent = `${((performance.now() - started) / 1000).toFixed(1)}s`;
  }
}

function handleEvent(raw) {
  let event = "message";
  const data = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  const payload = data.length ? JSON.parse(data.join("\n")) : {};
  if (event === "start") $("run-meta").textContent = `run ${payload.run_id.slice(0, 8)}`;
  else if (event === "step") onStep(payload);
  else if (event === "report") renderReport(payload);
  else if (event === "error") renderError(payload.message);
}

/* ---------- Init ---------- */

setupTabs();
renderPipeline();
loadHealth();
loadScenarios();
$("run").addEventListener("click", investigate);
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") investigate();
});
