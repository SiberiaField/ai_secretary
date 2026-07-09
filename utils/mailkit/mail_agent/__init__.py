from .agent import ImapMailAgent, create_folder_based_agent
from .auth import AuthStrategy, OAuth2Auth, PasswordAuth
from .config import MailAccountConfig
from .exceptions import (
    AuthenticationError,
    DraftError,
    FlaggingError,
    MailAgentError,
    MailConnectionError,
)
from .models import (
    DraftRef,
    EmailAddress,
    EmailMessage,
    IncomingAttachment,
    OutgoingAttachment,
    ProcessingStatus,
)
from .status_tracker import FolderStatusTracker, PostgresStatusTracker, StatusTracker

__all__ = [
    "ImapMailAgent",
    "create_folder_based_agent",
    "AuthStrategy",
    "PasswordAuth",
    "OAuth2Auth",
    "MailAccountConfig",
    "MailAgentError",
    "MailConnectionError",
    "AuthenticationError",
    "DraftError",
    "FlaggingError",
    "EmailAddress",
    "EmailMessage",
    "IncomingAttachment",
    "OutgoingAttachment",
    "ProcessingStatus",
    "DraftRef",
    "StatusTracker",
    "FolderStatusTracker",
    "PostgresStatusTracker",
]
