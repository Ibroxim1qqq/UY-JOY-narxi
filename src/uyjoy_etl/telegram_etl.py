from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb
from telethon import TelegramClient
from telethon.tl.custom.message import Message

from uyjoy_etl.config import AppConfig
from uyjoy_etl.db import Database

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramScrapeSummary:
    channel: str
    posts_seen: int
    posts_inserted: int
    posts_updated: int


def ensure_telegram_config(config: AppConfig) -> None:
    """Telegram API kalitlari borligini tekshiradi."""

    if not config.telegram.api_id or not config.telegram.api_hash:
        raise ValueError("TELEGRAM_API_ID va TELEGRAM_API_HASH .env ichida bo'lishi kerak")


def telegram_session_path(config: AppConfig) -> str:
    """Session faylini loyiha ichidagi xavfsiz `secrets/` papkaga yo'naltiradi."""

    session_name = config.telegram.session_name
    session_path = Path(session_name)
    if not session_path.is_absolute():
        session_path = config.root_dir / session_path
    session_path.parent.mkdir(parents=True, exist_ok=True)
    return str(session_path)


def telegram_login(config: AppConfig) -> None:
    """Birinchi marta Telegram session yaratadi; kod terminalda so'raladi."""

    ensure_telegram_config(config)

    async def _login() -> None:
        async with TelegramClient(
            telegram_session_path(config),
            config.telegram.api_id,
            config.telegram.api_hash,
        ) as client:
            me = await client.get_me()
            logger.info("Telegram login OK | user_id=%s | username=%s", me.id, me.username)
            print(f"telegram_login_ok user_id={me.id} username={me.username}")

    asyncio.run(_login())


def scrape_telegram_channels(
    config: AppConfig,
    database: Database,
    channels: list[str],
    limit: int | None = None,
) -> list[TelegramScrapeSummary]:
    """Berilgan public Telegram kanallardan postlarni olib Postgresga yozadi."""

    ensure_telegram_config(config)
    effective_limit = limit or config.telegram.default_limit

    async def _scrape() -> list[TelegramScrapeSummary]:
        async with TelegramClient(
            telegram_session_path(config),
            config.telegram.api_id,
            config.telegram.api_hash,
        ) as client:
            summaries: list[TelegramScrapeSummary] = []
            for channel in channels:
                entity = await client.get_entity(channel)
                channel_record = _channel_record(entity, channel)
                upsert_telegram_channel(database, channel_record)

                inserted = 0
                updated = 0
                seen = 0
                async for message in client.iter_messages(entity, limit=effective_limit):
                    if not message:
                        continue
                    seen += 1
                    action = upsert_telegram_post(
                        database,
                        _post_record(entity, message),
                    )
                    if action == "inserted":
                        inserted += 1
                    else:
                        updated += 1

                summaries.append(
                    TelegramScrapeSummary(
                        channel=channel,
                        posts_seen=seen,
                        posts_inserted=inserted,
                        posts_updated=updated,
                    )
                )
                logger.info(
                    "Telegram channel scrape tugadi | channel=%s | seen=%s | inserted=%s | updated=%s",
                    channel,
                    seen,
                    inserted,
                    updated,
                )
            return summaries

    return asyncio.run(_scrape())


def upsert_telegram_channel(database: Database, record: dict[str, Any]) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            insert into telegram_channels (
                channel_id, username, title, channel_url, raw_channel, first_seen_at, last_seen_at, updated_at
            )
            values (
                %(channel_id)s, %(username)s, %(title)s, %(channel_url)s, %(raw_channel)s, now(), now(), now()
            )
            on conflict (channel_id) do update
            set username = excluded.username,
                title = excluded.title,
                channel_url = excluded.channel_url,
                raw_channel = excluded.raw_channel,
                last_seen_at = now(),
                updated_at = now()
            """,
            {**record, "raw_channel": Jsonb(record["raw_channel"])},
        )
        conn.commit()


def upsert_telegram_post(database: Database, record: dict[str, Any]) -> str:
    with database.connect() as conn:
        row = conn.execute(
            """
            insert into telegram_posts (
                channel_id, message_id, channel_username, channel_title, post_url,
                posted_at, text, views, forwards, replies_count, has_media, media_type,
                raw_message, first_seen_at, updated_at
            )
            values (
                %(channel_id)s, %(message_id)s, %(channel_username)s, %(channel_title)s, %(post_url)s,
                %(posted_at)s, %(text)s, %(views)s, %(forwards)s, %(replies_count)s, %(has_media)s,
                %(media_type)s, %(raw_message)s, now(), now()
            )
            on conflict (channel_id, message_id) do update
            set channel_username = excluded.channel_username,
                channel_title = excluded.channel_title,
                post_url = excluded.post_url,
                posted_at = excluded.posted_at,
                text = excluded.text,
                views = excluded.views,
                forwards = excluded.forwards,
                replies_count = excluded.replies_count,
                has_media = excluded.has_media,
                media_type = excluded.media_type,
                raw_message = excluded.raw_message,
                updated_at = now()
            returning case when xmax = 0 then 'inserted' else 'updated' end as action
            """,
            {**record, "raw_message": Jsonb(record["raw_message"])},
        ).fetchone()
        conn.commit()
    return str(row["action"])


def _channel_record(entity: Any, source: str) -> dict[str, Any]:
    username = getattr(entity, "username", None)
    title = getattr(entity, "title", None)
    return {
        "channel_id": int(entity.id),
        "username": username,
        "title": title,
        "channel_url": _channel_url(username, source),
        "raw_channel": _safe_json(entity.to_dict()),
    }


def _post_record(entity: Any, message: Message) -> dict[str, Any]:
    username = getattr(entity, "username", None)
    return {
        "channel_id": int(entity.id),
        "message_id": int(message.id),
        "channel_username": username,
        "channel_title": getattr(entity, "title", None),
        "post_url": _post_url(username, message.id),
        "posted_at": message.date,
        "text": message.message,
        "views": message.views,
        "forwards": message.forwards,
        "replies_count": _replies_count(message),
        "has_media": message.media is not None,
        "media_type": type(message.media).__name__ if message.media else None,
        "raw_message": _safe_json(message.to_dict()),
    }


def _channel_url(username: str | None, source: str) -> str | None:
    if username:
        return f"https://t.me/{username}"
    if source.startswith("https://t.me/"):
        return source
    if source.startswith("@"):
        return f"https://t.me/{source[1:]}"
    return None


def _post_url(username: str | None, message_id: int) -> str | None:
    if not username:
        return None
    return f"https://t.me/{username}/{message_id}"


def _replies_count(message: Message) -> int | None:
    replies = getattr(message, "replies", None)
    if not replies:
        return None
    return getattr(replies, "replies", None)


def _safe_json(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default, ensure_ascii=False))


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
