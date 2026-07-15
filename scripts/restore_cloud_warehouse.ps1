param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl,

    [string]$CsvPath = "backups/uyjoy-cloud-listings.csv"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path $CsvPath)) {
    throw "CSV topilmadi: $CsvPath. Avval scripts\export_cloud_warehouse.ps1 ni ishlating."
}

$psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
if (-not (Test-Path $psql)) {
    throw "psql topilmadi: $psql"
}

$schemaPath = Join-Path $root "sql\schema_cloud.sql"
$resolvedCsvPath = (Resolve-Path $CsvPath).Path.Replace("\", "/")

$columns = @(
    "olx_id",
    "listing_url",
    "source_category_path",
    "source_page",
    "category_id",
    "category_type",
    "title",
    "description",
    "price_display",
    "price_value",
    "currency_code",
    "is_price_negotiable",
    "city_name",
    "district_name",
    "region_name",
    "location_path",
    "latitude",
    "longitude",
    "seller_id",
    "seller_name",
    "seller_type",
    "is_business",
    "contact_phone",
    "contact_name",
    "contact_source",
    "contact_raw",
    "contact_imported_at",
    "contact_updated_at",
    "created_time",
    "last_refresh_time",
    "pushup_time",
    "valid_to_time",
    "is_active",
    "status",
    "raw_params",
    "param_values",
    "raw_photos",
    "raw_listing",
    "raw_detail",
    "content_hash",
    "first_seen_at",
    "last_seen_at",
    "detail_fetched_at",
    "updated_at",
    "phone_number"
) -join ", "

$copySql = @"
\copy olx_listing_raw ($columns) from '$resolvedCsvPath' with (format csv, header true, encoding 'UTF8')
"@

$copyFile = Join-Path $env:TEMP "uyjoy_neon_copy_$PID.sql"
Set-Content -Path $copyFile -Value $copySql -Encoding UTF8

Write-Host "Cloud schema yaratilmoqda..."
& $psql $DatabaseUrl -v ON_ERROR_STOP=1 -f $schemaPath

Write-Host "Cloud jadval tozalanmoqda..."
& $psql $DatabaseUrl -v ON_ERROR_STOP=1 -c "truncate table olx_fetch_logs, etl_runs, olx_listing_raw restart identity cascade;"

Write-Host "CSV Neon/Postgresga COPY orqali yuklanmoqda..."
& $psql $DatabaseUrl -v ON_ERROR_STOP=1 -f $copyFile

Write-Host "Restore tugadi. Tekshiruv:"
& $psql $DatabaseUrl -c "select count(*) as listings from olx_listing_raw;"

Remove-Item -LiteralPath $copyFile -ErrorAction SilentlyContinue
