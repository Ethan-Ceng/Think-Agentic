from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TenantContext:
    tenant_id: UUID
    user_id: UUID | None = None
    member_id: UUID | None = None
    roles: tuple[str, ...] = ()
