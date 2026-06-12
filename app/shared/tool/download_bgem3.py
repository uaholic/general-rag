"""
工具脚本，用于处理 download bgem3 相关的辅助任务。
"""
from modelscope.hub.snapshot_download import snapshot_download

from app.shared.config.embedding_config import embedding_config


def main():
    model_dir = snapshot_download("BAAI/bge-m3", cache_dir=embedding_config.bge_m3_path)
    print(f"模型已下载到: {model_dir}")


if __name__ == "__main__":
    main()
