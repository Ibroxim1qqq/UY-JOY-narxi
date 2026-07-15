# Contact data uchun kerakli ruxsat va format

Telefon raqamlarni e'lon rowiga avtomatik qo'shish uchun ruxsatli manba kerak.

## Qabul qilinadigan ruxsat hujjatlari

1. OLX rahbariyati yoki vakolatli xodimidan yozma ruxsat.
2. Ruxsatda loyiha nomi bo'lishi kerak: masalan `uysot.uz` yoki `UY-JOY`.
3. Ruxsatda contact ma'lumotlarini avtomatik olish/import qilishga aniq ruxsat bo'lishi kerak.
4. Ruxsatda foydalanish chegarasi bo'lishi kerak: faqat uy-joy e'lonlari, faqat O'zbekiston, faqat platforma ichida aloqa o'rnatish.
5. Agar maxsus endpoint yoki feed berilsa, uning URL, auth usuli, rate limit va maydonlari ko'rsatiladi.

## Qabul qilinadigan texnik formatlar

CSV/Excel/export:

```csv
olx_id,listing_url,phone,contact_name
65095280,https://www.olx.uz/d/obyavlenie/example.html,+998901234567,Ali
```

Minimal majburiy maydonlar:

- `phone` yoki `contact_phone`
- `olx_id` yoki `listing_url`

Qo'shimcha maydonlar:

- `contact_name`
- `source`
- `seller_id`

## Import buyrug'i

```powershell
.\.venv\Scripts\python.exe -m uyjoy_etl.cli import-contacts contacts.csv --source olx_authorized_export
```

Import `olx_id` yoki `listing_url` orqali mavjud e'lonni topadi va `contact_phone` ustunini yangilaydi.
