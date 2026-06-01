from enum import StrEnum


class InvokeFrom(StrEnum):
    SERVICE_API = "service_api"
    WEB_APP = "web_app"
    DEBUGGER = "debugger"
    ASSISTANT_AGENT = "assistant_agent"


class MessageStatus(StrEnum):
    NORMAL = "normal"
    STOP = "stop"
    TIMEOUT = "timeout"
    ERROR = "error"
