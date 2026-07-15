from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from uyjoy_etl.category_catalog import category_by_path
from uyjoy_etl.cloud_export import export_cloud_csv, import_cloud_csv
from uyjoy_etl.config import load_config
from uyjoy_etl.contact_import import import_contacts_csv
from uyjoy_etl.db import Database, mask_secret
from uyjoy_etl.logging_config import configure_logging
from uyjoy_etl.pipeline import OlxRawPipeline
from uyjoy_etl.source_discovery import discover_sources, inspect_listing_source

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OLX.uz raw real-estate ETL")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate", help="Database yaratadi va schema.sql ni ishlatadi")
    subparsers.add_parser("migrate-cloud", help="Cloud uchun yengil schema_cloud.sql ni ishlatadi")
    subparsers.add_parser("ping-db", help="Postgres connectionni tekshiradi")
    subparsers.add_parser("categories", help="Configdagi category pathlarni chiqaradi")

    export_cloud_parser = subparsers.add_parser(
        "export-cloud-csv",
        help="Doimiy free DB uchun yengil warehouse CSV export qiladi",
    )
    export_cloud_parser.add_argument(
        "csv_path",
        nargs="?",
        default="backups/uyjoy-cloud-listings.csv",
    )

    import_cloud_parser = subparsers.add_parser(
        "import-cloud-csv",
        help="Yengil warehouse CSV faylini cloud Postgresga import qiladi",
    )
    import_cloud_parser.add_argument(
        "csv_path",
        nargs="?",
        default="backups/uyjoy-cloud-listings.csv",
    )

    inspect_parser = subparsers.add_parser(
        "inspect-source",
        help="Bitta OLX source pathdagi pagination va facetlarni ko'rsatadi",
    )
    inspect_parser.add_argument("path", nargs="?", default=None)

    scrape_parser = subparsers.add_parser("scrape", help="OLXdan raw data olib Postgresga yozadi")
    scrape_parser.add_argument("--max-pages", type=int, default=None)
    scrape_parser.add_argument("--limit-categories", type=int, default=None)
    scrape_parser.add_argument(
        "--no-details",
        action="store_true",
        help="Detail sahifalarni ochmaydi, faqat listing JSONini saqlaydi",
    )

    discover_parser = subparsers.add_parser(
        "discover-sources",
        help="OLX categorylardan region/city/district source URLlarni topadi",
    )
    discover_parser.add_argument("--limit-categories", type=int, default=None)
    discover_parser.add_argument("--max-visible", type=int, default=1000)
    discover_parser.add_argument("--with-room-market-splits", action="store_true")

    scrape_discovered_parser = subparsers.add_parser(
        "scrape-discovered",
        help="Avval source URLlarni topib, keyin hammasini scrape qiladi",
    )
    scrape_discovered_parser.add_argument("--limit-categories", type=int, default=None)
    scrape_discovered_parser.add_argument("--max-sources", type=int, default=None)
    scrape_discovered_parser.add_argument("--max-pages", type=int, default=25)
    scrape_discovered_parser.add_argument("--max-visible", type=int, default=1000)
    scrape_discovered_parser.add_argument("--with-room-market-splits", action="store_true")

    contacts_parser = subparsers.add_parser(
        "import-contacts",
        help="Ruxsatli CSV/export contactlarini e'lon rowlariga ulaydi",
    )
    contacts_parser.add_argument("csv_path", help="olx_id/listing_url va phone ustunlari bor CSV")
    contacts_parser.add_argument("--source", default="authorized_csv", help="Contact manbasi nomi")

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
        return 0

    if args.command == "migrate-cloud":
        database.ensure_database_exists()
        database.run_schema(config.root_dir / "sql" / "schema_cloud.sql")
        return 0

    if args.command == "export-cloud-csv":
        csv_path = Path(args.csv_path)
        if not csv_path.is_absolute():
            csv_path = config.root_dir / csv_path
        total = export_cloud_csv(database, csv_path)
        logger.info("Cloud CSV export tayyor | rows=%s | path=%s", total, csv_path)
        print(f"cloud_csv={csv_path}")
        print(f"rows={total}")
        return 0

    if args.command == "import-cloud-csv":
        csv_path = Path(args.csv_path)
        if not csv_path.is_absolute():
            csv_path = config.root_dir / csv_path
        total = import_cloud_csv(database, config.root_dir / "sql" / "schema_cloud.sql", csv_path)
        logger.info("Cloud CSV import tugadi | rows=%s | path=%s", total, csv_path)
        print(f"imported_rows={total}")
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

    if args.command == "categories":
        for category_path in config.olx.category_paths:
            category = category_by_path(category_path)
            if category:
                print(
                    f"{category.olx_category_id} | {category.name} | "
                    f"{category.property_group} | {category.deal_type} | {category.path}"
                )
            else:
                print(category_path)
        return 0

    if args.command == "inspect-source":
        listing_path = args.path or config.olx.category_paths[0]
        inspection = inspect_listing_source(config, listing_path)
        print(f"url: {inspection.url}")
        print(f"ads_on_page: {inspection.ads_count}")
        print(f"total_pages: {inspection.total_pages}")
        print(f"total_elements: {inspection.total_elements}")
        print(f"visible_elements: {inspection.visible_elements}")
        for facet_name, items in inspection.facets.items():
            print(f"facet: {facet_name} | items: {len(items)}")
            for item in items[:20]:
                print(f"  {item.get('id')} | {item.get('count')} | {item.get('label')} | {item.get('url')}")
        return 0

    if args.command == "discover-sources":
        categories = config.olx.category_paths
        if args.limit_categories:
            categories = categories[: args.limit_categories]
        sources = discover_sources(
            config=config,
            root_paths=categories,
            max_visible_per_source=args.max_visible,
            include_room_market_splits=args.with_room_market_splits,
        )
        print(f"discovered_sources={len(sources)}")
        for source in sources:
            print(
                f"{source.visible_elements:>6} | pages={source.total_pages:>2} | "
                f"level={source.split_level} | {source.path}"
            )
        return 0

    if args.command == "scrape-discovered":
        categories = config.olx.category_paths
        if args.limit_categories:
            categories = categories[: args.limit_categories]
        sources = discover_sources(
            config=config,
            root_paths=categories,
            max_visible_per_source=args.max_visible,
            include_room_market_splits=args.with_room_market_splits,
        )
        if args.max_sources:
            sources = sources[: args.max_sources]
        source_paths = tuple(source.path for source in sources)
        logger.info("Discovered source scrape boshlanadi | sources=%s", len(source_paths))
        pipeline = OlxRawPipeline(config=config, database=database)
        pipeline.run(
            category_paths=source_paths,
            max_pages_per_category=args.max_pages,
            fetch_details=False,
        )
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

    if args.command == "import-contacts":
        summary = import_contacts_csv(
            database=database,
            csv_path=Path(args.csv_path),
            source=args.source,
        )
        logger.info(
            "Contact import tugadi | rows_seen=%s | rows_updated=%s | rows_skipped=%s",
            summary.rows_seen,
            summary.rows_updated,
            summary.rows_skipped,
        )
        print(
            f"rows_seen={summary.rows_seen} "
            f"rows_updated={summary.rows_updated} "
            f"rows_skipped={summary.rows_skipped}"
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
