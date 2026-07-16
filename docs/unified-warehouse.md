# Unified real estate warehouse

Bu loyiha datani ikki qatlamda saqlaydi:

1. `olx_listing_raw`, `telegram_posts`, `telegram_real_estate_posts` - staging/raw qatlam. Parserdan kelgan asl data va audit uchun kerak.
2. `real_estate_listings` - clean/statistika qatlam. Sayt, admin dashboard va Power BI aynan shu jadvaldan o'qiydi.

## Nega bitta jadval kerak?

OLX va Telegram turli formatda keladi. Statistikada esa bitta umumiy model kerak:

- `source` - `olx` yoki `telegram`
- `source_listing_id` - manbadagi original ID
- `listing_code` - ichki ko'rinishdagi kod
- `source_url` - asl e'lon linki
- `title`, `description`
- `property_type`, `deal_type`
- `price_value`, `currency_code`, `price_display`
- `city_name`, `district_name`, `region_name`, `address`
- `room_count`, `floor_number`, `total_floors`, `area_m2`, `land_sotix`
- `quality_status`, `quality_reasons`
- `posted_at`, `first_seen_at`, `last_seen_at`, `updated_at`

## Yangilanish jarayoni

Har bir scrape/clean jarayonidan keyin:

```powershell
.\.venv\Scripts\python.exe -m uyjoy_etl.cli refresh-unified-listings
```

Bu komanda staging jadvallardan `real_estate_listings`ni qayta yig'adi. Daily schedulerda ham shu qadam qo'shilgan.

## Muhim qaror

Raw jadvallardan ustunlar hozircha o'chirilmaydi. Ular parser, audit, qayta-clean qilish va cloud sync uchun kerak. Keraksiz va chalkash ustunlar sayt/statistika qatlamidan chiqarildi: dashboard endi faqat `real_estate_listings`dagi normalizatsiya qilingan ustunlarni ishlatadi.
