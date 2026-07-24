from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from uyjoy_etl.config import load_config
from uyjoy_etl.data_quality import mark_suspicious_records
from uyjoy_etl.db import Database, mask_secret
from uyjoy_etl.logging_config import configure_logging
from uyjoy_etl.pipeline import OlxRawPipeline
from uyjoy_etl.telegram_cleaner import clean_telegram_real_estate
from uyjoy_etl.telegram_etl import scrape_telegram_channels, telegram_login
from uyjoy_etl.unified_listings import refresh_unified_listings


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UY-JOY core ETL va ML pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate", help="Local schema va BI viewlarni yaratadi")
    subparsers.add_parser("ping-db", help="Postgres connectionni tekshiradi")
    subparsers.add_parser("telegram-login", help="Telegram API session yaratadi")
    subparsers.add_parser(
        "clean-telegram-real-estate",
        help="Telegram raw postlardan clean real-estate fields chiqaradi",
    )
    subparsers.add_parser(
        "mark-suspicious",
        help="Noreal/shubhali e'lonlarni quality_status bilan belgilaydi",
    )
    subparsers.add_parser(
        "refresh-unified-listings",
        help="OLX va Telegram datani bitta real_estate_listings jadvaliga yig'adi",
    )

    train_model_parser = subparsers.add_parser(
        "train-valuation-model",
        help="Oxirgi N kunlik Toshkent kvartira sotuv data bilan modelni qayta o'qitadi",
    )
    train_model_parser.add_argument("--days", type=int, default=30, help="Oxirgi nechta kunlik data bilan train qilish")
    train_model_parser.add_argument("--min-rows", type=int, default=500, help="Train uchun minimum row soni")
    train_model_parser.add_argument("--output", default="", help="Model pickle output yo'li")

    scrape_parser = subparsers.add_parser("scrape", help="OLXdan raw data olib Postgresga yozadi")
    scrape_parser.add_argument("--max-pages", type=int, default=None)
    scrape_parser.add_argument("--limit-categories", type=int, default=None)
    scrape_parser.add_argument(
        "--no-details",
        action="store_true",
        help="Detail sahifalarni ochmaydi, faqat listing JSONini saqlaydi",
    )

    telegram_parser = subparsers.add_parser(
        "scrape-telegram",
        help="Public Telegram kanallardan postlarni olib Postgresga yozadi",
    )
    telegram_parser.add_argument("channels", nargs="+", help="@channel yoki https://t.me/channel ro'yxati")
    telegram_parser.add_argument("--limit", type=int, default=None, help="Har kanal uchun nechta post olinadi")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    configure_logging(config.logs_dir)
    database = Database(config.database)

    logger.info(
        "Config yuklandi | db_host=%s | db_port=%s | db_name=%s | db_user=%s | password=%s",
        config.database.host,
        config.database.port,
        config.database.database,
        config.database.user,
        mask_secret(config.database.password),
    )

    if args.command == "migrate":
        database.ensure_database_exists()
        database.run_schema(config.root_dir / "sql" / "schema.sql")
        database.run_schema(config.root_dir / "sql" / "bi_tashkent_sale_market.sql")
        return 0

    if args.command == "ping-db":
        row = database.ping()
        logger.info(
            "Postgres connection OK | database=%s | user=%s | server_time=%s",
            row["database"],
            row["user"],
            row["server_time"],
        )
        return 0

    if args.command == "telegram-login":
        telegram_login(config)
        return 0

    if args.command == "scrape":
        categories = config.olx.category_paths
        if args.limit_categories:
            categories = categories[: args.limit_categories]
        pipeline = OlxRawPipeline(config=config, database=database)
        pipeline.run(
            category_paths=categories,
            max_pages_per_category=args.max_pages,
            fetch_details=False if args.no_details else None,
        )
        return 0

    if args.command == "scrape-telegram":
        summaries = scrape_telegram_channels(
            config=config,
            database=database,
            channels=args.channels,
            limit=args.limit,
        )
        for summary in summaries:
            print(
                f"channel={summary.channel} "
                f"seen={summary.posts_seen} "
                f"inserted={summary.posts_inserted} "
                f"updated={summary.posts_updated}"
            )
        return 0

    if args.command == "clean-telegram-real-estate":
        summary = clean_telegram_real_estate(database)
        print(f"rows_seen={summary.rows_seen} rows_upserted={summary.rows_upserted}")
        return 0

    if args.command == "mark-suspicious":
        summary = mark_suspicious_records(database)
        print(f"olx_total={summary.olx_total} olx_suspicious={summary.olx_suspicious}")
        print(f"telegram_total={summary.telegram_total} telegram_suspicious={summary.telegram_suspicious}")
        return 0

    if args.command == "refresh-unified-listings":
        summary = refresh_unified_listings(database)
        print(
            f"total_rows={summary.total_rows} "
            f"olx_rows={summary.olx_rows} "
            f"telegram_rows={summary.telegram_rows}"
        )
        return 0

    if args.command == "train-valuation-model":
        from uyjoy_etl.valuation import MODEL_PATH
        from uyjoy_etl.valuation_training import train_apartment_valuation_model

        model_path = Path(args.output) if args.output else MODEL_PATH
        if not model_path.is_absolute():
            model_path = config.root_dir / model_path
        summary = train_apartment_valuation_model(
            database,
            model_path=model_path,
            min_rows=args.min_rows,
            training_window_days=args.days,
        )
        print(summary.to_json())
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
