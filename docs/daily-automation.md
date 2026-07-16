# Daily ETL automation

Maqsad: OLX va Telegramdan yangi e'lon/postlarni har kuni avtomatik olib kelish.

## Nima ishlaydi

`scripts/daily_update.ps1` quyidagilarni ketma-ket bajaradi:

1. Lokal Postgresni ishga tushiradi.
2. Database schema migration qiladi.
3. OLX category'laridan oxirgi sahifalarni tekshiradi.
4. Telegram public kanallaridan oxirgi postlarni oladi.
5. Telegram real-estate clean jadvalini qayta to'ldiradi.
6. Noreal/shubhali e'lonlarni `quality_status='suspicious'` qilib belgilaydi.
7. Agar `NEON_DATABASE_URL` yoki `CLOUD_DATABASE_URL` berilgan bo'lsa, lokal datani cloud Postgresga sync qiladi.
8. Lokal dashboardni qayta ishga tushiradi.

Duplicate data buzilmaydi:

- OLX `olx_id` bo'yicha update bo'ladi.
- Telegram `(channel_id, message_id)` bo'yicha update bo'ladi.

## Bir marta qo'lda sinash

```powershell
cd "C:\Users\Aslanbek\Documents\UY-JOY narxlari"
powershell -ExecutionPolicy Bypass -File .\scripts\daily_update.ps1
```

Faqat Telegramni sinash:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\daily_update.ps1 -SkipOlx
```

Faqat OLXni sinash:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\daily_update.ps1 -SkipTelegram
```

## Har kuni 10:00 ga o'rnatish

```powershell
cd "C:\Users\Aslanbek\Documents\UY-JOY narxlari"
powershell -ExecutionPolicy Bypass -File .\scripts\install_daily_update_task.ps1 -At 10:00
```

O'rnatilgandan keyin Windows Task Scheduler ichida `UyJoyDailyUpdate` nomli task ko'rinadi.

## Muhim shartlar

- Kompyuter 10:00 da yoqilgan bo'lishi kerak.
- Telegram session avval `scripts/telegram_login.ps1` orqali ochilgan bo'lishi kerak.
- `.env` ichida Telegram `api_id` va `api_hash` yozilgan bo'lishi kerak.
- Deploy qilingan sayt ham yangilanishi uchun `.env` ichida `NEON_DATABASE_URL` yozilgan bo'lishi kerak.
- Loglar `logs/daily-update-*.log` fayllariga yoziladi.

## Deploy qilingan sayt redeploysiz yangilanishi

Render sayt kodni GitHub'dan oladi, lekin ma'lumotni Neon Postgres'dan o'qiydi.
Shuning uchun data yangilanishi uchun GitHub push yoki Render redeploy shart emas.

Kerakli shart:

```text
NEON_DATABASE_URL=postgresql://...
```

Daily task oxirida `sync-cloud` komandasi ishlaydi:

```powershell
.\.venv\Scripts\python.exe -m uyjoy_etl.cli sync-cloud "NEON_DATABASE_URL"
```

Shunda lokal Postgresdagi yangilangan OLX va Telegram warehouse datasi Neon'ga ko'chadi,
Render sayt esa shu Neon bazadan o'qigani uchun yangi data real saytda ko'rinadi.

## Parametrlar

Default:

- OLX: har source uchun oxirgi `2` sahifa.
- OLX: maksimum `250` source.
- Cloud sync: OLX uchun oxirgi `1` kunda yangilangan qatorlar upsert qilinadi.
- Telegram: har kanal uchun oxirgi `200` post.

Kattaroq qilish:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_daily_update_task.ps1 `
  -At 10:00 `
  -OlxMaxPages 5 `
  -OlxMaxSources 500 `
  -TelegramLimit 500
```

Chuqur OLX source discovery kerak bo'lsa:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\daily_update.ps1 -UseOlxDiscovery
```

Daily task uchun default `UseOlxDiscovery` yoqilmagan. Sababi discovery katta kategoriyalarni bo'lib chiqadi va sekinroq; har kungi yangi e'lonlar uchun categorylarning oxirgi sahifalarini tekshirish yetarli va tezroq.

## Tekshirish query

```sql
select count(*) from olx_listing_raw;

select
    count(*) as jami,
    count(shahar) as shahar_bor,
    count(tuman) as tuman_bor,
    count(narx) as narx_bor
from telegram_real_estate_flat;
```
