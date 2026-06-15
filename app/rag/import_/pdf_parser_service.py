"""PDF 解析服务。

默认走 MinerU 远端解析，输出 Markdown 和图片目录。
如果本地调试不想请求 MinerU，可以设置 PDF_PARSE_ENGINE=pymupdf。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
import os
from pathlib import Path
import shutil

import fitz
import requests

from app.infra.config.providers import infra_config
from app.rag.import_.config import MINERU_MODEL_VERSION, MINERU_DOWNLOAD_TIMEOUT_SECONDS, MINERU_POLL_TIMEOUT_SECONDS, \
    MINERU_POLL_INTERVAL_SECONDS
from app.shared.utils.path_util import PROJECT_ROOT
from app.shared.runtime.logger import logger


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

    def upload_pdf_and_poll(self, pdf_path_obj: Path) -> str:
        """
           minerU交互
        :param pdf_path_obj:  上传文件的path对象
        :return: 返回的下载zip地址
        """
        # 1. 校验 MinerU 配置是否完整
        if not infra_config.mineru.base_url or not infra_config.mineru.api_key:
            logger.error(f"minerU请求核心参数为空(base_url 或者 api_key),业务无法继续进行!")
            raise ValueError(f"minerU请求核心参数为空(base_url 或者 api_key),业务无法继续进行!")
        # 2. 调用 `/file-urls/batch` 申请上传地址与 `batch_id`
        token = infra_config.mineru.api_key
        url = f"{infra_config.mineru.base_url}/file-urls/batch"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        data = {
            "files": [
                {"name": f"{pdf_path_obj.name}"}
            ],
            "model_version": MINERU_MODEL_VERSION
        }
        try:
            response = requests.post(url, headers=header, json=data, timeout=MINERU_DOWNLOAD_TIMEOUT_SECONDS)

            # 状态码是否正常200  (网络状态 服务器状态)
            if response.status_code != 200:
                logger.error(f"服务器发生异常!无法进行业务!响应状态码为:{response.status_code}")
                raise RuntimeError(f"服务器发生异常!无法进行业务!响应状态码为:{response.status_code}")
            # 判断业务是否正常0  (业务状态)
            response_dict = response.json()
            code = response_dict.get("code")
            if code != 0:
                logger.error(f"业务处理发生异常! 业务状态码为:{code},异常信息:{response_dict.get('msg')}")
                raise RuntimeError(f"业务处理发生异常! 业务状态码为:{code},异常信息:{response_dict.get('msg')}")

            batch_id = response_dict.get("data", {}).get("batch_id")
            upload_file_url = response_dict.get("data", {}).get("file_urls")[0]
            logger.info(f"调用 `/file-urls/batch` 申请上传地址成功, batch_id:{batch_id}")
        except Exception as e:
            logger.error(f"向minerU申请上传文件地址发生异常: {type(e).__name__}: {e}")
            raise

        # 3. 使用 `Session(trust_env=False)` 上传 PDF 文件
        try:
            with requests.Session() as session:
                # requests.Session() 获取请求会话
                # session使用和requests是一样的
                # 作用1: 可以复用请求 requests.Session() session.get post    session.close() [根本不服用]
                # 作用2: 有些特殊的设置 trust_env = False 我谁也不信!!! 向预签名地址传递数据避免干扰成功率更高!!
                session.trust_env = False
                put_response = session.put(
                    upload_file_url,
                    data=pdf_path_obj.read_bytes(),
                    timeout=MINERU_DOWNLOAD_TIMEOUT_SECONDS,
                )
                # status_code |  code
                if put_response.status_code != 200:
                    logger.error(
                        f"向minerU文件服务器上传文件发生异常,状态码:{put_response.status_code},业务无法继续!!")
                    raise RuntimeError(
                        f"向minerU文件服务器上传文件发生异常,状态码:{put_response.status_code},业务无法继续!!")
        except Exception as e:
            logger.error(f"向minerU文件服务器上传文件发生异常: {type(e).__name__}: {e}")
            raise

        # 4. 根据 `batch_id` 轮询任务状态
        # 前置准备工作
        get_zip_url = f"{infra_config.mineru.base_url}/extract-results/batch/{batch_id}"
        timeout = MINERU_POLL_TIMEOUT_SECONDS  # 600
        interval_time = MINERU_POLL_INTERVAL_SECONDS  # 3
        start_time = time.time()

        while True:
            # 获取结果  抛出异常  timeout
            # 1. 先判定是否超时
            if time.time() - start_time >= timeout:
                logger.error(f"轮询获取:{batch_id}结果超时! 用时:{time.time() - start_time}")
                raise TimeoutError(f"轮询获取:{batch_id}结果超时! 用时:{time.time() - start_time}")
            # 2. 发起网络请求(报错,再给一次机会)
            try:
                get_response = requests.get(
                    get_zip_url,
                    headers=header,
                    timeout=MINERU_DOWNLOAD_TIMEOUT_SECONDS,
                )
            except Exception as e:
                logger.warning(f"获取下载的zipurl地址, 网络请求失败!等待后继续尝试!")
                time.sleep(interval_time)
                continue
            # 3. 判断status_code
            # 客户端 -> 服务端 -> 1 2 3 4 5
            if get_response.status_code != 200:
                # 一定是错误了,看这个错误是否给机会! 5xx
                if 500 <= get_response.status_code < 600:
                    # 给机会
                    logger.warning(
                        f"获取下载的zipurl地址,minerU对应服务器发生异常! 状态码:{get_response.status_code},等待后再次尝试!!")
                    time.sleep(interval_time + 2)
                    continue
                logger.error(
                    f"获取下载的zipurl地址,minerU对应服务器发生异常! 状态码:{get_response.status_code},业务无法继续了!")
                raise RuntimeError(
                    f"获取下载的zipurl地址,minerU对应服务器发生异常! 状态码:{get_response.status_code},业务无法继续了!")

            # 4. 判断code
            get_response_dict = get_response.json()
            if get_response_dict.get('code') != 0:
                logger.error(
                    f"获取下载的zipurl地址,minerU对应服务器发生异常! 业务码:{get_response_dict.get('code')} ,错误信息:"
                    f"{get_response_dict.get('msg')},业务无法继续了!")
                raise RuntimeError(
                    f"获取下载的zipurl地址,minerU对应服务器发生异常! 业务码:{get_response_dict.get('code')} ,错误信息:"
                    f"{get_response_dict.get('msg')},业务无法继续了!")
            # 5. 获取结果信息(是否解析完毕)  正在解析 循环  解析完毕 获取结果 return 解析失败 抛出异常
            # 获取结果的dict
            result_dict = get_response_dict.get("data", {}).get("extract_result", [])[0]
            result_state = result_dict.get("state", "failed")

            if result_state == "done":
                full_zip_url = result_dict.get("full_zip_url")
                if not full_zip_url:
                    # 下载地址空
                    logger.error(
                        f"获取下载的zipurl地址,minerU对应服务器发生异常! 获取zip地址为空!!业务无法继续进行了!")
                    raise RuntimeError(
                        f"获取下载的zipurl地址,minerU对应服务器发生异常! 获取zip地址为空!!业务无法继续进行了!")
                return full_zip_url
            if result_state == "failed":
                # 下载地址空
                logger.error(
                    f"获取下载的zipurl地址,minerU对应服务器发生异常! 解析失败了!!业务无法继续进行了!")
                raise RuntimeError(
                    f"获取下载的zipurl地址,minerU对应服务器发生异常! 解析失败了!!业务无法继续进行了!")
            # 正在解析中.....
            logger.warning(f"{pdf_path_obj.name}minerU正在解析中......")
            time.sleep(interval_time)

    def download_and_extract_markdown(self, zip_url: str, local_dir_path_obj: Path, stem: str) -> Path:
        response = requests.get(zip_url, timeout=MINERU_DOWNLOAD_TIMEOUT_SECONDS)
        if response.status_code != 200:
            logger.error(f"下载minerU解析zip发生异常,状态码:{response.status_code},业务无法继续!!")
            raise RuntimeError(f"下载minerU解析zip发生异常,状态码:{response.status_code},业务无法继续!!")

        zip_path_obj = local_dir_path_obj / f"{stem}_result.zip"
        # 把返回写成zip文件
        zip_path_obj.write_bytes(response.content)

        zip_extract_dir_obj = local_dir_path_obj / stem

        if zip_extract_dir_obj.exists():
            shutil.rmtree(zip_extract_dir_obj)

        zip_extract_dir_obj.mkdir(parents=True, exist_ok=True)
        # 解压
        shutil.unpack_archive(zip_path_obj, zip_extract_dir_obj)
        # 在解压目录中递归查找
        md_file_obj_list = list(zip_extract_dir_obj.rglob("*.md"))
        if not md_file_obj_list or len(md_file_obj_list) == 0:
            logger.error(f"minerU解析zip解压到{zip_extract_dir_obj}目录下没有找到md文件,业务无法继续!!")
            raise RuntimeError(f"minerU解析zip解压到{zip_extract_dir_obj}目录下没有找到md文件,业务无法继续!!")

        for md_file_obj in md_file_obj_list:
            if md_file_obj.stem == stem:
                logger.info(f"解压的文件名为原文件名:{md_file_obj.name}，无需额外处理")
                return md_file_obj

        target_md_obj = None
        for md_file_obj in md_file_obj_list:
            if md_file_obj.name.lower() == "full.md":
                target_md_obj = md_file_obj
                break

        if not target_md_obj:
            target_md_obj = md_file_obj_list[0]
            logger.warning(
                f"minerU解析zip解压到{zip_extract_dir_obj}目录下没有找到{stem}.md文件和full.md文件，默认选择第一个文件:{target_md_obj.name}!!")

        return target_md_obj.rename(target_md_obj.with_name(stem + ".md"))

    def parse_pdf(self, *, pdf_path: str, doc_id: str, engine: str | None = None) -> PdfParseResult:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {path}")

        selected_engine = (engine or os.getenv("PDF_PARSE_ENGINE") or "mineru").lower()
        if selected_engine in {"mineru", "mineru_remote"}:
            return self._parse_with_mineru_remote(path=path, doc_id=doc_id)
        if selected_engine == "magic_pdf":
            return self._parse_with_magic_pdf(path=path, doc_id=doc_id)
        if selected_engine == "pymupdf":
            return self._parse_with_pymupdf(path=path, doc_id=doc_id)
        raise ValueError(f"不支持的 PDF_PARSE_ENGINE: {selected_engine}")

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

    def _parse_with_mineru_remote(self, *, path: Path, doc_id: str) -> PdfParseResult:
        output_dir = PARSED_ROOT / doc_id / "mineru"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        zip_url = self.upload_pdf_and_poll(path)
        markdown_path = self.download_and_extract_markdown(zip_url, output_dir, path.stem)
        if self._count_images(markdown_path.parent) == 0:
            self._append_embedded_images_to_markdown(pdf_path=path, markdown_path=markdown_path)
        image_dir = self._guess_image_dir(markdown_path)
        markdown_text = markdown_path.read_text(encoding="utf-8")
        return PdfParseResult(
            markdown_text=markdown_text,
            markdown_path=markdown_path,
            image_dir=image_dir,
            image_count=self._count_images(markdown_path.parent),
            engine="mineru",
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

    def _append_embedded_images_to_markdown(self, *, pdf_path: Path, markdown_path: Path) -> None:
        image_dir = markdown_path.parent / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_links: list[str] = []
        with fitz.open(pdf_path) as pdf:
            for page_index, page in enumerate(pdf, start=1):
                for image_index, image in enumerate(page.get_images(full=True), start=1):
                    xref = image[0]
                    image_data = pdf.extract_image(xref)
                    image_bytes = image_data.get("image")
                    if not image_bytes:
                        continue
                    extension = image_data.get("ext") or "png"
                    image_name = f"fallback_page_{page_index}_image_{image_index}.{extension}"
                    (image_dir / image_name).write_bytes(image_bytes)
                    image_links.append(f"![第 {page_index} 页图片 {image_index}](images/{image_name})")
        if image_links:
            with markdown_path.open("a", encoding="utf-8") as file:
                file.write("\n\n## PDF 原始图片\n\n")
                file.write("\n\n".join(image_links))
                file.write("\n")

    @staticmethod
    def _guess_image_dir(markdown_path: Path) -> Path:
        image_dir = markdown_path.parent / "images"
        if image_dir.exists():
            return image_dir
        for path in markdown_path.parent.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                return path.parent
        return image_dir

    @staticmethod
    def _count_images(image_dir: Path) -> int:
        if not image_dir.exists():
            return 0
        return sum(1 for path in image_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


pdf_parser_service = PdfParserService()
