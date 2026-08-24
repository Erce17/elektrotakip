"""Kimlik doğrulama katmanının güvenlik davranışları.

Buradaki her test bir açığı sabitliyor; hepsi canlıya çıkmadan kapatılması
gereken borç listesinden (`PROGRESS.md` → "Güvenlik borcu") geliyor.
"""

import time

import jwt
import pytest

from app import rate_limit
from app.config import Settings
from app.models import User
from app.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    parola_hatasi,
)

GECERLI_PAROLA = "cok-uzun-bir-parola"


def kayit_ol(client, eposta=" Ali@Example.COM ", parola=GECERLI_PAROLA):
    return client.post("/register", data={"email": eposta, "password": parola})


# --- Parola politikası ---------------------------------------------------


@pytest.mark.parametrize(
    "parola",
    ["a", "kisa", "123456789", "          ", "aaaaaaaaaaaa"],
)
def test_zayif_parola_reddedilir(parola):
    assert parola_hatasi(parola) is not None


def test_uzun_ve_karisik_parola_kabul_edilir():
    assert parola_hatasi("bakir fiyati her gun oynuyor") is None


def test_bcryptin_kirptigi_uzunluk_reddedilir():
    """bcrypt 72 bayttan sonrasını sessizce atıyor; sessiz kırpma kabul edilmiyor."""
    assert parola_hatasi("x" * 73) is not None


def test_parola_epostayla_ayni_olamaz():
    assert parola_hatasi("uzun@ornek.com", "uzun@ornek.com") is not None


def test_kisa_parolayla_kayit_olunamaz(client, db_session):
    yanit = kayit_ol(client, parola="kisa")

    assert yanit.status_code == 400
    assert db_session.query(User).count() == 0


# --- E-posta normalizasyonu ----------------------------------------------


def test_eposta_kucuk_harfe_indiriliyor(client, db_session):
    kayit_ol(client)

    kullanici = db_session.query(User).one()
    assert kullanici.email == "ali@example.com"


def test_farkli_yazimla_ayni_hesap_iki_kez_acilamaz(client, db_session):
    kayit_ol(client, eposta="ali@example.com")
    yanit = kayit_ol(client, eposta="ALI@example.com")

    assert yanit.status_code == 400
    assert db_session.query(User).count() == 1


def test_buyuk_harfle_giris_yapilabiliyor(client, db_session):
    kayit_ol(client, eposta="ali@example.com")

    yanit = client.post(
        "/login",
        data={"email": "ALI@Example.com", "password": GECERLI_PAROLA},
        follow_redirects=False,
    )

    assert yanit.status_code == 303
    assert "access_token" in yanit.cookies


def test_gecersiz_eposta_reddedilir(client, db_session):
    yanit = kayit_ol(client, eposta="eposta-degil")

    assert yanit.status_code == 400
    assert db_session.query(User).count() == 0


# --- Deneme sınırı --------------------------------------------------------


def test_besinci_hatali_denemeden_sonra_kilitleniyor(client, db_session):
    kayit_ol(client, eposta="ali@example.com")

    for _ in range(5):
        yanit = client.post(
            "/login", data={"email": "ali@example.com", "password": "yanlis-parola"}
        )
        assert "E-posta veya şifre hatalı." in yanit.text

    kilitli = client.post(
        "/login", data={"email": "ali@example.com", "password": "yanlis-parola"}
    )
    assert "Çok fazla hatalı deneme" in kilitli.text


def test_kilitliyken_dogru_parola_da_gecmiyor(client, db_session):
    """Kilit doğrulamadan önce bakılmalı; yoksa sınır kaba kuvveti durdurmuyor."""
    kayit_ol(client, eposta="ali@example.com")
    for _ in range(5):
        client.post("/login", data={"email": "ali@example.com", "password": "yanlis"})

    yanit = client.post(
        "/login",
        data={"email": "ali@example.com", "password": GECERLI_PAROLA},
        follow_redirects=False,
    )

    assert yanit.status_code == 400
    assert "access_token" not in yanit.cookies


def test_basarili_giris_sayaci_sifirliyor(client, db_session):
    kayit_ol(client, eposta="ali@example.com")
    for _ in range(4):
        client.post("/login", data={"email": "ali@example.com", "password": "yanlis"})

    client.post(
        "/login",
        data={"email": "ali@example.com", "password": GECERLI_PAROLA},
        follow_redirects=False,
    )
    for _ in range(4):
        yanit = client.post(
            "/login", data={"email": "ali@example.com", "password": "yanlis"}
        )

    assert "Çok fazla hatalı deneme" not in yanit.text


def test_pencere_gecince_kilit_aciliyor():
    sinir = rate_limit.DenemeSiniri(azami=2, pencere=0)
    sinir.basarisiz("ali")
    sinir.basarisiz("ali")

    time.sleep(0.01)
    assert not sinir.kilitli_mi("ali")


def test_kilit_hesap_bazli_baskasini_etkilemiyor(client, db_session):
    kayit_ol(client, eposta="ali@example.com")
    kayit_ol(client, eposta="veli@example.com")
    for _ in range(5):
        client.post("/login", data={"email": "ali@example.com", "password": "yanlis"})

    yanit = client.post(
        "/login",
        data={"email": "veli@example.com", "password": GECERLI_PAROLA},
        follow_redirects=False,
    )

    assert yanit.status_code == 303


# --- Kullanıcı sızdırma ---------------------------------------------------


def test_olmayan_kullanici_ile_yanlis_parola_ayni_mesaji_veriyor(client, db_session):
    kayit_ol(client, eposta="ali@example.com")

    yok = client.post("/login", data={"email": "kimse@example.com", "password": "yanlis"})
    yanlis = client.post("/login", data={"email": "ali@example.com", "password": "yanlis"})

    assert "E-posta veya şifre hatalı." in yok.text
    assert "E-posta veya şifre hatalı." in yanlis.text


# --- Token ----------------------------------------------------------------


def test_baska_anahtarla_imzalanan_token_reddediliyor():
    sahte = jwt.encode({"sub": "1", "exp": 9999999999}, "baska-anahtar", algorithm=ALGORITHM)

    assert decode_access_token(sahte) is None


def test_alg_none_token_reddediliyor():
    """`alg: none` klasik JWT atlatması; algoritma listesi açıkça verildiği için geçmez."""
    sahte = jwt.encode({"sub": "1", "exp": 9999999999}, None, algorithm="none")

    assert decode_access_token(sahte) is None


def test_suresiz_token_reddediliyor(monkeypatch):
    from app.config import settings

    sahte = jwt.encode({"sub": "1"}, settings.secret_key, algorithm=ALGORITHM)

    assert decode_access_token(sahte) is None


def test_gecerli_token_cozuluyor():
    assert decode_access_token(create_access_token(42)) == "42"


# --- Ayarlar --------------------------------------------------------------


@pytest.mark.parametrize("anahtar", ["kisa", "<buraya-rastgele-uzun-string>", "secret"])
def test_zayif_secret_key_uygulamayi_acmiyor(anahtar):
    with pytest.raises(ValueError):
        Settings(database_url="sqlite://", secret_key=anahtar, _env_file=None)


def test_guclu_secret_key_kabul_ediliyor():
    ayar = Settings(database_url="sqlite://", secret_key="x" * 40, _env_file=None)

    assert ayar.secret_key == "x" * 40


# --- Başlıklar ve çıkış ---------------------------------------------------


def test_guvenlik_basliklari_gonderiliyor(client):
    yanit = client.get("/login")

    assert yanit.headers["X-Frame-Options"] == "DENY"
    assert yanit.headers["X-Content-Type-Options"] == "nosniff"
    assert yanit.headers["Referrer-Policy"] == "same-origin"


def test_cikis_oturum_cookiesini_siliyor(client, db_session):
    kayit_ol(client, eposta="ali@example.com")
    client.post(
        "/login",
        data={"email": "ali@example.com", "password": GECERLI_PAROLA},
        follow_redirects=False,
    )

    client.post("/logout", follow_redirects=False)

    assert not client.cookies.get("access_token")
