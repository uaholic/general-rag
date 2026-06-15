from pymilvus import AnnSearchRequest

from app.infra.config.providers import infra_config
from app.shared.clients.milvus_utils import get_milvus_client, create_hybrid_search_requests, hybrid_search
from app.shared.runtime.logger import logger


class MilvusGateway:
    _resolved_chunk_collection_name: str | None = None
    _required_chunk_fields = {
        "chunk_id",
        "kb_id",
        "doc_id",
        "filename",
        "content",
        "dense_vector",
        "sparse_vector",
    }

    @property
    def subject_collection_name(self):
        return infra_config.milvus.subject_collection

    @property
    def chunk_collection_name(self):
        if self._resolved_chunk_collection_name:
            return self._resolved_chunk_collection_name

        configured_name = infra_config.milvus.chunks_collection
        try:
            if self.client.has_collection(configured_name):
                fields = {
                    field.get("name")
                    for field in self.client.describe_collection(configured_name).get("fields", [])
                }
                missing_fields = self._required_chunk_fields - fields
                if missing_fields:
                    fallback_name = f"{configured_name}_rag"
                    logger.warning(
                        f"Milvus集合 {configured_name} 缺少字段 {sorted(missing_fields)}，"
                        f"自动切换到 {fallback_name}"
                    )
                    self._resolved_chunk_collection_name = fallback_name
                    return fallback_name
        except Exception:
            logger.exception(f"检查Milvus集合 {configured_name} schema失败，暂按配置集合名继续")

        self._resolved_chunk_collection_name = configured_name
        return configured_name

    @property
    def client(self):
        return get_milvus_client()

    # 新引入
    def create_requests(
            self,
            dense_vector: list[float],
            sparse_vector: dict[int, float],
            *,
            expr: str = None,
            limit: int = 5,
    ):
        return create_hybrid_search_requests(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            expr=expr,
            limit=limit,
        )

    def hybrid_search(
            self,
            *,
            collection_name: str,
            reqs: list[AnnSearchRequest],
            ranker_weights: tuple[float, float] = (0.5, 0.5),
            norm_score: bool = False,
            limit: int = 5,
            output_fields: list[str] | None = None,
            search_params: dict | None = None,
    ):
        return hybrid_search(
            client=self.client,
            collection_name=collection_name,
            reqs=reqs,
            ranker_weights=ranker_weights,
            norm_score=norm_score,
            limit=limit,
            output_fields=output_fields,
            search_params=search_params,
        )

milvus_gateway = MilvusGateway()
