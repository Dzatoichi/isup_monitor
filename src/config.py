from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: str
    DB_USER: str
    DB_PASS: str
    DB_NAME: str
    YANDEX_CLIENT_ID: str = ""
    YANDEX_CLIENT_SECRET: SecretStr | None = None
    YANDEX_REDIRECT_URI: str = ""
    YANDEX_CORPORATE_DOMAIN: str = ""
    WEB_COOKIE_SECURE: bool = True

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore",
        )

    def CONNECT_ASYNC(self) -> URL:
        """
        Функция создания соединения с БД.
        """
        return URL.create(
            "postgresql+psycopg", username=self.DB_USER, password=self.DB_PASS,
            host=self.DB_HOST, port=int(self.DB_PORT), database=self.DB_NAME,
        )

settings = Settings() # pyright: ignore[reportCallIssue]
