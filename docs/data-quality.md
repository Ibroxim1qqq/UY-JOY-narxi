# Data quality filter

Maqsad: noreal yoki analitika uchun yaroqsiz e'lonlarni avtomatik yashirish.

## Qanday ishlaydi

Filter e'lonni darhol fizik o'chirmaydi. Ustunlar to'ldiriladi:

- `quality_status = 'ok'` - e'lon ko'rinadi.
- `quality_status = 'suspicious'` - e'lon dashboard va Power BI'dan yashiriladi.
- `quality_reasons` - nega shubhali deb topilgani.
- `quality_checked_at` - oxirgi tekshiruv vaqti.

## Noreal e'lon case'lari

- Sotuv narxi juda past yoki juda yuqori: masalan 500 USD kvartira yoki 100 mln USD uy.
- Ijara narxi juda past yoki juda yuqori: masalan oyiga 1 USD yoki 100 000 USD.
- Xona soni noreal: masalan 80 xona kvartira.
- Maydon noreal: masalan kvartira 5000 m2 yoki maydon 0 m2.
- Yer maydoni noreal: masalan 1000 sotixdan katta.
- Qavat mantiqsiz: masalan 12-qavat, lekin bino jami 5 qavatli.
- Title/description juda bo'sh.
- Telegram post `sotildi` deb belgilangan.
- Manzil ham, narx ham yo'q.

## Qo'lda ishga tushirish

```powershell
cd "C:\Users\Aslanbek\Documents\UY-JOY narxlari"
$env:PYTHONPATH="C:\Users\Aslanbek\Documents\UY-JOY narxlari\src"
.\.venv\Scripts\python.exe -m uyjoy_etl.cli mark-suspicious
```

Case ro'yxatini chiqarish:

```powershell
.\.venv\Scripts\python.exe -m uyjoy_etl.cli quality-cases
```

## Tekshirish query

```sql
select quality_status, count(*)
from olx_listing_raw
group by quality_status;

select olx_id, title, price_display, quality_reasons
from olx_listing_raw
where quality_status = 'suspicious'
limit 50;
```

Daily task har scrapingdan keyin shu filtrni avtomatik ishga tushiradi.
