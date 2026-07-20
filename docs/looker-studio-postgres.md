# Looker Studio ulanishi

Bu loyiha uchun Google Sheets `IMPORTDATA` ishlatish shart emas. Listing-level data
to'g'ridan-to'g'ri Neon Postgres ichidagi `public.looker_listings` view orqali
Looker Studio'ga ulanadi.

## Ulanish sozlamalari

Looker Studio ichida:

1. `Create` -> `Data source` -> `PostgreSQL` connectorni tanlang.
2. `Basic` oynasida quyidagilarni kiriting:

| Field | Value |
| --- | --- |
| Host | `ep-small-smoke-aockm6rm.c-2.ap-southeast-1.aws.neon.tech` |
| Port | `5432` |
| Database | `neondb` |
| Username | `looker_reader` |
| Password | `secrets/looker_reader_credentials.txt` ichidagi password |
| SSL | yoqilgan |
| Client authentication | o'chirilgan |

3. Auth tugmasini bosing.
4. Table ro'yxatidan `public.looker_listings` yoki `looker_listings` ni tanlang.
5. `Add` ni bosing.

## Muhim

- `looker_listings` aggregate emas: har bir row bitta e'lon.
- Narxlar Looker uchun tayyor `price_uzs` ustunida UZSga keltirilgan.
- Kvartira sotuv m2 narxi: `price_per_m2_uzs`.
- Hovli sotuv sotix narxi: `price_per_sotix_uzs`.
- Sana filterlari uchun: `posted_date`, `posted_week`, `posted_month`.
- Manba linki uchun: `source_url`.
- Telefon/contact ustunlari bu BI viewga kiritilmagan.
