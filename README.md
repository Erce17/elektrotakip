# ⚡ ElektroTakip

Yerel işletmeler için **katalog, müşteri ve fiyat takip** yazılımı.
Elektrik malzemesi satan işletmelerin Excel'de tuttuğu fiyat listelerini
aranabilir, düzenlenebilir bir web uygulamasına taşır.

## Stack

FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL · Jinja2 + HTMX · JWT (cookie tabanlı)

## Kurulum

```bash
uv sync
cp .env.example .env      # DATABASE_URL ve SECRET_KEY doldur
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

`.env` iki değer bekler:

```
DATABASE_URL=postgresql://user:pass@localhost/elektrotakip
SECRET_KEY=<rastgele-uzun-string>
```

## Yapı

```
app/
├── main.py          → uygulama, / ve /health, /db-health
├── config.py        → pydantic-settings ile .env okuma
├── database.py      → engine, SessionLocal, Base, get_db
├── security.py      → bcrypt hash + JWT üret/çöz
├── dependencies.py  → get_current_user (cookie'den token okur)
├── models/          → User · Category/Product · Customer
├── routers/         → auth · catalog · customers
└── templates/       → Jinja2 + HTMX partial'ları
alembic/versions/    → 7 migration
```

## Modüller

### Auth ✅
Kayıt, giriş, çıkış. bcrypt ile parola hash'i, httpOnly cookie'de JWT.
`get_current_user` token'ı çözer, kullanıcı yoksa `None` döner.

### Müşteriler ✅
Listeleme, ekleme, satır içi düzenleme, silme — hepsi HTMX ile sayfa yenilemeden.
Her route giriş kontrolü yapar ve **sadece o kullanıcının kayıtlarını** getirir.

### Katalog ⚠️ eksik
Kategori/ürün yönetimi, canlı arama, satır içi düzenleme, Excel içe/dışa aktarma
(KM bazlı fiyatı metreye çeviren dönüşüm dahil, Türkçe `1.200,50` formatını parse eder).

**Bilinen eksik:** Katalog route'larında henüz auth yok — `user_id=1` sabit veriliyor
ve sorgular kullanıcıya göre filtrelenmiyor. `customers.py` doğru kalıbı içeriyor;
katalog o kalıba çekilecek. Tek kullanıcılı geliştirme dışında kullanılmamalı.

## Yol haritası

- [ ] `catalog.py`'a `get_current_user` bağla, `user_id=1`'i kaldır
- [ ] Ürün sorgularını `Category.user_id` üzerinden kullanıcıya göre filtrele
- [ ] Test yaz (pytest + httpx kurulu, henüz test yok)
- [ ] Teklif/fatura üretimi
