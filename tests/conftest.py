"""Test altyapısı.

Testler PostgreSQL yerine bellekteki SQLite'ta koşar: kurulum gerektirmez ve her
test temiz bir şemayla başlar. Şema alembic'ten değil modellerden üretilir; amaç
migration'ları değil route mantığını sınamak.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import csrf
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import create_access_token, hash_password


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # tek bağlantı: TestClient ile aynı belleği paylaşsın
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def raw_client(db_session):
    """CSRF token'ı taşımayan istemci. Sadece CSRF testleri için."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client(raw_client):
    """Normal istemci: tarayıcı gibi CSRF token'ını her istekte taşır.

    Tarayıcıda bunu şablondaki gizli input ve body'deki hx-headers yapıyor;
    testte tek sefer başlığa koymak aynı işi görüyor.
    """
    raw_client.get("/login")  # token cookie'si bu istekte yerleşiyor
    raw_client.headers[csrf.HEADER_NAME] = raw_client.cookies[csrf.COOKIE_NAME]
    return raw_client


@pytest.fixture
def make_user(db_session):
    """Kullanıcı üretir; dönen token cookie'ye konunca o kullanıcı olarak istek atılır."""

    def _make(email: str, password: str = "parola123"):
        user = User(email=email, password_hash=hash_password(password))
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user, create_access_token(user.id)

    return _make


@pytest.fixture
def login_as(raw_client):
    """İstemciyi verilen kullanıcının oturumuna geçirir.

    Bilerek raw_client'a bağlı: client'a bağlansaydı CSRF testleri sırf giriş
    yapmak için token başlığını da yanında getirir, test ettiği şeyi bozardı.
    """

    def _login_as(token: str):
        raw_client.cookies.set("access_token", token)

    return _login_as
