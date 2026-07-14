from pydantic import BaseModel, Field


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: str | None = None


class UpdateFileRequest(BaseModel):
    name: str | None = None
    parent_id: str | None = None


class BatchMoveRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1)
    parent_id: str | None = None


class BatchDeleteRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1)


class StorageTestRequest(BaseModel):
    provider: str
