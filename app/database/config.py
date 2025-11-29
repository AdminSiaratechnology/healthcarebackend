from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MONGO_URI: str
    DB_NAME: str
    KEY_VAULT_DB: str
    KEY_VAULT_COLL: str
    AWS_REGION: str
    KMS_KEY_ARN: str
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    JWT_SECRET: str | None = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    model_config = SettingsConfigDict(  
        env_file=".env",
        env_file_encoding='utf-8',
        case_sensitive=True
    )


settings = Settings()
