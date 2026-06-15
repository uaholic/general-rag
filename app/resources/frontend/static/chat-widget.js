(function () {
  const script = document.currentScript;
  const apiBase = script?.dataset.apiBase || window.location.origin;
  const themeColor = script?.dataset.themeColor || "#2563eb";
  const businessLineId = script?.dataset.businessLineId || "business_line_course";
  const scriptUrl = script?.src ? new URL(script.src, window.location.href) : null;
  const staticBase = scriptUrl ? new URL("./", scriptUrl).href : `${(apiBase || window.location.origin).replace(/\/$/, "")}/static/`;
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
      max-height: 260px;
      object-fit: contain;
      border-radius: 8px;
      border: 1px solid #e8edf4;
      margin: 8px 0;
    }
    .rag-widget-message.assistant h1,
    .rag-widget-message.assistant h2,
    .rag-widget-message.assistant h3 {
      margin: 10px 0 6px;
      font-size: 15px;
    }
    .rag-widget-message.assistant h1 { font-size: 18px; }
    .rag-widget-message.assistant h2 { font-size: 16px; }
    .rag-widget-message.assistant p {
      margin: 8px 0;
    }
    .rag-widget-message.assistant code {
      padding: 2px 4px;
      border-radius: 5px;
      background: #eef2f7;
    }
    .rag-widget-message.assistant pre {
      overflow: auto;
      padding: 10px;
      border-radius: 7px;
      background: #101828;
      color: #e6edf7;
      white-space: pre-wrap;
    }
    .rag-widget-message.assistant ul,
    .rag-widget-message.assistant ol {
      margin: 8px 0 10px 20px;
      padding: 0;
    }
    .rag-widget-message.assistant li {
      margin: 4px 0;
    }
    .rag-widget-message.assistant table {
      width: 100%;
      margin: 10px 0;
      border-collapse: collapse;
      font-size: 12px;
    }
    .rag-widget-message.assistant th,
    .rag-widget-message.assistant td {
      padding: 7px 8px;
      border: 1px solid #e8edf4;
      text-align: left;
      vertical-align: top;
    }
    .rag-widget-message.assistant th {
      background: #f4f7fb;
      color: #172033;
      font-weight: 800;
    }
    .rag-widget-message.assistant blockquote {
      margin: 10px 0;
      padding: 8px 10px;
      border-left: 3px solid ${themeColor};
      background: #f8fbff;
      color: #667085;
    }
    .rag-widget-message.assistant hr {
      height: 1px;
      margin: 14px 0;
      border: 0;
      background: #e8edf4;
    }
    .rag-widget-progress {
      margin-top: 8px;
      padding: 8px;
      border: 1px solid #dbe6f5;
      border-radius: 7px;
      background: #f8fbff;
      color: #475467;
      font-size: 12px;
    }
    .rag-widget-progress-line {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 6px;
    }
    .rag-widget-progress-track {
      height: 5px;
      overflow: hidden;
      border-radius: 999px;
      background: #e8edf4;
    }
    .rag-widget-progress-fill {
      display: block;
      height: 100%;
      width: 0;
      background: ${themeColor};
      transition: width .2s ease;
    }
    .rag-widget-images {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }
    .rag-widget-image-caption {
      color: #667085;
      font-size: 12px;
    }
    .rag-widget-error {
      margin-top: 8px;
      color: #b42318;
      font-size: 12px;
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
    .rag-widget-ref summary {
      cursor: pointer;
      font-weight: 700;
      color: #263247;
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
  root.dataset.apiBase = apiBase;
  root.innerHTML = `
    <button class="rag-widget-button" type="button" aria-label="打开聊天框">问</button>
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
    return String(text || "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    })[char]);
  }

  let rendererPromise = null;

  function ensureRenderer() {
    if (window.RagMarkdown?.render) return Promise.resolve(window.RagMarkdown);
    if (!rendererPromise) {
      rendererPromise = new Promise((resolve, reject) => {
        const existing = document.querySelector('script[data-rag-widget-renderer="true"]');
        if (existing) {
          existing.addEventListener("load", () => resolve(window.RagMarkdown));
          existing.addEventListener("error", reject);
          return;
        }
        const tag = document.createElement("script");
        tag.src = `${staticBase}markdown-renderer.js?v=20260615-5`;
        tag.defer = true;
        tag.dataset.ragWidgetRenderer = "true";
        tag.onload = () => window.RagMarkdown?.render ? resolve(window.RagMarkdown) : reject(new Error("Markdown 渲染器未初始化"));
        tag.onerror = () => reject(new Error("Markdown 渲染器加载失败"));
        document.head.appendChild(tag);
      });
    }
    return rendererPromise;
  }

  function setMarkdownContent(target, text) {
    if (!target) return;
    const token = (target._ragWidgetRenderToken || 0) + 1;
    target._ragWidgetRenderToken = token;
    ensureRenderer()
      .then((renderer) => {
        if (target._ragWidgetRenderToken !== token) return;
        renderer.render(target, text);
      })
      .catch(() => {
        if (target._ragWidgetRenderToken !== token) return;
        target.innerHTML = escapeHtml(text || "").replace(/\n/g, "<br>");
      });
  }

  function apiUrl(path) {
    return `${(apiBase || window.location.origin).replace(/\/$/, "")}${path}`;
  }

  function updateProgress(target, data) {
    target.style.display = "block";
    const percent = Number(data.percent || 0);
    target.innerHTML = `
      <div class="rag-widget-progress-line">
        <span>${escapeHtml(data.label || data.step || "处理中")}</span>
        <span>${Math.max(0, Math.min(100, percent))}%</span>
      </div>
      <div class="rag-widget-progress-track"><span class="rag-widget-progress-fill" style="width:${Math.max(0, Math.min(100, percent))}%"></span></div>
      ${data.message ? `<div style="margin-top:6px">${escapeHtml(data.message)}</div>` : ""}
    `;
  }

  function renderImages(target, data) {
    const images = Array.isArray(data.images) ? data.images : [];
    if (!images.length && !data.message) return;
    const box = document.createElement("div");
    box.className = "rag-widget-images";
    if (data.message) {
      const caption = document.createElement("div");
      caption.className = "rag-widget-image-caption";
      caption.textContent = data.message;
      box.appendChild(caption);
    }
    images.forEach((image) => {
      if (!image.url) return;
      const img = document.createElement("img");
      img.src = image.url;
      img.alt = image.caption || "知识库图片";
      box.appendChild(img);
      if (image.caption) {
        const caption = document.createElement("div");
        caption.className = "rag-widget-image-caption";
        caption.textContent = image.caption;
        box.appendChild(caption);
      }
    });
    target.appendChild(box);
  }

  function renderReferences(target, references) {
    const refs = Array.isArray(references) ? references : [];
    if (!refs.length) return;
    target.innerHTML = refs.map((ref, index) => {
      if (typeof ref === "string") return `<details class="rag-widget-ref"><summary>引用 ${index + 1}</summary>${escapeHtml(ref)}</details>`;
      const title = ref.title || ref.file_name || ref.doc_name || `引用 ${index + 1}`;
      const score = ref.score == null ? "" : ` / score: ${ref.score}`;
      const text = ref.text || ref.content || ref.chunk || "";
      return `<details class="rag-widget-ref"><summary>${escapeHtml(title)}${escapeHtml(score)}</summary>${text ? `<div>${escapeHtml(text)}</div>` : ""}</details>`;
    }).join("");
  }

  async function readSse(response, onEvent) {
    if (!response.body) throw new Error("浏览器不支持流式响应");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";
      chunks.forEach((chunk) => {
        const lines = chunk.split("\n");
        let event = "message";
        let data = "";
        lines.forEach((line) => {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) data += line.slice(5).trim();
        });
        if (!data) return;
        try {
          onEvent(event, JSON.parse(data));
        } catch {
          onEvent(event, { text: data });
        }
      });
    }
  }

  loadHistory().forEach(renderMessage);
  ensureRenderer().catch(() => {});

  button.addEventListener("click", () => root.classList.add("open"));
  close.addEventListener("click", () => root.classList.remove("open"));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    const history = loadHistory();
    const userMessage = { role: "user", content: question };
    history.push(userMessage);
    renderMessage(userMessage);
    input.value = "";

    const assistant = renderMessage({ role: "assistant", content: "" });
    assistant.innerHTML = `
      <div data-answer-text></div>
      <div class="rag-widget-progress" data-progress></div>
      <div class="rag-widget-refs" data-references></div>
    `;
    const answerText = assistant.querySelector("[data-answer-text]");
    const progress = assistant.querySelector("[data-progress]");
    const refs = assistant.querySelector("[data-references]");
    let answer = "";

    try {
      const response = await fetch(apiUrl("/api/chat/stream"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: ensureSession(),
          message: question,
          company_id: script?.dataset.companyId || "default_company",
          business_line_id: businessLineId
        })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      await readSse(response, (eventName, data) => {
        if (eventName === "progress") {
          updateProgress(progress, data);
        } else if (eventName === "delta") {
          answer += data.text || data.content || "";
          setMarkdownContent(answerText, answer);
        } else if (eventName === "image") {
          renderImages(assistant, data);
        } else if (eventName === "references") {
          renderReferences(refs, data.references);
        } else if (eventName === "final") {
          if (!answer && data.answer) {
            answer = data.answer;
            setMarkdownContent(answerText, answer);
          }
          progress.style.display = "none";
        } else if (eventName === "error") {
          throw new Error(data.message || "回答生成失败");
        }
        messages.scrollTop = messages.scrollHeight;
      });
    } catch (error) {
      progress.style.display = "none";
      answer = preset.answer;
      setMarkdownContent(answerText, answer);
      const fallback = document.createElement("div");
      fallback.className = "rag-widget-error";
      fallback.textContent = "当前后端接口未连接，已展示本地演示回答。";
      assistant.appendChild(fallback);
      renderImages(assistant, {
        message: "图片事件会在后端返回 image SSE 时展示在这里。",
        images: []
      });
      renderReferences(refs, preset.refs);
    }

    const assistantMessage = { role: "assistant", html: assistant.innerHTML };
    history.push(assistantMessage);
    saveHistory(history);
  });
})();
