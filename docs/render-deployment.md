# Render web + Neon doimiy free DB deploy

Maqsad: dashboardni Render Free tierga, bazani esa vaqt bo'yicha expire bo'lmaydigan Neon Free Postgresga chiqarish.

Muhim cheklovlar:

- Render Free web service 15 daqiqa traffic bo'lmasa uxlab qoladi.
- Neon Free Postgres 0.5 GB storage beradi.
- Lokal raw data lake katta bo'lgani uchun cloudga yengil warehouse CSV yuklaymiz.
- Lokal raw database o'z kompyuterda qoladi; cloud database sayt va Power BI uchun ishlaydi.
- 52 153 e'lon bilan cloud warehouse test hajmi taxminan 151 MB chiqdi.

## 1. Repo tayyor

Repo ichida `render.yaml` bor:

- `uyjoy-dashboard`: FastAPI web service
- `DATABASE_URL`: Neon Postgres connection string
- `preDeployCommand`: yengil cloud schema migrationni ishlatadi

## 2. Neon database yaratish

1. Neon account oching.
2. New Project yarating.
3. Postgres connection stringni oling.
4. Connection string odatda shunga o'xshaydi:

```text
postgresql://user:password@host/dbname?sslmode=require
```

## 3. Render dashboardda deploy

1. Render accountga kiring.
2. GitHub/GitLab repo ulang.
3. `New` -> `Blueprint` tanlang.
4. Shu repo ichidagi `render.yaml`ni tanlang.
5. `DATABASE_URL` so'ralganda Neon connection stringni kiriting.
6. `DASHBOARD_PASSWORD` so'ralganda kuchli parol kiriting.
7. Deploy tugagach Render sizga `https://...onrender.com` URL beradi.

## 4. Lokal datani Neon Postgresga ko'chirish

Avval yengil cloud warehouse CSV yarating:

```powershell
cd "C:\Users\Aslanbek\Documents\UY-JOY narxlari"
powershell -ExecutionPolicy Bypass -File .\scripts\export_cloud_warehouse.ps1
```

Keyin Neon connection string bilan import qiling:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore_cloud_warehouse.ps1 -DatabaseUrl "PASTE_NEON_DATABASE_URL"
```

Restore oxirida `select count(*)` chiqadi. U `52153` atrofida bo'lishi kerak.

## 5. Power BI

Render dashboard URL uchun:

```text
https://YOUR-RENDER-APP.onrender.com/api/powerbi/listings.csv
```

Power BI `Web` connector bilan ulanadi. Login:

```text
Username: admin
Password: Render deploy paytida kiritilgan DASHBOARD_PASSWORD
```

## 6. Backup

Lokal raw data lake asosiy manba bo'lib qoladi. Cloud warehouse kerak bo'lsa qayta export/import qilinadi:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\export_cloud_warehouse.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\restore_cloud_warehouse.ps1 -DatabaseUrl "PASTE_NEON_DATABASE_URL"
```
