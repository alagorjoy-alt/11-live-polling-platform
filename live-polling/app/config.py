"""Settings are read from environment variables on every access so tests can override them."""
import os


def _flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    @property
    def database_path(self) -> str:
        return os.environ.get("DATABASE_PATH", "polling.db")

    @property
    def hash_salt(self) -> str:
        return os.environ.get("HASH_SALT", "dev-salt-change-me")

    @property
    def enforce_ip_limit(self) -> bool:
        return _flag("ENFORCE_IP_LIMIT")

    @property
    def trust_proxy(self) -> bool:
        return _flag("TRUST_PROXY")

    @property
    def cookie_secure(self) -> bool:
        return _flag("COOKIE_SECURE")


settings = Settings()
