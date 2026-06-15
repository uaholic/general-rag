from app.infra.config.providers import infra_config


class LLMProvider:

    def chat(self, model_name: str = None, json_mode: bool = False):
        from app.shared.model.lm_utils import get_llm_client

        return get_llm_client(model_name, json_mode)

    def vision_chat(self, model_name: str | None = None):
        from app.shared.model.lm_utils import get_llm_client

        return get_llm_client(model_name or infra_config.llm.lv_model or "qwen-vl-flash")

    def embedding_model(self):
        from app.shared.model.embedding_utils import get_bge_m3_ef

        return get_bge_m3_ef()

    def embedding_mode(self):
        return self.embedding_model()

    def embed_documents(self, documents: list[str]) -> dict[str, list]:
        """
            {
               dense: [[],[]],
               sparse: [{},{}]
            }
        :param documents:
        :return:
        """
        from app.shared.model.embedding_utils import generate_embeddings

        return generate_embeddings(documents)

    def reranker_model(self):
        from app.shared.model.reranker_utils import get_reranker_model

        return get_reranker_model()


llm_provider = LLMProvider()
