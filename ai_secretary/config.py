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
    agents_msgs_dir: Path
    tasks_root_dir: Path


class SendingAgentConfig(BaseModel):
    tasks_root_dir: Path
    generate_example_doc: bool
    output_dir: Path


class MailConfig(BaseModel):
    imap_host: str
    imap_port: int = 993
    imap_user: str
    imap_app_password: str
    drafts_folder: str | None = None  # None -> автоопределение через special_use.py


class Config(BaseSettings):
    secretary: SecretaryConfig
    database: DatabaseConfig
    documents: Documents
    sorting_agent: SortingAgentConfig
    sending_agent: SendingAgentConfig
    mail: MailConfig

    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__")


config = Config()
