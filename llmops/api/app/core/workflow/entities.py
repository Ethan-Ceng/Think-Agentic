from enum import StrEnum

WORKFLOW_CONFIG_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
WORKFLOW_CONFIG_DESCRIPTION_MAX_LENGTH = 1024


class WorkflowStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class WorkflowResultStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class NodeType(StrEnum):
    START = "start"
    LLM = "llm"
    TOOL = "tool"
    CODE = "code"
    DATASET_RETRIEVAL = "dataset_retrieval"
    HTTP_REQUEST = "http_request"
    TEMPLATE_TRANSFORM = "template_transform"
    END = "end"


class NodeStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


DEFAULT_WORKFLOW_CONFIG = {
    "graph": {},
    "draft_graph": {
        "nodes": [],
        "edges": [],
    },
}
