from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
DEFAULT_USERS_FILE = APP_DIR / "fixtures" / "ldap_users.yaml"
DEFAULT_PSSO_USERS_FILE = APP_DIR / "fixtures" / "psso_users.yaml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mock_host: str = "0.0.0.0"
    mock_port: int = 8090
    ldap_aes_key: str = "SEQNUM01KG118K65MZ69NM8GMGE0XE5W"
    ldap_users_file: Path = DEFAULT_USERS_FILE

    # openapi-mng-dev PSSO memberLogin mock (AES/CBC/PKCS5, zero IV — see app/crypto/aes_cbc.py)
    # Must match openapi-mng-dev's psso.aes.key (PSSO_AES_KEY env var).
    psso_aes_key: str = "PSSOMOCK25OVMC6CV13PC97OBEWX5FYE"
    psso_users_file: Path = DEFAULT_PSSO_USERS_FILE


@lru_cache
def get_settings() -> Settings:
    return Settings()
