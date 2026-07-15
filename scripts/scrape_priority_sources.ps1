$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

& (Join-Path $PSScriptRoot "start_local_postgres.ps1")

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    py -m venv .venv
}

$python = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $root "src"

$code = @'
from uyjoy_etl.config import load_config
from uyjoy_etl.db import Database
from uyjoy_etl.logging_config import configure_logging
from uyjoy_etl.pipeline import OlxRawPipeline

config = load_config()
configure_logging(config.logs_dir)
database = Database(config.database)
database.ensure_database_exists()
database.run_schema(config.root_dir / "sql" / "schema.sql")

priority_sources = (
    "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=12",
    "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=25",
    "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=22",
    "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=26",
    "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=13",
    "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=23",
    "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=19",
    "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=24",
    "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=20",
    "/nedvizhimost/kvartiry/prodazha/samarkand",
    "/nedvizhimost/kvartiry/prodazha/chirchik",
    "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=21",
    "/nedvizhimost/kvartiry/prodazha/navoi",
    "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=18",
    "/nedvizhimost/kvartiry/prodazha/fergana",
    "/nedvizhimost/kvartiry/prodazha/tojtepa",
    "/nedvizhimost/kvartiry/prodazha/almalyk",
    "/nedvizhimost/kvartiry/prodazha/zarafshan",
    "/nedvizhimost/kvartiry/prodazha/yangiyul",
    "/nedvizhimost/kvartiry/prodazha/eshanguzar",
    "/nedvizhimost/kvartiry/prodazha/kibraj",
    "/nedvizhimost/kvartiry/prodazha/keles",
)

pipeline = OlxRawPipeline(config=config, database=database)
pipeline.run(
    category_paths=priority_sources,
    max_pages_per_category=25,
    fetch_details=False,
)
'@

$code | & $python -
& (Join-Path $PSScriptRoot "restart_site.ps1")
