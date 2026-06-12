"""
MongoDB chat history helpers.

The module keeps connection creation lazy so importing repository or agent
modules does not require MongoDB to be available.
"""
from datetime import datetime, timezone
import os
from typing import Any

from bson import ObjectId
from pymongo import MongoClient

from app.shared.runtime.logger import logger


class HistoryMongoTool:
    """MongoDB access object for chat sessions and messages."""

    def __init__(self):
        self.mongo_url = os.getenv("MONGO_URL")
        self.db_name = os.getenv("MONGO_DB_NAME")
        if not self.mongo_url:
            raise RuntimeError("缺少 MONGO_URL 环境变量配置")
        if not self.db_name:
            raise RuntimeError("缺少 MONGO_DB_NAME 环境变量配置")

        self.client = MongoClient(self.mongo_url)
        self.db = self.client[self.db_name]
        self.chat_sessions = self.db["chat_sessions"]
        self.chat_messages = self.db["chat_messages"]

        self.chat_sessions.create_index([("session_id", 1)], unique=True)
        self.chat_sessions.create_index([("updated_at", -1)])
        self.chat_messages.create_index([("session_id", 1), ("ts", -1)])
        logger.info(f"Successfully connected to MongoDB: {self.db_name}")


_history_mongo_tool: HistoryMongoTool | None = None


def get_history_mongo_tool() -> HistoryMongoTool:
    """Return the lazy singleton Mongo helper."""
    global _history_mongo_tool
    if _history_mongo_tool is None:
        _history_mongo_tool = HistoryMongoTool()
    return _history_mongo_tool


def _utc_now() -> tuple[float, str]:
    now = datetime.now(timezone.utc)
    return now.timestamp(), now.isoformat()


def clear_history(session_id: str) -> int:
    """Clear all messages for a session."""
    mongo_tool = get_history_mongo_tool()
    try:
        result = mongo_tool.chat_messages.delete_many({"session_id": session_id})
        mongo_tool.chat_sessions.update_one(
            {"session_id": session_id},
            {"$set": {"message_count": 0, "last_message": ""}},
        )
        logger.info(f"Deleted {result.deleted_count} messages for session {session_id}")
        return result.deleted_count
    except Exception as e:
        logger.error(f"Error clearing history for session {session_id}: {e}")
        return 0


def save_chat_message(
    session_id: str,
    role: str,
    content: str | None = None,
    *,
    text: str | None = None,
    rewritten_query: str = "",
    subject_names: list[str] | None = None,
    image_urls: list[str] | None = None,
    references: list[dict[str, Any]] | None = None,
    company_id: str = "default_company",
    business_line_id: str = "",
    message_id: str | None = None,
) -> str:
    """
    Insert or update one chat message.

    `text` is accepted as a backward-compatible alias while the project-facing
    field is `content`.
    """
    message_content = content if content is not None else text
    if message_content is None:
        raise ValueError("content 不能为空")

    ts, created_at = _utc_now()
    document = {
        "session_id": session_id,
        "company_id": company_id,
        "business_line_id": business_line_id,
        "role": role,
        "content": message_content,
        "rewritten_query": rewritten_query or "",
        "subject_names": subject_names or [],
        "image_urls": image_urls or [],
        "references": references or [],
        "ts": ts,
        "created_at": created_at,
    }

    mongo_tool = get_history_mongo_tool()
    if message_id:
        mongo_tool.chat_messages.update_one(
            {"_id": ObjectId(message_id)},
            {"$set": document},
        )
        saved_id = message_id
    else:
        result = mongo_tool.chat_messages.insert_one(document)
        saved_id = str(result.inserted_id)

    mongo_tool.chat_sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "session_id": session_id,
                "company_id": company_id,
                "business_line_id": business_line_id,
                "updated_at": created_at,
                "last_message": message_content,
                "subject_names": subject_names or [],
            },
            "$inc": {"message_count": 0 if message_id else 1},
            "$setOnInsert": {"created_at": created_at},
        },
        upsert=True,
    )
    return saved_id


def update_message_subject_names(ids: list[str], subject_names: list[str]) -> int:
    """Bulk update subject names for selected chat messages."""
    mongo_tool = get_history_mongo_tool()
    try:
        object_ids = [ObjectId(i) for i in ids]
        result = mongo_tool.chat_messages.update_many(
            {"_id": {"$in": object_ids}},
            {"$set": {"subject_names": subject_names}},
        )
        logger.info(f"Updated {result.modified_count} records to subject_names: {subject_names}")
        return result.modified_count
    except Exception as e:
        logger.error(f"Error updating history subject_names: {e}")
        return 0


def get_recent_messages(session_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Query recent messages for one session, returned in chronological order."""
    mongo_tool = get_history_mongo_tool()
    try:
        cursor = mongo_tool.chat_messages.find({"session_id": session_id}).sort("ts", -1).limit(limit)
        messages = list(cursor)
        messages.reverse()
        return messages
    except Exception as e:
        logger.error(f"Error getting recent messages: {e}")
        return []
