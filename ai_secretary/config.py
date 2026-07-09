from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecretaryConfig(BaseModel):
    name: str
    email: str


class DatabaseConfig(BaseModel):
    excel_path: Path


class Documents(BaseModel):
    templates_dir: Path


class SortingAgentConfig(BaseModel):
    model_name: str
    gigachat_auth_key: str
    tasks_root_dir: Path


class SendingAgentConfig(BaseModel):
    tasks_root_dir: Path
    generate_example_doc: bool
    output_dir: Path


class Config(BaseSettings):
    secretary: SecretaryConfig
    database: DatabaseConfig
    documents: Documents
    sorting_agent: SortingAgentConfig
    sending_agent: SendingAgentConfig

    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__")


config = Config()
