const pages = Array.from(document.querySelectorAll(".page"));
const navLinks = Array.from(document.querySelectorAll("[data-route]"));
const toast = document.querySelector("[data-toast]");

function showToast(message) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 1800);
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

window.addEventListener("hashchange", () => setPage(routeFromHash()));
setPage(routeFromHash());

document.querySelectorAll("[data-open-modal]").forEach((button) => {
  button.addEventListener("click", () => {
    const modal = document.querySelector(`[data-modal="${button.dataset.openModal}"]`);
    if (modal) modal.classList.add("open");
  });
});

document.querySelectorAll("[data-close-modal]").forEach((button) => {
  button.addEventListener("click", () => {
    button.closest(".modal-backdrop")?.classList.remove("open");
  });
});

document.querySelectorAll("form[data-save]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    showToast(form.dataset.save || "已保存");
  });
});

document.querySelectorAll("[data-toast-message]").forEach((button) => {
  button.addEventListener("click", () => showToast(button.dataset.toastMessage));
});

document.querySelectorAll("[data-copy-code]").forEach((button) => {
  button.addEventListener("click", async () => {
    const code = document.querySelector(button.dataset.copyCode)?.innerText || "";
    try {
      await navigator.clipboard.writeText(code);
      showToast("嵌入代码已复制");
    } catch {
      showToast("当前浏览器不支持自动复制");
    }
  });
});

document.querySelectorAll("[data-open-embed-code]").forEach((button) => {
  button.addEventListener("click", () => {
    const modal = document.querySelector('[data-modal="embed-code"]');
    const code = document.querySelector("#modal-embed-code");
    const name = document.querySelector("[data-modal-business-line-name]");
    const kbs = document.querySelector("[data-modal-business-line-kbs]");
    const businessLineId = button.dataset.businessLineId || "business_line_course";
    const color = button.dataset.themeColor || "#2563eb";
    if (name) name.textContent = button.dataset.businessLineName || "";
    if (kbs) kbs.textContent = button.dataset.kbs || "";
    if (code) {
      code.textContent = `<script
  src="http://localhost:8000/static/chat-widget.js"
  data-company-id="default_company"
  data-business-line-id="${businessLineId}"
  data-theme-color="${color}"
></script>`;
    }
    modal?.classList.add("open");
  });
});

document.querySelectorAll(".kb-picker").forEach((picker) => {
  const countLabel = picker.querySelector(".kb-picker-summary strong");
  const selectedWrap = picker.querySelector(".kb-picker-selected");
  const search = picker.querySelector(".kb-picker-tools input");
  const rows = Array.from(picker.querySelectorAll(".kb-picker-row"));

  function syncSelected() {
    const selectedRows = rows.filter((row) => row.querySelector("input")?.checked);
    if (countLabel) countLabel.textContent = `已选 ${selectedRows.length} 个知识库`;
    if (selectedWrap) {
      selectedWrap.innerHTML = selectedRows.slice(0, 3).map((row) => {
        const name = row.querySelector(".kb-picker-name")?.textContent || "";
        return `<span class="kb-pill">${name}</span>`;
      }).join("");
      if (selectedRows.length > 3) {
        selectedWrap.insertAdjacentHTML("beforeend", `<span class="kb-more">+${selectedRows.length - 3}</span>`);
      }
    }
  }

  function filterRows() {
    const keyword = (search?.value || "").trim().toLowerCase();
    rows.forEach((row) => {
      row.style.display = row.textContent.toLowerCase().includes(keyword) ? "" : "none";
    });
  }

  rows.forEach((row) => row.querySelector("input")?.addEventListener("change", syncSelected));
  search?.addEventListener("input", filterRows);
  syncSelected();
});

const playgroundForm = document.querySelector("[data-playground-form]");
if (playgroundForm) {
  playgroundForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const answer = document.querySelector("[data-playground-answer]");
    if (!answer) return;
    const text = "RAG 的基本流程包括文档解析、chunk 切分、embedding、向量检索、可选 rerank，以及把检索片段组装进 Prompt 后调用大模型生成回答。";
    answer.textContent = "";
    let index = 0;
    const timer = window.setInterval(() => {
      answer.textContent += text[index] || "";
      index += 1;
      if (index >= text.length) {
        window.clearInterval(timer);
        showToast("测试回答已生成");
      }
    }, 18);
  });
}

const loginForm = document.querySelector("[data-login-form]");
if (loginForm) {
  loginForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const secret = loginForm.querySelector("input")?.value.trim();
    const error = document.querySelector("[data-login-error]");
    if (secret === "123456") {
      window.location.href = "admin.html";
    } else if (error) {
      error.textContent = "暗号错误，请重新输入";
    }
  });
}
