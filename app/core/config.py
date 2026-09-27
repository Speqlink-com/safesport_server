from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    otp_expire_minutes: int = 10
    password_reset_expire_minutes: int = 30

    frontend_url: str = "http://localhost:3000"
    backend_public_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None

    zoho_smtp_host: str = "smtp.zoho.com"
    zoho_smtp_port: int = 587
    zoho_smtp_username: str = ""
    zoho_smtp_password: str = ""
    zoho_from_email: str = ""
    zoho_from_name: str = "SafeSport"
    email_delivery_mode: Literal["smtp", "console"] = "smtp"
    safesport_logo_url: str = "https://res.cloudinary.com/dfyqn0c1t/image/upload/v1790532798/safesport_1_roaybx.png"
    uploads_dir: str = "uploads"
    max_logo_bytes: int = 2 * 1024 * 1024
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    cloudinary_upload_preset: str = ""
    cloudinary_institution_folder: str = "safesport/institutions"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def secure_cookies(self) -> bool:
        return self.environment == "production" or self.cookie_secure

    @field_validator("cookie_domain", mode="before")
    @classmethod
    def blank_domain_is_none(cls, value: object) -> object:
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
