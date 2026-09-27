const form = document.querySelector("#audit-form");
const resultPanel = document.querySelector("#result-panel");
const summary = document.querySelector("#result-summary");
const agentResults = document.querySelector("#agent-results");
const taskTrace = document.querySelector("#task-trace");
const submitButton = document.querySelector("#submit-button");

const decisionLabels = {
  supported: "证据支持",
  "needs-review": "需要复核",
  conflicting: "存在冲突",
  "no-evidence": "缺少证据",
  incomplete: "核验不完整",
};

const agentLabels = {
  "source-verifier": "来源核验智能体",
  "evidence-grader": "证据分级智能体",
  "contradiction-scout": "冲突检查智能体",
};

document.querySelector("#example-button").addEventListener("click", () => {
  document.querySelector("#claim-text").value = "该处理导致细胞死亡";
  document.querySelector("#source-id").value = "demo:association-study";
  document.querySelector("#source-title").value = "关联性研究演示材料";
  document.querySelector("#source-locator").value = "结果，第2段";
  document.querySelector("#source-excerpt").value =
    "结果提示该处理与细胞死亡相关，可能涉及氧化应激。";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setLoading(true);
  resultPanel.hidden = false;
  summary.replaceChildren(messageBox("三个智能体正在协同核验…"));
  agentResults.replaceChildren();
  taskTrace.replaceChildren();

  const payload = {
    schema_version: "1.0",
    claim_id: `claim-${crypto.randomUUID()}`,
    claim_text: document.querySelector("#claim-text").value.trim(),
    source: {
      source_id: document.querySelector("#source-id").value.trim(),
      title: document.querySelector("#source-title").value.trim(),
      locator: document.querySelector("#source-locator").value.trim(),
    },
    source_excerpt: document.querySelector("#source-excerpt").value.trim(),
  };

  try {
    const response = await fetch("/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    renderPassport(data);
  } catch (error) {
    summary.replaceChildren(messageBox(`核验失败：${error.message}`, true));
  } finally {
    setLoading(false);
    resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});

function renderPassport(data) {
  const card = element("div", `decision-card ${data.decision}`);
  card.append(
    element("div", "decision-label", "LEADER DECISION"),
    element("div", "decision-value", decisionLabels[data.decision] || data.decision),
  );
  if (data.risk_flags?.length) {
    const list = element("ul", "risk-list");
    data.risk_flags.forEach((risk) => list.append(element("li", "", risk)));
    card.append(list);
  } else {
    card.append(element("p", "privacy-note", "本轮未产生风险标志。"));
  }
  summary.replaceChildren(card);

  agentResults.replaceChildren();
  Object.entries(data.partner_products || {}).forEach(([name, product]) => {
    const payload = product.payload || {};
    const status = payload.status || payload.level || "已返回";
    const agentCard = element("article", "agent-card");
    const header = element("header", "");
    header.append(element("h3", "", agentLabels[name] || name), element("code", "", status));
    agentCard.append(header);
    if (payload.rationale) agentCard.append(element("p", "", payload.rationale));
    if (payload.issues?.length) agentCard.append(element("p", "", payload.issues.join("；")));
    if (payload.indicators?.length) agentCard.append(element("p", "", payload.indicators.join("；")));
    agentResults.append(agentCard);
  });

  taskTrace.replaceChildren();
  Object.entries(data.task_ids || {}).forEach(([name, taskId]) => {
    const row = element("div", "trace-row");
    row.append(element("span", "", agentLabels[name] || name), element("code", "", taskId));
    taskTrace.append(row);
  });
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function messageBox(text, isError = false) {
  return element("div", isError ? "error-box" : "decision-card", text);
}

function setLoading(loading) {
  submitButton.disabled = loading;
  submitButton.querySelector("span").textContent = loading ? "核验进行中…" : "启动协同核验";
}
