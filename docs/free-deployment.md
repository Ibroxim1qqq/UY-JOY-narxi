# Bepul deploy variantlari

Maqsad: serverga pul to'lamasdan dashboardni ko'rish va ulashish.

## Variant A: 0 so'm, eng tez yo'l

Lokal kompyuterdagi hozirgi dashboardni Cloudflare Quick Tunnel orqali internetga chiqaramiz.

Afzalliklari:

- VPS kerak emas.
- Postgres lokal qoladi, hozirgi data yo'qolmaydi.
- Public HTTPS link beradi.
- pgAdmin lokal ishlashda davom etadi.

Cheklovlari:

- Kompyuter yoqilgan bo'lishi kerak.
- Dashboard va Postgres ishlab turishi kerak.
- Quick Tunnel URL har restartda o'zgarishi mumkin.
- Bu production emas, demo va shaxsiy ishlatish uchun qulay.

Ishga tushirish:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_free_tunnel.ps1
```

Script lokal Postgresni ko'taradi, dashboardni restart qiladi va `cloudflared` orqali public URL chiqaradi.

Backgroundda ishga tushirish uchun:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_free_tunnel_background.ps1
```

Chiqgan public link `logs/public-url.txt` ichiga ham yoziladi.

To'xtatish:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_free_tunnel.ps1
```

## Variant A2: doimiy URL bilan Cloudflare tunnel

Quick Tunnel (`*.trycloudflare.com`) doimiy emas. Bitta o'zgarmaydigan link kerak bo'lsa, Cloudflare account va Cloudflarega ulangan domen kerak bo'ladi.

Misol:

```text
https://dashboard.uysot.uz
```

Birinchi marta sozlash:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_permanent_tunnel.ps1 -Hostname dashboard.uysot.uz
```

Bu jarayonda browser ochiladi. Cloudflare accountga kirib, domenni tanlaysiz. Script named tunnel yaratadi, DNS route qo'shadi va `infra/cloudflare/config.yml` faylini tayyorlaydi.

Keyingi safar doimiy URLni ishga tushirish:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_permanent_tunnel.ps1
```

Doimiy link `logs/permanent-public-url.txt` ichida ham turadi.

## Variant B: cloud ham bepul, lekin limitli

Bu variantda database Neon Free, web app esa Render Free bo'lishi mumkin.

Hozirgi lokal baza hajmi taxminan 264 MB. Neon Free 0.5 GB storage beradi, shuning uchun hozircha sig'adi.

Cheklovlari:

- Data 0.5 GB dan oshsa tozalash yoki pullik plan kerak bo'ladi.
- Render Free web service 15 daqiqa ishlatilmasa uxlab qoladi va keyingi ochishda taxminan 1 daqiqa uyg'onadi.
- Doimiy scrapingni free tierda ko'p ishlatish tavsiya qilinmaydi. Scrapingni lokal kompyuterdan yoki kam-kam GitHub Actions orqali yuritish yaxshiroq.
- Public dashboardga chiqarishdan oldin login/parol qo'shish kerak.

## Tavsiya

Hozircha eng toza bepul yo'l: Variant A.

Keyingi bosqich:

1. Dashboardga oddiy login/parol qo'shamiz.
2. `start_free_tunnel.ps1` bilan public link chiqaramiz.
3. Agar keyin doimiy domen kerak bo'lsa, Render + Neon Free variantini sozlaymiz.
