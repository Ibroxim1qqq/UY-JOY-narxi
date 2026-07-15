# UY-JOY production deploy tartibi

Bu loyiha FastAPI dashboard, OLX scraper va Postgres bazadan iborat. 200-300 ming e'longacha o'sishini hisobga olib, production deploy Docker Compose + Postgres + Nginx orqali qilinadi.

## 1. Server tanlash

Tavsiya:

- 200-300 ming e'lon uchun: 4 CPU, 8 GB RAM, 80+ GB SSD.
- Minimal ishlaydigan variant: 2 CPU, 4 GB RAM, 50+ GB SSD.
- Free hosting 300 ming e'lon uchun ishonchli emas. Hozirgi 23 ming qator baza 264 MB, 300 ming qator bir necha GB bo'lishi mumkin.

## 2. Serverga Docker o'rnatish

Ubuntu serverda:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git nginx certbot python3-certbot-nginx
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Keyin serverga qayta login qiling.

## 3. Loyihani serverga joylash

```bash
sudo mkdir -p /opt/uyjoy
sudo chown -R $USER:$USER /opt/uyjoy
cd /opt/uyjoy
```

Loyihani shu papkaga Git orqali clone qiling yoki fayllarni upload qiling.

## 4. Production env

```bash
cp .env.prod.example .env.prod
nano .env.prod
```

Majburiy almashtiriladi:

- `POSTGRES_PASSWORD`
- `PGADMIN_DEFAULT_PASSWORD`
- `DASHBOARD_PASSWORD`

Dashboard productionda basic auth bilan himoyalanadi. Login/parol `.env.prod` ichidagi `DASHBOARD_USERNAME` va `DASHBOARD_PASSWORD`.

## 5. Deploy

```bash
chmod +x scripts/*.sh
scripts/deploy_prod.sh
```

Script quyidagilarni qiladi:

- Postgresni tuning bilan ko'taradi.
- Schema va 300k uchun kerakli indekslarni yaratadi.
- FastAPI dashboardni ishga tushiradi.
- `/health` endpointini tekshiradi.

Qo'lda tekshirish:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
curl http://127.0.0.1:8000/health
```

## 6. Hozirgi lokal datani serverga ko'chirish

Windows lokal kompyuterda dump oling:

```powershell
$env:PGPASSWORD = "uyjoy_password"
& "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" `
  -h 127.0.0.1 -p 55432 -U uyjoy -d uyjoy_olx `
  -Fc -f uyjoy_olx.dump
```

Serverga yuboring:

```bash
scp uyjoy_olx.dump user@server-ip:/opt/uyjoy/
```

Serverda restore:

```bash
cd /opt/uyjoy
scripts/restore_prod.sh uyjoy_olx.dump
```

Restore tugagach web app avtomatik qayta ko'tariladi.

## 7. Ko'proq data yig'ish

Qo'lda scrape:

```bash
scripts/scrape_prod.sh
```

Parametr bilan:

```bash
MAX_PAGES=25 MAX_VISIBLE=1000 scripts/scrape_prod.sh
```

Cron orqali har 6 soatda:

```bash
mkdir -p /opt/uyjoy/logs
crontab -e
```

```cron
0 */6 * * * cd /opt/uyjoy && scripts/backup_prod.sh >> /opt/uyjoy/logs/backup.log 2>&1 && scripts/scrape_prod.sh >> /opt/uyjoy/logs/scrape.log 2>&1
```

## 8. Domain va SSL

Nginx config namunasi bor:

```bash
sudo cp infra/nginx/uyjoy.conf.example /etc/nginx/sites-available/uyjoy
sudo nano /etc/nginx/sites-available/uyjoy
```

`your-domain.uz` ni haqiqiy domain bilan almashtiring.

```bash
sudo ln -s /etc/nginx/sites-available/uyjoy /etc/nginx/sites-enabled/uyjoy
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.uz
```

## 9. Backup va restore

Backup:

```bash
scripts/backup_prod.sh
```

Backup fayllari `backups/` ichida turadi. Default retention: 14 kun.

Restore:

```bash
scripts/restore_prod.sh backups/uyjoy_olx_YYYYMMDD_HHMMSS.dump
```

## 10. pgAdmin

pgAdmin default ko'tarilmaydi. Kerak bo'lsa:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml --profile admin up -d pgadmin
```

pgAdmin serverning faqat `127.0.0.1:5050` portida ochiladi. Local kompyuterdan tunnel:

```bash
ssh -L 5050:127.0.0.1:5050 user@server-ip
```

Keyin browserda:

```text
http://127.0.0.1:5050
```

## 11. Monitoring buyruqlari

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f web
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f postgres
docker stats
df -h
```

## Muhim

Bu loyiha Python backend va Postgresga tayanadi. Static hosting yoki oddiy Sites deploy bunga mos emas, chunki 200-300 ming qator raw JSON data va scraper uchun doimiy Postgres kerak.
