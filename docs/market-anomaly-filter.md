# Market trend anomaly filter

Analytics line graph raw e'lonlarni o'chirmaydi. U faqat trend hisobida noreal kunlik sakrashlarni chiqarib tashlaydi.

## Segment

Har bir kun alohida segmentda tekshiriladi:

- `city_name`
- `district_name`
- `property_type`
- `deal_type`
- `currency_code`

Masalan, Toshkent + Mirzo-Ulug'bek + kvartira + ijara + UZS boshqa tuman yoki boshqa category bilan aralashtirilmaydi.

## Qanday anomaly deb olinadi?

1. Har kun va segment uchun avg qiymat hisoblanadi.
2. Shu segmentning oldingi va keyingi 2 kuni olinadi.
3. Qo'shni kunlar weighted avg baseline bo'ladi.
4. Agar o'sha kun kamida 3 ta e'longa ega bo'lsa, qo'shni kunlarda ham kamida 3 ta e'lon bo'lsa va kunlik avg qo'shni baseline'dan 2.2 baravar katta yoki 2.2 baravar kichik bo'lsa, u kun anomaly hisoblanadi.

Formula:

```text
daily_avg > neighbor_avg * 2.2
or
daily_avg < neighbor_avg / 2.2
```

## Natija

Anomaly deb topilgan kunlar chart average line, 5 kunlik moving average va umumiy avg hisobidan chiqariladi. Raw data esa bazada qoladi.
