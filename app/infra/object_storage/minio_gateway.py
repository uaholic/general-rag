from dataclasses import dataclass, field

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

minio_gateway = MinioGateway()
