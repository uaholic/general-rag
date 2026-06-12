(function () {
  const script = document.currentScript;
  const themeColor = script?.dataset.themeColor || "#2563eb";
  const businessLineId = script?.dataset.businessLineId || "business_line_course";
  const presets = {
    business_line_course: {
      name: "大模型学习助手",
      welcome: "你好，我是课程知识库助手，可以帮你解答大模型学习问题。",
      answer: "RAG 的基本流程包括文档解析、chunk 切分、embedding、向量检索、Prompt 构造和大模型生成回答。下面这张图可以帮助理解整体链路。",
      refs: ["[1] rag.md / RAG 基础流程 / score: 0.82", "[2] milvus.md / 向量检索 / score: 0.76"]
    },
    business_line_sales: {
      name: "售前咨询助手",
      welcome: "你好，我是售前咨询助手，可以介绍产品能力、案例和套餐政策。",
      answer: "这个业务线会优先检索产品资料库和价格政策库，用于回答官网访客的产品能力、适用场景、交付流程和套餐问题。",
      refs: ["[1] product.md / 产品能力 / score: 0.84", "[2] pricing.md / 套餐政策 / score: 0.79"]
    },
    business_line_support: {
      name: "售后服务助手",
      welcome: "你好，我是售后服务助手，可以帮你查询使用说明和故障排查资料。",
      answer: "这个业务线会检索售后知识库，优先给出操作步骤、排查路径和注意事项。",
      refs: ["[1] support.md / 故障排查 / score: 0.81"]
    }
  };
  const preset = presets[businessLineId] || presets.business_line_course;
  const sessionKey = `rag_widget_session_id_${businessLineId}`;
  const historyKey = `rag_widget_history_${businessLineId}`;

  function ensureSession() {
    let sessionId = localStorage.getItem(sessionKey);
    if (!sessionId) {
      sessionId = `session_${Date.now().toString(36)}`;
      localStorage.setItem(sessionKey, sessionId);
    }
    return sessionId;
  }

  function loadHistory() {
    try {
      return JSON.parse(localStorage.getItem(historyKey) || "[]");
    } catch {
      return [];
    }
  }

  function saveHistory(history) {
    localStorage.setItem(historyKey, JSON.stringify(history.slice(-20)));
  }

  const style = document.createElement("style");
  style.textContent = `
    .rag-widget-root {
      position: fixed;
      right: 22px;
      bottom: 22px;
      z-index: 9999;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: #172033;
      letter-spacing: 0;
    }
    .rag-widget-button {
      width: 58px;
      height: 58px;
      border: 0;
      border-radius: 50%;
      background: ${themeColor};
      color: #fff;
      box-shadow: 0 18px 40px rgba(25, 34, 56, 0.25);
      font-size: 24px;
      cursor: pointer;
    }
    .rag-widget-panel {
      display: none;
      width: min(380px, calc(100vw - 28px));
      height: min(620px, calc(100vh - 36px));
      overflow: hidden;
      border: 1px solid #d8dee8;
      border-radius: 8px;
      background: #fff;
      box-shadow: 0 24px 60px rgba(25, 34, 56, 0.22);
    }
    .rag-widget-root.open .rag-widget-panel { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; }
    .rag-widget-root.open .rag-widget-button { display: none; }
    .rag-widget-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 16px;
      background: ${themeColor};
      color: #fff;
    }
    .rag-widget-title { font-weight: 800; }
    .rag-widget-close {
      width: 30px;
      height: 30px;
      border: 0;
      border-radius: 7px;
      background: rgba(255,255,255,0.14);
      color: #fff;
      font-size: 18px;
      cursor: pointer;
    }
    .rag-widget-messages {
      min-height: 0;
      overflow-y: auto;
      padding: 14px;
      background: #f6f8fc;
    }
    .rag-widget-message {
      max-width: 92%;
      margin-bottom: 12px;
      padding: 10px 12px;
      border: 1px solid #e8edf4;
      border-radius: 8px;
      background: #fff;
      font-size: 14px;
      line-height: 1.55;
      word-break: break-word;
    }
    .rag-widget-message.user {
      margin-left: auto;
      background: ${themeColor};
      border-color: ${themeColor};
      color: #fff;
    }
    .rag-widget-message.assistant img {
      max-width: 100%;
      border-radius: 8px;
      border: 1px solid #e8edf4;
      margin: 8px 0;
    }
    .rag-widget-welcome {
      color: #667085;
      font-size: 13px;
      margin: 0 0 12px;
    }
    .rag-widget-refs {
      margin-top: 10px;
      display: grid;
      gap: 7px;
    }
    .rag-widget-ref {
      padding: 8px;
      border-radius: 7px;
      background: #f9fafc;
      border: 1px solid #e8edf4;
      color: #475467;
      font-size: 12px;
    }
    .rag-widget-form {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      padding: 12px;
      border-top: 1px solid #e8edf4;
      background: #fff;
    }
    .rag-widget-input {
      min-height: 40px;
      border: 1px solid #d8dee8;
      border-radius: 7px;
      padding: 8px 10px;
      outline: none;
    }
    .rag-widget-input:focus {
      border-color: ${themeColor};
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }
    .rag-widget-send {
      min-width: 58px;
      border: 0;
      border-radius: 7px;
      background: ${themeColor};
      color: #fff;
      font-weight: 700;
      cursor: pointer;
    }
  `;
  document.head.appendChild(style);

  const root = document.createElement("div");
  root.className = "rag-widget-root";
  root.innerHTML = `
    <button class="rag-widget-button" type="button" aria-label="打开聊天框">?</button>
    <section class="rag-widget-panel" aria-label="知识库聊天框">
      <header class="rag-widget-header">
        <div>
          <div class="rag-widget-title">${preset.name}</div>
          <div style="font-size:12px;opacity:.86">${businessLineId} · ${ensureSession()}</div>
        </div>
        <button class="rag-widget-close" type="button" aria-label="关闭聊天框">×</button>
      </header>
      <div class="rag-widget-messages">
        <p class="rag-widget-welcome">${preset.welcome}</p>
      </div>
      <form class="rag-widget-form">
        <input class="rag-widget-input" placeholder="请输入问题，例如：RAG 的流程是什么？">
        <button class="rag-widget-send" type="submit">发送</button>
      </form>
    </section>
  `;
  document.body.appendChild(root);

  const button = root.querySelector(".rag-widget-button");
  const close = root.querySelector(".rag-widget-close");
  const messages = root.querySelector(".rag-widget-messages");
  const form = root.querySelector(".rag-widget-form");
  const input = root.querySelector(".rag-widget-input");

  function renderMessage(item) {
    const message = document.createElement("div");
    message.className = `rag-widget-message ${item.role}`;
    message.innerHTML = item.html || escapeHtml(item.content || "");
    messages.appendChild(message);
    messages.scrollTop = messages.scrollHeight;
    return message;
  }

  function escapeHtml(text) {
    return text.replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    })[char]);
  }

  loadHistory().forEach(renderMessage);

  button.addEventListener("click", () => root.classList.add("open"));
  close.addEventListener("click", () => root.classList.remove("open"));

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    const history = loadHistory();
    const userMessage = { role: "user", content: question };
    history.push(userMessage);
    renderMessage(userMessage);
    input.value = "";

    const assistant = renderMessage({ role: "assistant", content: "" });
    const answer = preset.answer;
    let index = 0;
    const timer = window.setInterval(() => {
      assistant.textContent += answer[index] || "";
      messages.scrollTop = messages.scrollHeight;
      index += 1;
      if (index >= answer.length) {
        window.clearInterval(timer);
        assistant.innerHTML = `${escapeHtml(answer)}
          <div style="height:72px;margin-top:8px;border:1px solid #e8edf4;border-radius:8px;background:linear-gradient(135deg,rgba(37,99,235,.14),rgba(22,163,74,.18)),repeating-linear-gradient(45deg,#fff,#fff 8px,#edf2f7 8px,#edf2f7 16px);"></div>
          <div class="rag-widget-refs">
            ${preset.refs.map((ref) => `<div class="rag-widget-ref">${escapeHtml(ref)}</div>`).join("")}
          </div>`;
        const assistantMessage = { role: "assistant", html: assistant.innerHTML };
        history.push(assistantMessage);
        saveHistory(history);
      }
    }, 18);
  });
})();
