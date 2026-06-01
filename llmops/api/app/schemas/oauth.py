from pydantic import BaseModel


class AuthorizeRequest(BaseModel):
    code: str

