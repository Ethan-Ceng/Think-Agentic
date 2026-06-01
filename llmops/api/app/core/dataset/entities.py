from enum import StrEnum

DEFAULT_DATASET_DESCRIPTION_FORMATTER = "Use the {name} knowledge base when you need relevant managed knowledge."
ALLOWED_IMAGE_EXTENSION = ["jpg", "jpeg", "png", "webp", "gif", "svg"]
ALLOWED_DOCUMENT_EXTENSION = ["txt", "markdown", "md", "pdf", "html", "htm", "xlsx", "xls", "doc", "docx", "csv"]


class ProcessType(StrEnum):
    AUTOMATIC = "automatic"
    CUSTOM = "custom"


DEFAULT_PROCESS_RULE = {
    "mode": ProcessType.CUSTOM.value,
    "rule": {
        "pre_process_rules": [
            {"id": "remove_extra_space", "enabled": True},
            {"id": "remove_url_and_email", "enabled": True},
        ],
        "segment": {
            "separators": [
                "\n\n",
                "\n",
                "。|！|？",
                r"\.\s|\!\s|\?\s",
                r";\s|；\s",
                r",\s|，\s",
                " ",
                "",
            ],
            "chunk_size": 500,
            "chunk_overlap": 50,
        },
    },
}


class DocumentStatus(StrEnum):
    WAITING = "waiting"
    PARSING = "parsing"
    SPLITTING = "splitting"
    INDEXING = "indexing"
    COMPLETED = "completed"
    ERROR = "error"


class SegmentStatus(StrEnum):
    WAITING = "waiting"
    INDEXING = "indexing"
    COMPLETED = "completed"
    ERROR = "error"


class RetrievalStrategy(StrEnum):
    FULL_TEXT = "full_text"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class RetrievalSource(StrEnum):
    HIT_TESTING = "hit_testing"
    APP = "app"
