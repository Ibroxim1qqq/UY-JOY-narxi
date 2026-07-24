# UY-JOY Core

UY-JOY endi bitta toza local pipeline atrofida ishlaydi:

```text
OLX + Telegram -> Postgres -> bi_tashkent_sale_market -> Metabase
bi_tashkent_sale_market -> 30 kunlik ML model -> ML forma
```

## Start

Hamma kerakli servislarni ko'tarish:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_uyjoy.ps1
```

Bu script:

- local Postgresni `127.0.0.1:55432` da ishga tushiradi
- Metabaseni `http://127.0.0.1:3000` da tekshiradi yoki ko'taradi
- ML formani `http://127.0.0.1:8000` da tekshiradi yoki ko'taradi
- daily update kerak bo'lsa backgroundda boshlaydi

Doimiy local deploy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_uyjoy.ps1
```

Deploy script test, migration, HTTP smoke, startup va daemon restartni bajaradi. Daemon har 5 daqiqada Postgres, Metabase va ML formani tekshiradi. Data o'zgarsa `real_estate_listings` refresh qilinadi, 30 kunlik ML model qayta train bo'ladi va ML forma restart qilinadi.

Startupga qo'shish:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_uyjoy_startup.ps1
```

Startupdan olib tashlash:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall_uyjoy_startup.ps1
```

## Daily Update

Kunlik data va model update:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\daily_update.ps1
```

Pipeline ketma-ketligi:

1. Schema va BI viewlarni yangilaydi.
2. OLX yangi e'lonlarini tortadi.
3. Telegram postlarini tortadi va clean qiladi.
4. Shubhali e'lonlarni quality filterdan o'tkazadi.
5. OLX + Telegram datani `real_estate_listings` jadvaliga yig'adi.
6. Oxirgi 30 kunlik Toshkent kvartira sotuv data bilan ML modelni train qiladi.
7. ML formani qayta ishga tushiradi.
8. `NEON_DATABASE_URL` berilgan bo'lsa, cloud Postgresni ham sync qiladi.

## Metabase

Local Metabase:

```text
http://127.0.0.1:3000
```

Asosiy BI source:

```text
public.bi_tashkent_sale_market
```

Runtime joylari:

```text
Postgres data: .postgres-data
Metabase app jar: %LOCALAPPDATA%\UYJOY\metabase\metabase.jar
Metabase runner: tools\metabase\run-metabase.cmd
Startup shortcut: shell:startup\UYJOY Core Daemon.lnk
```

## ML Forma

Local ML valuation form:

```text
http://127.0.0.1:8000
```

API:

```http
POST /api/apartment-valuation
```

Payload:

```json
{
  "district": "Uchtepa",
  "rooms": 2,
  "area_m2": 55,
  "floor_number": 3,
  "total_floors": 9,
  "currency": "UZS"
}
```

## Public Deploy

Doimiy public URL uchun repo Render blueprint bilan tayyorlangan:

```text
render.yaml
Dockerfile.ml
Dockerfile.metabase
```

Cloud database sifatida Render Postgres emas, Neon ishlatiladi. Kerakli env varlar:

```powershell
$env:NEON_DATABASE_URL='postgresql://.../uyjoy_olx?sslmode=require'
$env:METABASE_DATABASE_URL='postgresql://.../metabase_app?sslmode=require'
```

Lokal OLX + Telegram data Neon warehousega ko'chirish. Default holatda free Neon limitiga sig'ishi uchun oxirgi 90 kunlik `real_estate_listings` market data ko'chadi; raw OLX/Telegram jadvallari cloudga tashlanmaydi.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync_cloud_database.ps1
```

Butun raw datani majburan ko'chirish kerak bo'lsa:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync_cloud_database.ps1 -FullRaw
```

Lokal Metabase dashboard metadata va `UY-JOY Postgres` connectionni Neon warehousega yo'naltirish:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync_cloud_metabase.ps1
```

Render services:

```text
uyjoy-ml-form  -> DATABASE_URL = NEON_DATABASE_URL
uyjoy-metabase -> MB_DB_CONNECTION_URI = METABASE_DATABASE_URL
```

`daily_update.ps1` har kuni data tortgandan keyin `NEON_DATABASE_URL` mavjud bo'lsa cloud datani ham yangilaydi.

## CLI

Core komandalar:

```powershell
.\.venv\Scripts\python.exe -m uyjoy_etl.cli migrate
.\.venv\Scripts\python.exe -m uyjoy_etl.cli ping-db
.\.venv\Scripts\python.exe -m uyjoy_etl.cli telegram-login
.\.venv\Scripts\python.exe -m uyjoy_etl.cli scrape --max-pages 2 --no-details
.\.venv\Scripts\python.exe -m uyjoy_etl.cli scrape-telegram t.me/uybozorim --limit 200
.\.venv\Scripts\python.exe -m uyjoy_etl.cli clean-telegram-real-estate
.\.venv\Scripts\python.exe -m uyjoy_etl.cli mark-suspicious
.\.venv\Scripts\python.exe -m uyjoy_etl.cli refresh-unified-listings
.\.venv\Scripts\python.exe -m uyjoy_etl.cli train-valuation-model --days 30
```

## Tests

```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m unittest discover -s tests
```
