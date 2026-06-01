from uuid import UUID

from pydantic import BaseModel, Field


class BootstrapTenantRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=255)
    owner_email: str = Field(min_length=3, max_length=255)
    owner_name: str = Field(min_length=1, max_length=255)


class AccountResponse(BaseModel):
    id: UUID
    name: str
    email: str
    status: str


class TenantResponse(BaseModel):
    id: UUID
    name: str
    status: str


class TenantMemberResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    role: str
    status: str


class BootstrapTenantResponse(BaseModel):
    tenant: TenantResponse
    account: AccountResponse
    member: TenantMemberResponse


class CurrentWorkspaceResponse(BaseModel):
    tenant: TenantResponse
