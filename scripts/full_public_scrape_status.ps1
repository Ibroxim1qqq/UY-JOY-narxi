$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$processes = Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -notlike "*-Command*" -and
        (
            ($_.CommandLine -like "*-File*" -and $_.CommandLine -like "*scrape_all_public_sources.ps1*") -or
            ($_.CommandLine -like "*uyjoy_etl.full_public_scrape*")
        )
    } |
    Select-Object ProcessId, ParentProcessId, CreationDate, CommandLine

Write-Host "== Full scrape process =="
if ($processes) {
    $processes | Format-Table -AutoSize
} else {
    Write-Host "Full public scrape ishlamayapti."
}

Write-Host ""
Write-Host "== Progress tail =="
$progressPath = Join-Path $root "logs\full_public_scrape_progress.txt"
if (Test-Path $progressPath) {
    Get-Content $progressPath -Tail 30
} else {
    Write-Host "Progress fayli hali yo'q."
}

Write-Host ""
Write-Host "== Database summary =="
$python = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $root "src"
$env:PYTHONIOENCODING = "utf-8"

@'
from uyjoy_etl.config import load_config
from uyjoy_etl.db import Database

with Database(load_config().database).connect() as conn:
    summary = conn.execute("""
        select count(*) as total,
               count(distinct source_category_path) as sources,
               count(distinct city_name) filter (where city_name is not null) as cities,
               count(distinct district_name) filter (where district_name is not null) as districts,
               count(*) filter (where deal_type = 'sale') as sale,
               count(*) filter (where deal_type = 'rent') as rent,
               count(*) filter (where deal_type = 'exchange') as exchange,
               max(last_seen_at) as last_seen_at
        from olx_listing_raw
    """).fetchone()
    print(dict(summary))

    print("--- category groups ---")
    rows = conn.execute("""
        select
            case
                when source_category_path like '%/kvartiry/prodazha%' then 'kvartira_sotuv'
                when source_category_path like '%/kvartiry/arenda-dolgosrochnaya%' then 'kvartira_ijara'
                when source_category_path like '%/kvartiry/obmen%' then 'kvartira_almashuv'
                when source_category_path like '%/doma/prodazha%' then 'uy_sotuv'
                when source_category_path like '%/doma/arenda-dolgosrochnaya%' then 'uy_ijara'
                when source_category_path like '%/doma/obmen%' then 'uy_almashuv'
                when source_category_path like '%/zemlja/prodazha%' then 'yer_sotuv'
                when source_category_path like '%/zemlja/arenda%' then 'yer_ijara'
                when source_category_path like '%/garazhi-stoyanki/%' then 'garaj'
                when source_category_path like '%/kommercheskie-pomeshcheniya/%' then 'tijorat'
                when source_category_path like '%/posutochno_pochasovo/%' then 'sutkalik'
                else 'boshqa'
            end as group_name,
            count(*) as total,
            max(last_seen_at) as last_seen_at
        from olx_listing_raw
        group by group_name
        order by total desc
    """).fetchall()
    for row in rows:
        print(f"{row['total']:>7} | {row['group_name']} | {row['last_seen_at']}")

    print("--- latest runs ---")
    runs = conn.execute("""
        select status, started_at, finished_at, rows_inserted, rows_updated, pages_processed, error_message
        from etl_runs
        order by started_at desc
        limit 5
    """).fetchall()
    for row in runs:
        print(dict(row))
'@ | & $python -
