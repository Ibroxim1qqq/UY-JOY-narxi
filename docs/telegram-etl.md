# Telegram ETL

Maqsad: public Telegram kanallardagi postlarni rasmiy Telegram API orqali olib, Postgresga yozish.

## Xavfsizlik

- `TELEGRAM_API_ID` va `TELEGRAM_API_HASH` faqat lokal `.env` ichida turadi.
- Telegram session `secrets/` papkasida saqlanadi.
- `.env` va `secrets/` GitHubga chiqmaydi.
- Faqat public kanal postlari olinadi; private kanal, user phone, member list olinmaydi.

## Birinchi login

```powershell
cd "C:\Users\Aslanbek\Documents\UY-JOY narxlari"
$env:PYTHONPATH="C:\Users\Aslanbek\Documents\UY-JOY narxlari\src"
.\.venv\Scripts\python.exe -m uyjoy_etl.cli telegram-login
```

Terminal telefon raqam va Telegram appga kelgan kodni so'rashi mumkin. Bir marta login bo'lgach session saqlanadi.

## Kanal postlarini olish

```powershell
$env:PYTHONPATH="C:\Users\Aslanbek\Documents\UY-JOY narxlari\src"
.\.venv\Scripts\python.exe -m uyjoy_etl.cli scrape-telegram @channel_username --limit 100
```

Bir nechta kanal:

```powershell
.\.venv\Scripts\python.exe -m uyjoy_etl.cli scrape-telegram @channel1 https://t.me/channel2 --limit 200
```

## Saqlanadigan ustunlar

`telegram_channels`:

- `channel_id`
- `username`
- `title`
- `channel_url`
- `raw_channel`

`telegram_posts`:

- `channel_id`
- `message_id`
- `channel_username`
- `channel_title`
- `post_url`
- `posted_at`
- `text`
- `views`
- `forwards`
- `replies_count`
- `has_media`
- `media_type`
- `raw_message`

Post link formati:

```text
https://t.me/channel_username/message_id
```
