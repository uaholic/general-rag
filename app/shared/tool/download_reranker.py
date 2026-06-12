"""
工具脚本，用于处理 download reranker 相关的辅助任务。
"""
from modelscope.hub.snapshot_download import snapshot_download

from app.shared.config.reranker_config import reranker_config


def main():
    local_dir = reranker_config.bge_reranker_large
    snapshot_download(
        model_id="BAAI/bge-reranker-large",
        cache_dir=local_dir,
    )
    print("下载完成，模型目录：", local_dir)


if __name__ == "__main__":
    main()
