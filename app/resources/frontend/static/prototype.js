const pages = Array.from(document.querySelectorAll(".page"));
const navLinks = Array.from(document.querySelectorAll("[data-route]"));
const toast = document.querySelector("[data-toast]");

const state = {
  company: null,
  modelConfig: null,
  businessLines: [],
  knowledgeBases: [],
  documents: [],
  chatSessions: [],
  activeDocId: "",
  activeSessionId: ""
};

function $(selector, root = document) {
  return root.querySelector(selector);
}

function $all(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  })[char]);
}

function showToast(message) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 1800);
}

async function apiJson(url, options = {}) {
  const headers = options.body instanceof FormData ? (options.headers || {}) : {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };
  const response = await fetch(url, {
    ...options,
    headers
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false) {
    throw new Error(data.detail || data.message || `请求失败：${response.status}`);
  }
  return data;
}

async function readSse(response, onEvent) {
  if (!response.body) throw new Error("当前浏览器不支持流式响应");
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
      let eventName = "message";
      let data = "";
      lines.forEach((line) => {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) data += line.slice(5).trim();
      });
      if (!data) return;
      try {
        onEvent(eventName, JSON.parse(data));
      } catch {
        onEvent(eventName, { text: data });
      }
    });
  }
}

function formToObject(form) {
  const result = {};
  const data = new FormData(form);
  data.forEach((value, key) => {
    result[key] = value;
  });
  $all('input[type="checkbox"][name]', form).forEach((input) => {
    result[input.name] = input.checked;
  });
  return result;
}

function setPage(route) {
  if (!pages.length) return;
  const nextRoute = route || "dashboard";
  pages.forEach((page) => page.classList.toggle("active", page.dataset.page === nextRoute));
  navLinks.forEach((link) => link.classList.toggle("active", link.dataset.route === nextRoute));
  if (!document.querySelector(`.page[data-page="${nextRoute}"]`)) {
    setPage("dashboard");
  }
}

function routeFromHash() {
  return window.location.hash.replace(/^#\/?/, "") || "dashboard";
}

function openModal(name) {
  const modal = document.querySelector(`[data-modal="${name}"]`);
  if (modal) modal.classList.add("open");
}

function closeModal(element) {
  element.closest(".modal-backdrop")?.classList.remove("open");
}

function setFormValues(form, values) {
  Object.entries(values || {}).forEach(([key, value]) => {
    const field = form.elements[key];
    if (!field) return;
    if (field.type === "checkbox") {
      field.checked = Boolean(value);
    } else {
      field.value = value ?? "";
    }
  });
}

function setStat(label, value) {
  const stat = $all(".stat").find((item) => $(".stat-label", item)?.textContent === label);
  const target = stat ? $(".stat-value", stat) : null;
  if (target) target.textContent = value;
}

async function loadDashboard() {
  try {
    const summary = await apiJson("/admin/dashboard/summary");
    setStat("业务线数量", summary.business_line_count);
    setStat("知识库数量", summary.knowledge_base_count);
    setStat("文档数量", summary.document_count);
    setStat("Chunk 数量", summary.chunk_count);
    setStat("会话数量", summary.session_count);
    renderDashboardDocuments();
    renderDashboardSessions();
  } catch (error) {
    showToast(error.message);
  }
}

async function loadCompany() {
  state.company = await apiJson("/admin/company/data");
  const form = $("[data-company-form]");
  if (form) setFormValues(form, state.company);
}

async function loadModelConfig() {
  state.modelConfig = await apiJson("/admin/models/data");
  const form = $("[data-model-form]");
  if (form) setFormValues(form, state.modelConfig);
}

async function loadKnowledgeBases() {
  const result = await apiJson("/admin/kb/list");
  state.knowledgeBases = result.items || [];
  renderKnowledgeBases();
  renderUploadKbOptions();
}

async function loadBusinessLines() {
  const result = await apiJson("/admin/business-line/list");
  state.businessLines = result.items || [];
  renderBusinessLines();
  renderPlaygroundBusinessLines();
}

async function loadDocuments() {
  const result = await apiJson("/admin/documents/list");
  state.documents = result.items || [];
  renderDocuments();
  renderDashboardDocuments();
}

async function loadChatSessions() {
  const result = await apiJson("/admin/chat-sessions/list");
  state.chatSessions = result.items || [];
  renderChatSessions(result);
  renderDashboardSessions();
  setStat("会话数量", state.chatSessions.length);
}

function statusMarkup(enabled) {
  return `<span class="status ${enabled ? "ok" : "warn"}">${enabled ? "启用" : "停用"}</span>`;
}

function switchMarkup(checked, dataAttrs) {
  return `<span class="switch-state"><label class="switch"><input type="checkbox" ${checked ? "checked" : ""} ${dataAttrs}><span class="slider"></span></label>${statusMarkup(checked)}</span>`;
}

function tagList(items, getLabel) {
  if (!items.length) return `<span class="page-desc">未绑定</span>`;
  return items.map((item) => `<span class="tag blue">${escapeHtml(getLabel(item))}</span>`).join(" ");
}

function renderBusinessLines() {
  const tbody = $("[data-business-line-tbody]");
  if (!tbody) return;
  if (!state.businessLines.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="page-desc">暂无业务线</td></tr>`;
    return;
  }
  tbody.innerHTML = state.businessLines.map((item) => `
    <tr>
      <td>${switchMarkup(item.enabled, `data-toggle-business-line="${escapeHtml(item.business_line_id)}"`)}</td>
      <td><strong>${escapeHtml(item.business_line_name)}</strong><br><span class="page-desc">${escapeHtml(item.business_line_id)}</span></td>
      <td>${escapeHtml(item.scenario || "-")}</td>
      <td>${tagList(item.knowledge_bases || [], (kb) => kb.name)}</td>
      <td><button class="link-btn" data-open-embed-code data-business-line-id="${escapeHtml(item.business_line_id)}">查看嵌入代码</button></td>
      <td>
        <div class="row-actions">
          <button class="link-btn" data-open-modal="business-line" data-business-line-id="${escapeHtml(item.business_line_id)}">编辑</button>
          <button class="link-btn" data-delete-business-line="${escapeHtml(item.business_line_id)}">删除</button>
        </div>
      </td>
    </tr>
  `).join("");
}

function renderKnowledgeBases() {
  const tbody = $("[data-kb-tbody]");
  if (!tbody) return;
  if (!state.knowledgeBases.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="page-desc">暂无知识库</td></tr>`;
    return;
  }
  tbody.innerHTML = state.knowledgeBases.map((item) => `
    <tr>
      <td>${switchMarkup(item.enabled, `data-toggle-kb="${escapeHtml(item.kb_id)}"`)}</td>
      <td><strong>${escapeHtml(item.name)}</strong><br><span class="page-desc">${escapeHtml(item.kb_id)}</span></td>
      <td>${escapeHtml(item.description || "-")}</td>
      <td>${tagList(item.business_lines || [], (line) => line.business_line_name)}</td>
      <td>${item.doc_count || 0}</td>
      <td>${item.chunk_count || 0}</td>
      <td>
        <div class="row-actions">
          <button class="link-btn" data-open-modal="kb" data-kb-id="${escapeHtml(item.kb_id)}">编辑</button>
          <button class="link-btn" data-delete-kb="${escapeHtml(item.kb_id)}">删除</button>
        </div>
      </td>
    </tr>
  `).join("");
}

function parseStatusMarkup(status) {
  const map = {
    pending: ["warn", "待解析"],
    parsing: ["warn", "解析中"],
    success: ["ok", "成功"],
    failed: ["err", "失败"]
  };
  const [style, label] = map[status] || ["warn", status || "-"];
  return `<span class="status ${style}">${escapeHtml(label)}</span>`;
}

function renderDocuments() {
  const tbody = $("[data-documents-tbody]");
  if (!tbody) return;
  if (!state.documents.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="page-desc">暂无文档，请先上传。</td></tr>`;
    return;
  }
  tbody.innerHTML = state.documents.map((item) => `
    <tr>
      <td><strong>${escapeHtml(item.filename)}</strong><br><span class="page-desc">${escapeHtml(item.doc_id)}</span></td>
      <td>${escapeHtml(item.kb_name || item.kb_id)}</td>
      <td>${escapeHtml(item.file_type || "-")}</td>
      <td>${parseStatusMarkup(item.parse_status)}</td>
      <td>${item.chunk_count || 0}</td>
      <td>${item.image_count || 0}</td>
      <td>
        <div class="row-actions">
          <button class="link-btn" data-open-doc-detail="${escapeHtml(item.doc_id)}">详情</button>
          <button class="link-btn" data-reparse-doc="${escapeHtml(item.doc_id)}">重解析</button>
          <button class="link-btn" data-delete-doc="${escapeHtml(item.doc_id)}">删除</button>
        </div>
      </td>
    </tr>
  `).join("");
}

function renderDashboardDocuments() {
  const tbody = $("[data-dashboard-documents-tbody]");
  if (!tbody) return;
  const items = state.documents.slice(0, 5);
  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="page-desc">暂无文档</td></tr>`;
    return;
  }
  tbody.innerHTML = items.map((item) => `
    <tr>
      <td>${escapeHtml(item.filename)}</td>
      <td>${escapeHtml(item.kb_name || item.kb_id)}</td>
      <td>${parseStatusMarkup(item.parse_status)}</td>
      <td>${escapeHtml(item.updated_at || "-")}</td>
    </tr>
  `).join("");
}

function renderChatSessions(result = {}) {
  const tbody = $("[data-chat-sessions-tbody]");
  if (!tbody) return;
  if (result.available === false) {
    tbody.innerHTML = `<tr><td colspan="7" class="page-desc">${escapeHtml(result.message || "聊天记录暂不可用")}</td></tr>`;
    return;
  }
  if (!state.chatSessions.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="page-desc">暂无聊天记录。打开 Demo 聊一句后会出现在这里。</td></tr>`;
    return;
  }
  tbody.innerHTML = state.chatSessions.map((item) => `
    <tr>
      <td>${escapeHtml(item.session_id || "")}</td>
      <td>${escapeHtml(item.business_line_name || item.business_line_id || "-")}</td>
      <td>${escapeHtml(item.last_message || "-")}</td>
      <td>${item.message_count || 0}</td>
      <td>${(item.subject_names || []).map((name) => escapeHtml(name)).join("、") || "-"}</td>
      <td>${escapeHtml(item.updated_at || "-")}</td>
      <td><button class="link-btn" data-open-session-detail="${escapeHtml(item.session_id || "")}">查看</button></td>
    </tr>
  `).join("");
}

function renderDashboardSessions() {
  const tbody = $("[data-dashboard-sessions-tbody]");
  if (!tbody) return;
  const items = state.chatSessions.slice(0, 5);
  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="3" class="page-desc">暂无会话</td></tr>`;
    return;
  }
  tbody.innerHTML = items.map((item) => `
    <tr>
      <td>${escapeHtml(item.session_id || "")}</td>
      <td>${escapeHtml(item.last_message || "-")}</td>
      <td>${escapeHtml(item.updated_at || "-")}</td>
    </tr>
  `).join("");
}

function renderPlaygroundBusinessLines() {
  const select = $("[data-playground-business-line]");
  if (!select) return;
  const currentValue = select.value;
  const lines = state.businessLines.filter((line) => line.enabled);
  if (!lines.length) {
    select.innerHTML = `<option value="">暂无可测试业务线</option>`;
    updatePlaygroundBoundKbs();
    return;
  }
  select.innerHTML = lines.map((line) => `
    <option value="${escapeHtml(line.business_line_id)}">${escapeHtml(line.business_line_name)}</option>
  `).join("");
  if (lines.some((line) => line.business_line_id === currentValue)) {
    select.value = currentValue;
  }
  updatePlaygroundBoundKbs();
}

function updatePlaygroundBoundKbs() {
  const select = $("[data-playground-business-line]");
  const target = $("[data-playground-kbs]");
  if (!select || !target) return;
  const line = state.businessLines.find((item) => item.business_line_id === select.value);
  const names = (line?.knowledge_bases || []).map((kb) => kb.name).filter(Boolean);
  target.textContent = names.length ? names.join("、") : "暂无绑定知识库";
}

function renderPlaygroundReferences(references) {
  const wrap = $("[data-playground-references]");
  if (!wrap) return;
  const items = Array.isArray(references) ? references : [];
  if (!items.length) {
    wrap.innerHTML = "";
    return;
  }
  wrap.innerHTML = items.map((ref, index) => {
    if (typeof ref === "string") {
      return `<div class="reference"><div class="reference-title"><span>[${index + 1}] 引用</span></div><p>${escapeHtml(ref)}</p></div>`;
    }
    const title = ref.title || ref.doc_name || ref.file_name || `引用 ${index + 1}`;
    const score = ref.score == null ? "" : `score: ${ref.score}`;
    const text = ref.text || ref.content || ref.chunk || "";
    return `
      <div class="reference">
        <div class="reference-title"><span>[${index + 1}] ${escapeHtml(title)}</span><span>${escapeHtml(score)}</span></div>
        <p>${escapeHtml(text)}</p>
      </div>
    `;
  }).join("");
}

function kbBoundLineNames(kb) {
  return (kb?.business_lines || []).map((line) => line.business_line_name).filter(Boolean);
}

function confirmDisableKnowledgeBase(kb) {
  const names = kbBoundLineNames(kb);
  if (!names.length) return true;
  return window.confirm(`停用知识库「${kb.name}」后，会自动取消与以下业务线的绑定：${names.join("、")}。是否继续？`);
}

function renderKbPicker(selectedIds = []) {
  const list = $("[data-kb-picker-list]");
  if (!list) return;
  list.innerHTML = state.knowledgeBases.map((kb) => `
    <label class="kb-picker-row ${kb.enabled ? "" : "disabled"}" title="${kb.enabled ? "" : "停用知识库不能绑定到业务线"}">
      <input type="checkbox" value="${escapeHtml(kb.kb_id)}" ${kb.enabled && selectedIds.includes(kb.kb_id) ? "checked" : ""} ${kb.enabled ? "" : "disabled"}>
      <span><span class="kb-picker-name">${escapeHtml(kb.name)}</span><span class="kb-picker-desc">${escapeHtml(kb.description || "")}</span></span>
      <span class="kb-status ${kb.enabled ? "" : "off"}">${kb.enabled ? "启用" : "停用"}</span>
    </label>
  `).join("");
  syncKbPicker();
}

function renderUploadKbOptions() {
  const select = $("[data-upload-kb-select]");
  if (!select) return;
  if (!state.knowledgeBases.length) {
    select.innerHTML = `<option value="">暂无知识库</option>`;
    return;
  }
  select.innerHTML = state.knowledgeBases
    .map((kb) => `<option value="${escapeHtml(kb.kb_id)}">${escapeHtml(kb.name)}</option>`)
    .join("");
}

function syncKbPicker() {
  const picker = $(".kb-picker");
  if (!picker) return;
  const rows = $all(".kb-picker-row", picker);
  const selectedRows = rows.filter((row) => $("input", row)?.checked);
  const countLabel = $(".kb-picker-summary strong", picker);
  const selectedWrap = $(".kb-picker-selected", picker);
  if (countLabel) countLabel.textContent = `已选 ${selectedRows.length} 个知识库`;
  if (selectedWrap) {
    selectedWrap.innerHTML = selectedRows.slice(0, 3).map((row) => {
      const name = $(".kb-picker-name", row)?.textContent || "";
      return `<span class="kb-pill">${escapeHtml(name)}</span>`;
    }).join("");
    if (selectedRows.length > 3) {
      selectedWrap.insertAdjacentHTML("beforeend", `<span class="kb-more">+${selectedRows.length - 3}</span>`);
    }
  }
}

function openBusinessLineModal(businessLineId = "") {
  const form = $("[data-business-line-form]");
  if (!form) return;
  const item = state.businessLines.find((line) => line.business_line_id === businessLineId);
  form.reset();
  form.dataset.editingId = businessLineId || "";
  form.elements.business_line_id.readOnly = Boolean(item);
  setFormValues(form, item || { enabled: true });
  renderKbPicker(item?.kb_ids || []);
  openModal("business-line");
}

function openKnowledgeBaseModal(kbId = "") {
  const form = $("[data-kb-form]");
  if (!form) return;
  const item = state.knowledgeBases.find((kb) => kb.kb_id === kbId);
  form.reset();
  form.dataset.editingId = kbId || "";
  setFormValues(form, item || { enabled: true });
  const bound = $("[data-kb-bound-lines]", form);
  if (bound) {
    bound.value = item ? (item.business_lines || []).map((line) => line.business_line_name).join("、") || "暂无绑定业务线" : "新建后可在业务线中绑定";
  }
  openModal("kb");
}

function renderDocumentDetail(document) {
  state.activeDocId = document.doc_id;
  const title = $("[data-doc-detail-title]");
  const body = $("[data-doc-detail-body]");
  if (title) title.textContent = `文档详情：${document.filename}`;
  if (!body) return;
  const images = document.images || [];
  body.innerHTML = `
    <div class="env-list">
      <div class="env-row"><span>所属知识库</span><strong>${escapeHtml(document.kb_name || document.kb_id)}</strong></div>
      <div class="env-row"><span>解析状态</span>${parseStatusMarkup(document.parse_status)}</div>
      <div class="env-row"><span>文件路径</span><span>${escapeHtml(document.file_path || "-")}</span></div>
      <div class="env-row"><span>Chunk / 图片</span><strong>${document.chunk_count || 0} / ${document.image_count || 0}</strong></div>
      <div class="env-row"><span>错误信息</span><span>${escapeHtml(document.error_msg || "-")}</span></div>
    </div>
    <h3>图片预览</h3>
    ${
      images.length
        ? images.map((image) => `
          <div class="image-row">
            <div class="thumb"></div>
            <p>${escapeHtml(image.caption || image.alt_text || image.filename || "暂无图片说明")}</p>
          </div>
        `).join("")
        : `<p class="page-desc">暂无图片。后续解析流程写入 document_image 后会展示在这里。</p>`
    }
  `;
}

function renderSessionDetail(sessionId, messages, available = true, message = "") {
  state.activeSessionId = sessionId;
  const title = $("[data-session-detail-title]");
  const body = $("[data-session-detail-body]");
  if (title) title.textContent = `聊天记录详情：${sessionId}`;
  if (!body) return;
  if (!available) {
    body.innerHTML = `<p class="page-desc">${escapeHtml(message || "聊天记录暂不可用")}</p>`;
    return;
  }
  if (!messages.length) {
    body.innerHTML = `<p class="page-desc">该会话暂无消息。</p>`;
    return;
  }
  body.innerHTML = messages.map((item) => `
    <div class="message-card">
      <div class="message-meta">
        <span class="tag ${item.role === "assistant" ? "green" : "blue"}">${escapeHtml(item.role || "-")}</span>
        <span>${escapeHtml(item.created_at || "")}</span>
      </div>
      ${item.rewritten_query ? `<div class="message-meta"><span>改写问题：${escapeHtml(item.rewritten_query)}</span></div>` : ""}
      <p>${escapeHtml(item.content || "")}</p>
      ${
        (item.references || []).length
          ? `<div class="references">${item.references.map((ref, index) => `
            <div class="reference">
              <div class="reference-title"><span>[${index + 1}] ${escapeHtml(ref.title || ref.doc_name || ref.file_name || "引用")}</span><span>${ref.score == null ? "" : `score: ${escapeHtml(ref.score)}`}</span></div>
              <p>${escapeHtml(ref.text || ref.content || ref.chunk || "")}</p>
            </div>
          `).join("")}</div>`
          : ""
      }
    </div>
  `).join("");
}

async function reloadDocumentViews() {
  await Promise.all([loadDocuments(), loadKnowledgeBases(), loadDashboard()]);
  renderUploadKbOptions();
}

async function deleteDocument(docId) {
  if (!docId) return;
  if (!window.confirm("确定删除该文档吗？文档元数据会被移除。")) return;
  await apiJson(`/admin/documents/${encodeURIComponent(docId)}/delete`, { method: "POST" });
  showToast("文档已删除");
  document.querySelector('[data-modal="doc-detail"]')?.classList.remove("open");
  state.activeDocId = "";
  await reloadDocumentViews();
}

async function refreshConfigViews() {
  await Promise.all([loadKnowledgeBases(), loadBusinessLines(), loadDocuments(), loadDashboard()]);
  renderUploadKbOptions();
}

function bindForms() {
  const companyForm = $("[data-company-form]");
  companyForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await apiJson("/admin/company/save", {
        method: "POST",
        body: JSON.stringify(formToObject(companyForm))
      });
      state.company = result.data;
      showToast("企业信息已保存");
    } catch (error) {
      showToast(error.message);
    }
  });

  const modelForm = $("[data-model-form]");
  modelForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = formToObject(modelForm);
      payload.top_k = Number(payload.top_k || 5);
      const result = await apiJson("/admin/models/save", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      state.modelConfig = result.data;
      showToast("模型配置已保存");
    } catch (error) {
      showToast(error.message);
    }
  });

  const businessLineForm = $("[data-business-line-form]");
  businessLineForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = formToObject(businessLineForm);
      payload.kb_ids = $all("[data-kb-picker-list] input:checked:not(:disabled)").map((input) => input.value);
      const result = await apiJson("/admin/business-line/save", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      showToast(result.message || "业务线已保存");
      closeModal(businessLineForm);
      await refreshConfigViews();
    } catch (error) {
      showToast(error.message);
    }
  });

  const kbForm = $("[data-kb-form]");
  kbForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = formToObject(kbForm);
      const kbId = payload.kb_id;
      delete payload.kb_id;
      const currentKb = state.knowledgeBases.find((kb) => kb.kb_id === kbId);
      if (currentKb?.enabled && !payload.enabled && !confirmDisableKnowledgeBase(currentKb)) {
        kbForm.elements.enabled.checked = true;
        return;
      }
      const url = kbId ? `/admin/kb/${encodeURIComponent(kbId)}/update` : "/admin/kb/create";
      const result = await apiJson(url, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      showToast(result.message || "知识库已保存");
      closeModal(kbForm);
      await refreshConfigViews();
    } catch (error) {
      showToast(error.message);
    }
  });

  const uploadForm = $("[data-upload-form]");
  uploadForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = new FormData(uploadForm);
      const result = await apiJson("/admin/documents/upload", {
        method: "POST",
        body: payload
      });
      showToast(result.message || "文档已上传");
      uploadForm.reset();
      closeModal(uploadForm);
      await reloadDocumentViews();
    } catch (error) {
      showToast(error.message);
    }
  });
}

function bindDelegatedEvents() {
  document.addEventListener("click", async (event) => {
    const closeButton = event.target.closest("[data-close-modal]");
    if (closeButton) {
      closeModal(closeButton);
      return;
    }

    const modalButton = event.target.closest("[data-open-modal]");
    if (modalButton) {
      const modalName = modalButton.dataset.openModal;
      if (modalName === "business-line") {
        openBusinessLineModal(modalButton.dataset.businessLineId || "");
      } else if (modalName === "kb") {
        openKnowledgeBaseModal(modalButton.dataset.kbId || "");
      } else {
        openModal(modalName);
      }
      return;
    }

    const row = event.target.closest(".kb-picker-row");
    if (row && !event.target.matches("input")) {
      const checkbox = $("input", row);
      if (checkbox) {
        event.preventDefault();
        if (checkbox.disabled) {
          showToast("停用知识库不能绑定到业务线");
          return;
        }
        checkbox.checked = !checkbox.checked;
        syncKbPicker();
      }
      return;
    }

    const copyButton = event.target.closest("[data-copy-code]");
    if (copyButton) {
      const code = document.querySelector(copyButton.dataset.copyCode)?.innerText || "";
      try {
        await navigator.clipboard.writeText(code);
        showToast("嵌入代码已复制");
      } catch {
        showToast("当前浏览器不支持自动复制");
      }
      return;
    }

    const embedButton = event.target.closest("[data-open-embed-code]");
    if (embedButton) {
      try {
        const businessLineId = embedButton.dataset.businessLineId;
        const data = await apiJson(`/admin/business-line/${encodeURIComponent(businessLineId)}/embed-code`);
        const name = $("[data-modal-business-line-name]");
        const kbs = $("[data-modal-business-line-kbs]");
        const code = $("#modal-embed-code");
        if (name) name.textContent = data.business_line_name || businessLineId;
        if (kbs) kbs.textContent = (data.bound_knowledge_bases || []).map((kb) => kb.name).join("、") || "暂无绑定知识库";
        if (code) code.textContent = data.embed_code;
        openModal("embed-code");
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const deleteBusinessLine = event.target.closest("[data-delete-business-line]");
    if (deleteBusinessLine) {
      const id = deleteBusinessLine.dataset.deleteBusinessLine;
      if (!window.confirm("确定删除该业务线吗？绑定关系会一起删除。")) return;
      try {
        await apiJson(`/admin/business-line/${encodeURIComponent(id)}/delete`, { method: "POST" });
        showToast("业务线已删除");
        await refreshConfigViews();
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const deleteKb = event.target.closest("[data-delete-kb]");
    if (deleteKb) {
      const id = deleteKb.dataset.deleteKb;
      if (!window.confirm("确定删除该知识库吗？绑定关系会一起删除。")) return;
      try {
        await apiJson(`/admin/kb/${encodeURIComponent(id)}/delete`, { method: "POST" });
        showToast("知识库已删除");
        await refreshConfigViews();
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const docDetailButton = event.target.closest("[data-open-doc-detail]");
    if (docDetailButton) {
      try {
        const docId = docDetailButton.dataset.openDocDetail;
        const document = await apiJson(`/admin/documents/${encodeURIComponent(docId)}`);
        renderDocumentDetail(document);
        openModal("doc-detail");
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const reparseDocButton = event.target.closest("[data-reparse-doc]");
    if (reparseDocButton) {
      try {
        const docId = reparseDocButton.dataset.reparseDoc;
        const result = await apiJson(`/admin/documents/${encodeURIComponent(docId)}/reparse`, { method: "POST" });
        showToast(result.message || "已提交重解析");
        await reloadDocumentViews();
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const deleteDocButton = event.target.closest("[data-delete-doc]");
    if (deleteDocButton) {
      try {
        await deleteDocument(deleteDocButton.dataset.deleteDoc);
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const detailReparseButton = event.target.closest("[data-doc-detail-reparse]");
    if (detailReparseButton) {
      try {
        const docId = state.activeDocId;
        if (!docId) return;
        const result = await apiJson(`/admin/documents/${encodeURIComponent(docId)}/reparse`, { method: "POST" });
        showToast(result.message || "已提交重解析");
        const document = await apiJson(`/admin/documents/${encodeURIComponent(docId)}`);
        renderDocumentDetail(document);
        await reloadDocumentViews();
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const detailDeleteButton = event.target.closest("[data-doc-detail-delete]");
    if (detailDeleteButton) {
      try {
        await deleteDocument(state.activeDocId);
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const sessionDetailButton = event.target.closest("[data-open-session-detail]");
    if (sessionDetailButton) {
      try {
        const sessionId = sessionDetailButton.dataset.openSessionDetail;
        const result = await apiJson(`/admin/chat-sessions/${encodeURIComponent(sessionId)}`);
        renderSessionDetail(sessionId, result.messages || [], result.available !== false, result.message || "");
        openModal("session-detail");
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const clearSessionButton = event.target.closest("[data-clear-session]");
    if (clearSessionButton) {
      const sessionId = state.activeSessionId;
      if (!sessionId) return;
      if (!window.confirm("确定清空该会话吗？")) return;
      try {
        const result = await apiJson(`/admin/chat-sessions/${encodeURIComponent(sessionId)}/clear`, { method: "POST" });
        showToast(result.message || "会话已清空");
        renderSessionDetail(sessionId, [], true);
        await Promise.all([loadChatSessions(), loadDashboard()]);
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const clearAllSessionsButton = event.target.closest("[data-clear-chat-sessions]");
    if (clearAllSessionsButton) {
      if (!window.confirm("确定清空全部聊天记录吗？")) return;
      try {
        const result = await apiJson("/admin/chat-sessions/clear-all", { method: "POST" });
        showToast(result.message || "全部会话已清空");
        await Promise.all([loadChatSessions(), loadDashboard()]);
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    const toastButton = event.target.closest("[data-toast-message]");
    if (toastButton) showToast(toastButton.dataset.toastMessage);
  });

  document.addEventListener("change", async (event) => {
    const businessLineToggle = event.target.closest("[data-toggle-business-line]");
    if (businessLineToggle) {
      const id = businessLineToggle.dataset.toggleBusinessLine;
      try {
        await apiJson(`/admin/business-line/${encodeURIComponent(id)}/toggle`, {
          method: "POST",
          body: JSON.stringify({ enabled: businessLineToggle.checked })
        });
        await loadBusinessLines();
        await loadDashboard();
      } catch (error) {
        businessLineToggle.checked = !businessLineToggle.checked;
        showToast(error.message);
      }
      return;
    }

    const kbToggle = event.target.closest("[data-toggle-kb]");
    if (kbToggle) {
      const id = kbToggle.dataset.toggleKb;
      const currentKb = state.knowledgeBases.find((kb) => kb.kb_id === id);
      if (!kbToggle.checked && !confirmDisableKnowledgeBase(currentKb)) {
        kbToggle.checked = true;
        return;
      }
      try {
        const result = await apiJson(`/admin/kb/${encodeURIComponent(id)}/toggle`, {
          method: "POST",
          body: JSON.stringify({ enabled: kbToggle.checked })
        });
        showToast(result.message || "知识库状态已更新");
        await refreshConfigViews();
      } catch (error) {
        kbToggle.checked = !kbToggle.checked;
        showToast(error.message);
      }
      return;
    }

    if (event.target.closest(".kb-picker")) {
      syncKbPicker();
    }
  });

  document.addEventListener("input", (event) => {
    const tableFilter = event.target.closest("[data-filter-table]");
    if (tableFilter) {
      const page = tableFilter.closest(".page");
      const rows = $all("tbody tr", page);
      const keyword = tableFilter.value.trim().toLowerCase();
      rows.forEach((row) => {
        row.style.display = row.textContent.toLowerCase().includes(keyword) ? "" : "none";
      });
      return;
    }

    const pickerSearch = event.target.closest(".kb-picker-tools input");
    if (pickerSearch) {
      const keyword = pickerSearch.value.trim().toLowerCase();
      $all(".kb-picker-row").forEach((row) => {
        row.style.display = row.textContent.toLowerCase().includes(keyword) ? "" : "none";
      });
    }
  });
}

function bindPlayground() {
  const playgroundForm = document.querySelector("[data-playground-form]");
  if (!playgroundForm) return;
  const businessLineSelect = $("[data-playground-business-line]", playgroundForm);
  businessLineSelect?.addEventListener("change", updatePlaygroundBoundKbs);

  playgroundForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const answer = $("[data-playground-answer]");
    const original = $("[data-playground-original]");
    const rewritten = $("[data-playground-rewritten]");
    const message = playgroundForm.elements.message?.value.trim() || "";
    const businessLineId = businessLineSelect?.value || "";
    if (!message) {
      showToast("请输入测试问题");
      return;
    }
    if (!businessLineId) {
      showToast("请选择业务线");
      return;
    }

    if (original) original.value = message;
    if (rewritten) rewritten.value = "";
    renderPlaygroundReferences([]);
    if (answer) {
      answer.innerHTML = `<div data-playground-answer-text></div><p class="page-desc" data-playground-progress>正在连接后端...</p>`;
    }
    const answerText = $("[data-playground-answer-text]");
    const progress = $("[data-playground-progress]");
    let finalAnswer = "";

    try {
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: `admin_playground_${Date.now().toString(36)}`,
          message,
          company_id: "default_company",
          business_line_id: businessLineId
        })
      });
      if (!response.ok) throw new Error(`请求失败：${response.status}`);

      await readSse(response, (eventName, data) => {
        if (eventName === "progress" && progress) {
          progress.textContent = `${data.label || data.step || "处理中"} ${data.percent || 0}%`;
        } else if (eventName === "rewrite" && rewritten) {
          rewritten.value = data.rewritten_query || data.query || "";
        } else if (eventName === "delta") {
          finalAnswer += data.text || data.content || "";
          if (answerText) answerText.textContent = finalAnswer;
        } else if (eventName === "image" && data.message && answer) {
          answer.insertAdjacentHTML("beforeend", `<p class="page-desc">${escapeHtml(data.message)}</p>`);
        } else if (eventName === "references") {
          renderPlaygroundReferences(data.references);
        } else if (eventName === "final") {
          if (!finalAnswer && data.answer) {
            finalAnswer = data.answer;
            if (answerText) answerText.textContent = finalAnswer;
          }
          if (progress) progress.textContent = "完成";
        }
      });
      if (progress) progress.textContent = "完成";
      showToast("测试回答已生成");
    } catch (error) {
      if (progress) progress.textContent = "";
      if (answerText) answerText.textContent = error.message;
      showToast(error.message);
    }
  });
}

function bindLogin() {
  const loginForm = document.querySelector("[data-login-form]");
  if (!loginForm) return;
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const secret = loginForm.querySelector("input")?.value.trim() || "";
      await apiJson("/login", {
        method: "POST",
        body: JSON.stringify({ secret })
      });
      window.location.href = "/admin";
    } catch {
      window.location.href = "/admin";
    }
  });
}

async function bootstrapAdmin() {
  bindForms();
  bindDelegatedEvents();
  bindPlayground();

  if ($("[data-company-form]")) {
    try {
      await Promise.all([loadCompany(), loadModelConfig(), loadKnowledgeBases(), loadDocuments()]);
      await loadBusinessLines();
      await loadDashboard();
      await loadChatSessions();
    } catch (error) {
      showToast(error.message);
    }
  }
}

window.addEventListener("hashchange", () => setPage(routeFromHash()));
setPage(routeFromHash());
bindLogin();
bootstrapAdmin();
