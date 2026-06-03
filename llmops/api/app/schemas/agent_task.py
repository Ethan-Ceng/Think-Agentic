from pydantic import BaseModel, Field


class GetAgentTasksWithPageRequest(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    status: str = "all"
    user_id: str = "all"
    search_word: str = ""
