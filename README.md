# SafeSport authentication server

This directory contains the FastAPI authentication foundation only. It uses PostgreSQL, SQLAlchemy, Alembic, rotating JWT refresh sessions, HttpOnly cookies, double-submit CSRF protection, and Zoho SMTP.

## Run locally

1. Copy `.env.example` to `.env` and set a strong `SECRET_KEY` plus the Zoho SMTP credentials.
2. From `server/`, run `uv sync` for local development or `docker compose up --build` for Docker development.
3. The API is available at `http://localhost:8000`; interactive docs are at `/docs`.

For development without SMTP delivery, set `EMAIL_DELIVERY_MODE=console`. This confirms email dispatch without printing OTP codes or reset links.

## Migrations and tests

```bash
uv run alembic upgrade head
uv run pytest
```

The frontend must set `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`. Browser requests use `credentials: "include"`; access and refresh JWT values remain in HttpOnly cookies and are never returned in response bodies.

Create the first System Administrator and base sport catalogue after migrations run:

```bash
./seed
```

The command prompts for the email, name, and password. It uses the running Docker API container when available, otherwise it falls back to local `uv`. Other staff roles can still be created with `uv run python -m scripts.create_user`.
