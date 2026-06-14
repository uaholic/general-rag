"""PDF 解析服务。

当前默认使用 PyMuPDF 做轻量解析，保证本地练习时不依赖大模型下载。
如果需要更完整的版面、表格和 OCR 解析，可以设置 PDF_PARSE_ENGINE=magic_pdf。
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil

import fitz

from app.shared.utils.path_util import PROJECT_ROOT


PARSED_ROOT = PROJECT_ROOT / "app" / "resources" / "parsed"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}


@dataclass(slots=True)
class PdfParseResult:
    """PDF 解析产物。"""

    markdown_text: str
    markdown_path: Path
    image_dir: Path
    image_count: int
    engine: str


class PdfParserService:
    """把 PDF 转成服务端可控的 Markdown 和图片目录。"""

    def parse_pdf(self, *, pdf_path: str, doc_id: str, engine: str | None = None) -> PdfParseResult:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {path}")

        selected_engine = (engine or os.getenv("PDF_PARSE_ENGINE") or "pymupdf").lower()
        if selected_engine in {"magic_pdf", "mineru"}:
            try:
                return self._parse_with_magic_pdf(path=path, doc_id=doc_id)
            except Exception as exc:
                # 练习阶段优先保证上传可用。生产环境可以改成直接抛错，让前端提示重试。
                fallback = self._parse_with_pymupdf(path=path, doc_id=doc_id)
                note = f"<!-- magic_pdf 解析失败，已降级为 PyMuPDF：{exc} -->\n\n"
                fallback.markdown_path.write_text(note + fallback.markdown_text, encoding="utf-8")
                return PdfParseResult(
                    markdown_text=note + fallback.markdown_text,
                    markdown_path=fallback.markdown_path,
                    image_dir=fallback.image_dir,
                    image_count=fallback.image_count,
                    engine="pymupdf_fallback",
                )

        return self._parse_with_pymupdf(path=path, doc_id=doc_id)

    def find_latest_markdown(self, doc_id: str) -> Path | None:
        """查找某个文档最近一次 PDF 解析出的 Markdown。"""
        doc_dir = PARSED_ROOT / doc_id
        if not doc_dir.exists():
            return None
        markdown_files = [path for path in doc_dir.rglob("*.md") if path.is_file()]
        if not markdown_files:
            return None
        return max(markdown_files, key=lambda item: item.stat().st_mtime)

    def delete_parsed(self, doc_id: str) -> None:
        """删除某个文档的 PDF 解析产物。"""
        doc_dir = PARSED_ROOT / doc_id
        if doc_dir.exists():
            shutil.rmtree(doc_dir)

    def _parse_with_pymupdf(self, *, path: Path, doc_id: str) -> PdfParseResult:
        output_dir = PARSED_ROOT / doc_id / "pymupdf"
        image_dir = output_dir / "images"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        image_dir.mkdir(parents=True, exist_ok=True)

        markdown_parts: list[str] = [f"# {path.stem}", ""]
        image_count = 0

        with fitz.open(path) as pdf:
            for page_index, page in enumerate(pdf, start=1):
                markdown_parts.extend([f"## 第 {page_index} 页", ""])

                text = page.get_text("text").strip()
                if text:
                    markdown_parts.extend([text, ""])

                for image_index, image in enumerate(page.get_images(full=True), start=1):
                    xref = image[0]
                    image_data = pdf.extract_image(xref)
                    image_bytes = image_data.get("image")
                    if not image_bytes:
                        continue
                    extension = image_data.get("ext") or "png"
                    image_name = f"page_{page_index}_image_{image_index}.{extension}"
                    (image_dir / image_name).write_bytes(image_bytes)
                    image_count += 1
                    markdown_parts.extend([f"![第 {page_index} 页图片 {image_index}](images/{image_name})", ""])

                if not text and not page.get_images(full=True):
                    markdown_parts.extend(["_本页未提取到文本或图片。_", ""])

        markdown_text = "\n".join(markdown_parts).strip() + "\n"
        markdown_path = output_dir / f"{path.stem}.md"
        markdown_path.write_text(markdown_text, encoding="utf-8")
        return PdfParseResult(
            markdown_text=markdown_text,
            markdown_path=markdown_path,
            image_dir=image_dir,
            image_count=image_count,
            engine="pymupdf",
        )

    def _parse_with_magic_pdf(self, *, path: Path, doc_id: str) -> PdfParseResult:
        # magic_pdf 导入很重，必须放到真实使用时再导入，避免拖慢服务启动。
        from magic_pdf.tools.common import do_parse

        output_dir = PARSED_ROOT / doc_id / "magic_pdf"
        pdf_name = path.stem or doc_id
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        do_parse(
            str(output_dir),
            pdf_name,
            path.read_bytes(),
            [],
            "auto",
            debug_able=False,
            f_draw_span_bbox=False,
            f_draw_layout_bbox=False,
            f_dump_md=True,
            f_dump_middle_json=True,
            f_dump_model_json=False,
            f_dump_orig_pdf=False,
            f_dump_content_list=True,
        )

        markdown_path = output_dir / pdf_name / "auto" / f"{pdf_name}.md"
        if not markdown_path.exists():
            markdown_files = list(output_dir.rglob("*.md"))
            if not markdown_files:
                raise FileNotFoundError(f"magic_pdf 未生成 Markdown: {output_dir}")
            markdown_path = max(markdown_files, key=lambda item: item.stat().st_mtime)

        image_dir = markdown_path.parent / "images"
        return PdfParseResult(
            markdown_text=markdown_path.read_text(encoding="utf-8"),
            markdown_path=markdown_path,
            image_dir=image_dir,
            image_count=self._count_images(image_dir),
            engine="magic_pdf",
        )

    @staticmethod
    def _count_images(image_dir: Path) -> int:
        if not image_dir.exists():
            return 0
        return sum(1 for path in image_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


pdf_parser_service = PdfParserService()
