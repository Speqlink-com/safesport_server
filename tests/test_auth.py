import os

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "SECRET_KEY": "test-secret-key-that-is-long-enough-for-tests",
        "EMAIL_DELIVERY_MODE": "console",
        "COOKIE_SECURE": "false",
        "UPLOADS_DIR": "/tmp/safesport-test-uploads",
    }
)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth import User
from app.models.institution import Institution, Sport
from app.services.security import hash_password

engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)


def override_db():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_db


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return {"X-CSRF-Token": client.cookies["safesport_csrf"]}


def test_registration_session_refresh_and_logout(monkeypatch) -> None:
    monkeypatch.setattr("app.services.otp_service.random_otp", lambda: "1234")
    client = TestClient(app)
    headers = csrf_headers(client)
    with Session(engine) as db:
        sport = Sport(name="Football")
        institution = Institution(
            name="SafeSport Academy",
            type="academy",
            city="Nairobi",
            country="Kenya",
            sports=[sport],
        )
        db.add(institution)
        db.commit()
        db.refresh(institution)
        db.refresh(sport)
        institution_id = str(institution.id)
        sport_id = str(sport.id)

    started = client.post(
        "/api/v1/auth/register/start",
        headers=headers,
        json={
            "role": "athlete",
            "first_name": "Amina",
            "last_name": "Otieno",
            "email": "amina@example.com",
            "password": "correct-horse-battery-staple",
            "date_of_birth": "2008-04-10",
            "organization_id": institution_id,
            "organization_name": "SafeSport Academy",
            "sport_id": sport_id,
        },
    )
    assert started.status_code == 200
    assert "safesport_registration" in client.cookies
    assert "token" not in started.json()

    verified = client.post("/api/v1/auth/register/verify", headers=headers, json={"code": "1234"})
    assert verified.status_code == 200
    completed = client.post("/api/v1/auth/register/complete", headers=headers)
    assert completed.status_code == 200
    assert completed.json()["user"]["role"] == "athlete"
    assert set(completed.json()) == {"user"}
    assert "safesport_access" in client.cookies
    assert "safesport_refresh" in client.cookies

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    old_refresh = client.cookies["safesport_refresh"]
    refreshed = client.post("/api/v1/auth/refresh", headers=headers)
    assert refreshed.status_code == 200
    assert client.cookies["safesport_refresh"] != old_refresh

    logged_out = client.post("/api/v1/auth/logout", headers=headers)
    assert logged_out.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_requires_csrf_and_verifies_otp(monkeypatch) -> None:
    monkeypatch.setattr("app.services.otp_service.random_otp", lambda: "9876")
    client = TestClient(app)
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "amina@example.com", "password": "correct-horse-battery-staple"},
    ).status_code == 403
    headers = csrf_headers(client)
    login = client.post(
        "/api/v1/auth/login",
        headers=headers,
        json={"email": "amina@example.com", "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200
    assert "safesport_login" in client.cookies
    assert client.post("/api/v1/auth/login/verify", headers=headers, json={"code": "0000"}).status_code == 400
    verified = client.post("/api/v1/auth/login/verify", headers=headers, json={"code": "9876"})
    assert verified.status_code == 200
    assert "token" not in verified.json()


def test_password_reset_uses_one_time_http_only_cookie(monkeypatch) -> None:
    monkeypatch.setattr("app.api.auth.random_token", lambda: "one-time-reset-code")
    client = TestClient(app, follow_redirects=False)
    headers = csrf_headers(client)

    forgot = client.post(
        "/api/v1/auth/password/forgot",
        headers=headers,
        json={"email": "amina@example.com"},
    )
    assert forgot.status_code == 200
    assert forgot.json() == {"detail": "If that account exists, password reset instructions were sent"}

    consumed = client.get("/api/v1/auth/password/reset/consume?code=one-time-reset-code")
    assert consumed.status_code == 307
    assert "safesport_password_reset" in consumed.headers["set-cookie"]
    assert "HttpOnly" in consumed.headers["set-cookie"]

    reset = client.post(
        "/api/v1/auth/password/reset",
        headers=headers,
        json={"password": "a-new-secure-password"},
    )
    assert reset.status_code == 200
    assert client.post(
        "/api/v1/auth/password/reset",
        headers=headers,
        json={"password": "another-secure-password"},
    ).status_code == 400


def test_system_admin_creates_institution_for_athlete_catalog(monkeypatch) -> None:
    monkeypatch.setattr("app.services.otp_service.random_otp", lambda: "2468")
    with Session(engine) as db:
        db.add(
            User(
                email="admin@example.com",
                password_hash=hash_password("secure-admin-password"),
                first_name="System",
                last_name="Administrator",
                role="sys-admin",
            )
        )
        db.commit()

    client = TestClient(app)
    headers = csrf_headers(client)
    assert client.post(
        "/api/v1/auth/login",
        headers=headers,
        json={"email": "admin@example.com", "password": "secure-admin-password"},
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/login/verify", headers=headers, json={"code": "2468"}
    ).status_code == 200

    sport = client.post("/api/v1/admin/sports", headers=headers, json={"name": "Swimming"})
    assert sport.status_code == 201
    created = client.post(
        "/api/v1/admin/institutions",
        headers=headers,
        data={
            "name": "Nairobi Sports School",
            "type": "school",
            "city": "Nairobi",
            "country": "Kenya",
            "contact_email": "sports@example.com",
            "is_active": "true",
            "sport_ids": sport.json()["id"],
        },
        files={"logo": ("logo.png", b"small-logo", "image/png")},
    )
    assert created.status_code == 201, created.text
    assert created.json()["sports"][0]["name"] == "Swimming"
    assert created.json()["logo_url"].endswith(".png")

    public = client.get("/api/v1/catalog/institutions")
    assert public.status_code == 200
    assert any(item["name"] == "Nairobi Sports School" for item in public.json())
