(function () {
  const MARKED_URL = "https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js";
  const DOMPURIFY_URL = "https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js";
  const MATHJAX_URL = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js";
  let mathJaxPromise = null;

  function escapeHtml(text) {
    return String(text ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    })[char]);
  }

  function loadScript(src, marker) {
    if (marker && document.querySelector(`script[data-rag-lib="${marker}"]`)) {
      return Promise.resolve();
    }
    return new Promise((resolve, reject) => {
      const tag = document.createElement("script");
      tag.src = src;
      tag.defer = true;
      if (marker) tag.dataset.ragLib = marker;
      tag.onload = () => resolve();
      tag.onerror = () => reject(new Error(`脚本加载失败：${src}`));
      document.head.appendChild(tag);
    });
  }

  async function ensureMarked() {
    if (window.marked?.parse || typeof window.marked === "function") return;
    await loadScript(MARKED_URL, "marked");
  }

  async function ensureDomPurify() {
    if (window.DOMPurify?.sanitize) return;
    await loadScript(DOMPURIFY_URL, "dompurify");
  }

  function waitForMathJax() {
    if (window.MathJax?.typesetPromise) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const startedAt = Date.now();
      const timer = window.setInterval(() => {
        if (window.MathJax?.typesetPromise) {
          window.clearInterval(timer);
          resolve();
          return;
        }
        if (Date.now() - startedAt > 6000) {
          window.clearInterval(timer);
          reject(new Error("MathJax 加载超时"));
        }
      }, 80);
    });
  }

  function ensureMathJax() {
    window.MathJax = window.MathJax || {
      tex: { inlineMath: [["\\(", "\\)"], ["$", "$"]], displayMath: [["$$", "$$"]] },
      startup: { typeset: false }
    };
    if (window.MathJax.typesetPromise) {
      return Promise.resolve();
    }
    if (!mathJaxPromise) {
      const existing = document.querySelector('script[data-rag-lib="mathjax"], script[src*="mathjax@3"]');
      mathJaxPromise = existing
        ? waitForMathJax()
        : loadScript(MATHJAX_URL, "mathjax").then(waitForMathJax);
    }
    return mathJaxPromise;
  }

  async function ready() {
    await Promise.all([ensureMarked(), ensureDomPurify()]);
  }

  function normalizeMarkdown(text) {
    return String(text || "")
      .replace(/\r\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n");
  }

  function protectMath(text) {
    const blocks = [];
    const value = String(text || "").replace(
      /\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)/g,
      (match) => {
        const token = `RAG_MATH_TOKEN_${blocks.length}`;
        blocks.push(match);
        return token;
      }
    );
    return { value, blocks };
  }

  function restoreMath(html, blocks) {
    return blocks.reduce(
      (result, block, index) => result.replaceAll(`RAG_MATH_TOKEN_${index}`, escapeHtml(block)),
      html
    );
  }

  async function renderToHtml(markdown) {
    const protectedMath = protectMath(normalizeMarkdown(markdown));
    try {
      await ready();
      const markedApi = window.marked;
      const parse = markedApi.parse || markedApi;
      if (markedApi.setOptions) {
        markedApi.setOptions({
          async: false,
          breaks: false,
          gfm: true,
          mangle: false,
          pedantic: false
        });
      }
      const rawHtml = parse(protectedMath.value);
      const safeHtml = window.DOMPurify.sanitize(rawHtml, {
        ADD_ATTR: ["target", "rel", "loading", "referrerpolicy"],
        ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i
      });
      return restoreMath(safeHtml, protectedMath.blocks);
    } catch {
      return restoreMath(escapeHtml(protectedMath.value).replace(/\n/g, "<br>"), protectedMath.blocks);
    }
  }

  function decorate(root, options = {}) {
    const imageClass = options.imageClass || "";
    root.querySelectorAll("a[href]").forEach((link) => {
      link.target = "_blank";
      link.rel = "noreferrer";
    });
    root.querySelectorAll("img").forEach((image) => {
      if (imageClass) image.classList.add(imageClass);
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      if (!image.alt) image.alt = "知识库图片";
    });
  }

  function typesetMath(root) {
    if (!root) return;
    window.clearTimeout(root._ragMathTimer);
    root._ragMathTimer = window.setTimeout(() => {
      ensureMathJax()
        .then(() => window.MathJax.typesetPromise([root]))
        .catch(() => {});
    }, 120);
  }

  async function render(root, markdown, options = {}) {
    if (!root) return;
    const token = (root._ragMarkdownToken || 0) + 1;
    root._ragMarkdownToken = token;
    const html = await renderToHtml(markdown);
    if (root._ragMarkdownToken !== token) return;
    root.innerHTML = html;
    decorate(root, options);
    typesetMath(root);
  }

  window.RagMarkdown = {
    ready,
    render,
    renderToHtml
  };
})();
