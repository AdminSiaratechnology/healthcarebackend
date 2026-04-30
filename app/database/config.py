from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGO_URI: str
    DB_NAME: str
    GEMINI_API_KEY: str
    KEY_VAULT_DB: str
    KEY_VAULT_COLL: str
    AWS_REGION: str
    KMS_KEY_ARN: str
    AWS_S3_BUCKET: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    JWT_SECRET: str | None = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 525600
    SMTP_HOST: str | None = None
    SMTP_PORT: int | None = 587
    SMTP_USER: str | None = None
    SMTP_PASS: str | None = None
    SMTP_FROM: str | None = None
    SMTP_FROM_NAME: str | None = None
    USE_AWS_KMS: bool = False
    model_config = SettingsConfigDict(  
        env_file=".env",
        env_file_encoding='utf-8',
        case_sensitive=True
    )


settings = Settings()
