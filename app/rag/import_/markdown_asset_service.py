"""Markdown 图片资源处理。

生产环境里，服务器无法读取用户电脑上的 `./images/a.png` 或
`/Users/me/Desktop/a.png`。正确做法是让用户把 Markdown 和资源文件一起上传，
例如 zip 包或目录上传，然后服务端解压/保存/上传对象存储，并重写 Markdown 图片地址。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from urllib.parse import urlparse


MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")
HTML_IMAGE_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)


@dataclass(frozen=True)
class MarkdownImageRef:
    src: str
    kind: str
    exists_on_server: bool
    note: str


class MarkdownAssetService:
    """识别 Markdown 中的图片引用，后续可扩展为资源归档处理。"""

    def inspect(self, *, markdown_text: str, markdown_path: str) -> dict:
        base_dir = Path(markdown_path).parent
        refs = [self._classify(src.strip(), base_dir) for src in self._extract_sources(markdown_text)]
        warnings = [ref.note for ref in refs if ref.note]
        return {
            "markdown_image_refs": [asdict(ref) for ref in refs],
            "asset_warnings": warnings,
        }

    def _extract_sources(self, markdown_text: str) -> list[str]:
        sources = [match.group(1) for match in MARKDOWN_IMAGE_RE.finditer(markdown_text)]
        sources.extend(match.group(1) for match in HTML_IMAGE_RE.finditer(markdown_text))
        return list(dict.fromkeys(sources))

    def _classify(self, src: str, base_dir: Path) -> MarkdownImageRef:
        parsed = urlparse(src)
        if parsed.scheme in {"http", "https"}:
            return MarkdownImageRef(src=src, kind="remote", exists_on_server=False, note="")
        if parsed.scheme == "data":
            return MarkdownImageRef(src=src[:80], kind="data_uri", exists_on_server=False, note="发现 base64 图片，后续可抽取为对象存储文件")
        if parsed.scheme == "file":
            return MarkdownImageRef(src=src, kind="local_file_uri", exists_on_server=False, note="file:// 图片路径只在用户本机有效，服务器无法读取")

        candidate = Path(src)
        resolved = candidate if candidate.is_absolute() else base_dir / candidate
        exists = resolved.exists()
        note = "" if exists else f"本地图片未随 Markdown 上传，服务器无法解析：{src}"
        return MarkdownImageRef(src=src, kind="local_relative" if not candidate.is_absolute() else "local_absolute", exists_on_server=exists, note=note)


markdown_asset_service = MarkdownAssetService()
