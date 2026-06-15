"""Milvus 存量 chunk 主体词回填服务。"""
from __future__ import annotations

import json
from typing import Any

from app.infra.vectorstore.milvus_gateway import milvus_gateway
from app.rag.import_.document_import_service import document_import_service
from app.rag.import_.vector_writer import vector_write_service
from app.shared.runtime.logger import logger


class SubjectBackfillService:
    """给旧导入数据补齐 subject_names，避免必须整篇重新解析。"""

    def backfill_empty_subjects(
        self,
        *,
        limit: int = 1000,
        batch_size: int = 64,
        use_llm: bool = True,
        only_empty: bool = True,
        dry_run: bool = False,
    ) -> dict[str, int]:
        collection_name = milvus_gateway.chunk_collection_name
        client = milvus_gateway.client
        if not client.has_collection(collection_name):
            return {"matched": 0, "updated": 0}

        rows = client.query(
            collection_name=collection_name,
            filter='subject_names == "[]" or subject_names == ""' if only_empty else 'chunk_id != ""',
            output_fields=[
                "chunk_id",
                "kb_id",
                "doc_id",
                "filename",
                "title",
                "title_path",
                "content",
                "chunk_index",
                "subject_names",
                "image_urls",
                "dense_vector",
                "sparse_vector",
            ],
            limit=limit,
        )
        if not rows:
            return {"matched": 0, "updated": 0}

        updated = 0
        safe_batch_size = max(1, batch_size)
        for start in range(0, len(rows), safe_batch_size):
            batch_rows = rows[start:start + safe_batch_size]
            updated_rows = self._build_updated_rows(batch_rows, use_llm=use_llm)
            if not dry_run and updated_rows:
                vector_write_service.upsert_chunks(updated_rows)
            updated += len(updated_rows)
            logger.info(
                f"Milvus主体词回填进度：{min(start + safe_batch_size, len(rows))}/{len(rows)} "
                f"updated={updated} use_llm={use_llm} only_empty={only_empty} dry_run={dry_run}"
            )

        logger.info(f"Milvus主体词回填完成：matched={len(rows)} updated={updated} only_empty={only_empty} dry_run={dry_run}")
        return {"matched": len(rows), "updated": updated}

    def _build_updated_rows(self, rows: list[dict[str, Any]], *, use_llm: bool) -> list[dict[str, Any]]:
        subject_map = self._subject_map(rows, use_llm=use_llm)
        updated_rows: list[dict[str, Any]] = []
        for row in rows:
            subjects = subject_map.get(row.get("chunk_id", "")) or []
            if not subjects:
                continue
            updated_rows.append(
                {
                    "chunk_id": row.get("chunk_id", ""),
                    "kb_id": row.get("kb_id", ""),
                    "doc_id": row.get("doc_id", ""),
                    "filename": row.get("filename", ""),
                    "title": row.get("title", ""),
                    "title_path": row.get("title_path", ""),
                    "content": row.get("content", ""),
                    "chunk_index": row.get("chunk_index") or 0,
                    "subject_names": subjects,
                    "image_urls": self._parse_json_list(row.get("image_urls")),
                    "dense_vector": row.get("dense_vector") or [],
                    "sparse_vector": row.get("sparse_vector") or {},
                }
            )
        return updated_rows

    @staticmethod
    def _subject_map(rows: list[dict[str, Any]], *, use_llm: bool) -> dict[str, list[str]]:
        chunks = [
            {
                "chunk_id": row.get("chunk_id", ""),
                "content": row.get("content", ""),
            }
            for row in rows
        ]
        if use_llm:
            return {
                chunk["chunk_id"]: chunk.get("subject_names") or []
                for chunk in document_import_service.recognize_chunk_subjects(chunks)
            }
        return {
            chunk["chunk_id"]: document_import_service._fallback_subjects(chunk.get("content", ""))
            for chunk in chunks
        }

    @staticmethod
    def _parse_json_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if not value:
            return []
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [item.strip() for item in value.split(",") if item.strip()]
            return [str(item) for item in parsed if item] if isinstance(parsed, list) else []
        return []


subject_backfill_service = SubjectBackfillService()
