from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from uyjoy_etl.config import load_config
from uyjoy_etl.db import Database
from uyjoy_etl.logging_config import configure_logging
from uyjoy_etl.pipeline import OlxRawPipeline
from uyjoy_etl.source_discovery import DiscoveredSource, discover_sources


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Barcha public OLX real-estate source'larini scrape qiladi")
    parser.add_argument("--max-pages", type=int, default=25)
    parser.add_argument("--max-visible", type=int, default=1000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = load_config()
    configure_logging(config.logs_dir)
    database = Database(config.database)
    database.ensure_database_exists()
    database.run_schema(config.root_dir / "sql" / "schema.sql")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sources_file = config.logs_dir / f"full_public_sources_{timestamp}.txt"
    progress_file = config.logs_dir / "full_public_scrape_progress.txt"

    def db_count() -> int:
        with database.connect() as conn:
            return int(conn.execute("select count(*) as total from olx_listing_raw").fetchone()["total"])

    def append_progress(message: str) -> None:
        line = f"{datetime.now().isoformat(timespec='seconds')} | {message}"
        print(line, flush=True)
        with progress_file.open("a", encoding="utf-8") as file:
            file.write(line + "\n")

    before_total = db_count()
    append_progress(
        f"FULL PUBLIC SCRAPE START | before_total={before_total} | "
        f"max_pages={args.max_pages} | categories={len(config.olx.category_paths)}"
    )

    pipeline = OlxRawPipeline(config=config, database=database)
    all_sources: list[str] = []

    for category_path in config.olx.category_paths:
        append_progress(f"DISCOVERY START | category={category_path}")
        sources = discover_sources(
            config=config,
            root_paths=(category_path,),
            max_visible_per_source=args.max_visible,
            include_room_market_splits=True,
        )
        source_paths = tuple(source.path for source in sources)
        all_sources.extend(source_paths)
        _append_sources_file(sources_file, category_path, sources)
        append_progress(f"DISCOVERY DONE | category={category_path} | sources={len(source_paths)}")

        if not source_paths:
            continue

        category_before = db_count()
        append_progress(
            f"SCRAPE START | category={category_path} | sources={len(source_paths)} | before={category_before}"
        )
        pipeline.run(
            category_paths=source_paths,
            max_pages_per_category=args.max_pages,
            fetch_details=False,
        )
        category_after = db_count()
        append_progress(
            f"SCRAPE DONE | category={category_path} | "
            f"after={category_after} | added={category_after - category_before}"
        )

    after_total = db_count()
    append_progress(
        f"FULL PUBLIC SCRAPE DONE | categories={len(config.olx.category_paths)} | "
        f"sources={len(all_sources)} | before_total={before_total} | after_total={after_total} | "
        f"added={after_total - before_total} | sources_file={sources_file}"
    )
    return 0


def _append_sources_file(
    sources_file: Path,
    category_path: str,
    sources: list[DiscoveredSource],
) -> None:
    with sources_file.open("a", encoding="utf-8") as file:
        file.write(f"# {category_path} | sources={len(sources)}\n")
        for source in sources:
            file.write(
                f"{source.visible_elements:>8} | pages={source.total_pages:>2} | "
                f"level={source.split_level} | {source.path}\n"
            )


if __name__ == "__main__":
    raise SystemExit(main())
