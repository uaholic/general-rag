from dataclasses import dataclass, field
import mimetypes
from pathlib import Path
import re
from urllib.parse import quote

from minio import Minio

from app.infra.config.providers import infra_config
from app.shared.clients.minio_utils import get_minio_client


@dataclass
class MinioGateway:

    bucket_name: str = infra_config.minio.bucket_name

    image_dir: str = infra_config.minio.minio_img_dir

    _client: Minio | None = field(default=None, init=False, repr=False)

    @property
    def client(self) -> Minio:
        if self._client is None:
            self._client = get_minio_client()
        return self._client

    def build_image_url(self, stem: str, object_name: str):
        protocol = "https" if infra_config.minio.minio_secure else "http"
        image_dir = self.image_dir.strip("/")
        image_prefix = f"/{image_dir}" if image_dir else ""

        return (
            f"{protocol}://{infra_config.minio.endpoint}/{self.bucket_name}"
            f"{image_prefix}/{stem}/{object_name}"
        )

    def upload_dir_name(self, filename: str) -> str:
        """按原始文件名生成 MinIO 二级目录名。"""
        name = Path(filename or "unnamed").name.strip() or "unnamed"
        return re.sub(r'[\x00-\x1f\\/:*?"<>|]+', "_", name).strip(" .") or "unnamed"

    def object_prefix(self, filename: str) -> str:
        image_dir = self.image_dir.strip("/")
        dir_name = self.upload_dir_name(filename)
        return f"{image_dir}/{dir_name}".strip("/")

    def object_name_for(self, *, filename: str, relative_name: str) -> str:
        clean_relative = relative_name.strip().lstrip("/").replace("\\", "/")
        if not clean_relative:
            clean_relative = Path(filename or "unnamed").name
        return f"{self.object_prefix(filename)}/{clean_relative}".strip("/")

    def clear_file_dir(self, filename: str) -> int:
        """清空同名文件目录，避免重复上传留下旧文件。"""
        prefix = f"{self.object_prefix(filename).rstrip('/')}/"
        removed = 0
        for obj in self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True):
            self.client.remove_object(self.bucket_name, obj.object_name)
            removed += 1
        return removed

    def upload_file(self, *, local_path: str | Path, filename: str, relative_name: str = "") -> str:
        """上传本地文件到当前文件名目录下，返回可访问 URL。"""
        path = Path(local_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"待上传文件不存在: {path}")

        object_name = self.object_name_for(
            filename=filename,
            relative_name=relative_name or path.name,
        )
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.client.fput_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
            file_path=str(path),
            content_type=content_type,
        )
        return self.public_url(object_name)

    def public_url(self, object_name: str) -> str:
        protocol = "https" if infra_config.minio.minio_secure else "http"
        quoted_object = quote(object_name.strip("/"), safe="/")
        return f"{protocol}://{infra_config.minio.endpoint}/{self.bucket_name}/{quoted_object}"

minio_gateway = MinioGateway()
