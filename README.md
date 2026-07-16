# UY-JOY Narxlari ETL

OLX.uz ko'chmas mulk e'lonlarini bosqichma-bosqich yig'ish uchun ETL loyiha.

Hozirgi bosqich: **raw extract + Postgres load**.

## Nima qiladi?

- OLX.uz real estate listing sahifalarini ochadi.
- Sahifa ichidagi `window.__PRERENDERED_STATE__` JSON ma'lumotini ajratib oladi.
- E'lonning listingdagi va detail sahifadagi raw JSONlarini Postgres `jsonb` ustunlarida saqlaydi.
- Qidirish oson bo'lishi uchun asosiy maydonlarni alohida ustunlarga ham yozadi.
- Har bir request, page, e'lon va xato bo'yicha log yozadi.

## Tez Start

Docker bilan eng oson yo'l:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_docker_and_scrape.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\restart_site.ps1
```

Shundan keyin:

- Dashboard: `http://127.0.0.1:8000`
- pgAdmin: `http://127.0.0.1:5050`
- pgAdmin login: `admin@uyjoy.local` / `admin`
- Postgres server: `127.0.0.1:55432`
- Postgres user/password: `uyjoy` / `uyjoy_password`

Docker Desktop WSL sabab ishlamasa, lokal Postgres cluster bilan:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_local_postgres_and_scrape.ps1
```

Bu loyiha ichida `.postgres-data` papkasida alohida Postgres serverni `127.0.0.1:55432` portda ishga tushiradi.

Ko'proq data olish uchun:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\scrape_priority_sources.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\scrape_rent_priority_sources.ps1
```

Bu scriptlar katta sotuv va ijara source URLlardan 25 sahifagacha olib, `olx_id` bo'yicha duplicate'larni update qiladi.

Har kuni avtomatik yangilash uchun:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_daily_update_task.ps1 -At 10:00
```

Batafsil: `docs/daily-automation.md`.

1. Virtual environment yarating:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Kerakli paketlarni o'rnating:

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
```

3. `.env.example` faylidan `.env` yarating va Postgres parolini yozing.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_env_from_example.ps1
```

Yoki hammasini bitta script bilan tayyorlash:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_project.ps1
```

4. Database schema yarating:

```powershell
python -m uyjoy_etl.cli migrate
```

5. Test scrape:

```powershell
python -m uyjoy_etl.cli scrape --max-pages 1 --limit-categories 1
```

## pgAdmin Ulanish

Docker Postgres `127.0.0.1:55432` da ishlaydi.

pgAdmin uchun:

- Browser: `http://127.0.0.1:5050`
- Login: `admin@uyjoy.local`
- Password: `admin`
- Server host: `postgres` agar pgAdmin container ichidan ulansa, `127.0.0.1` agar lokal pgAdmin appdan ulansa
- Server port: `5432` container pgAdmin ichida, `55432` lokal pgAdmin appda
- Database: `uyjoy_olx`
- Username: `uyjoy`
- Password: `uyjoy_password`

`C:\Program Files\PostgreSQL\17\pgAdmin 4\runtime\pgAdmin4.exe` orqali pgAdmin ochiladi.

Migrationdan keyin pgAdmin ichida `Databases > uyjoy_olx` bazasini oching.
Data ko'rish uchun `sql/useful_queries.sql` faylidagi querylardan foydalaning.

## OLX Limit Haqida

OLX ayrim katta kategoriyalarda ko'rinadigan e'lonlar sonini o'n minglab ko'rsatadi, lekin pagination odatda 25 sahifa / 1000 e'lon atrofida kesiladi.
Shuning uchun haqiqatan ko'proq data olish uchun keyingi bosqichda category -> region -> city -> district bo'yicha bo'lib scraping qilamiz.
Hozirgi pipeline raw saqlash va DBga aniq yozish skeletini tayyorlaydi.

## Tekshiruv

Kod va parser testlarini ishga tushirish:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_checks.ps1
```

Live OLXdan 1 kategoriya va 1 sahifa test scrape:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_test_scrape.ps1
```

OLX source pathdagi region/city/district facetlarini tekshirish:

```powershell
python -m uyjoy_etl.cli inspect-source nedvizhimost/kvartiry/prodazha
```

## Lokal Site

Tortilgan datalarni browserda ko'rish:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_site.ps1
```

Keyin oching:

```text
http://127.0.0.1:8000
```

Site `olx_listing_raw` jadvalidan o'qiydi. Search title, description, shahar, tuman, region va link ichidan qidiradi.

## Muhim Eslatma

Scraper OLX `robots.txt`da yopilgan contact/ajax/account endpointlariga kirmaydi. Telefon raqamni ochish yoki yashirin kontakt endpointlaridan foydalanish bu bosqichga kiritilmagan.
