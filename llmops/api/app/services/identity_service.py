from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.rbac import MemberRole, Permission, Role, RolePermission
from app.models.tenant import Tenant, TenantMember
from app.schemas.identity import BootstrapTenantRequest


@dataclass
class BootstrapTenantResult:
    tenant: Tenant
    account: Account
    member: TenantMember


class IdentityService:
    def bootstrap_tenant(self, session: Session, req: BootstrapTenantRequest) -> BootstrapTenantResult:
        account = session.query(Account).filter(Account.email == req.owner_email).one_or_none()
        if account is None:
            account = Account(name=req.owner_name, email=req.owner_email)
            session.add(account)
            session.flush()

        tenant = session.query(Tenant).filter(Tenant.name == req.tenant_name).one_or_none()
        if tenant is None:
            tenant = Tenant(name=req.tenant_name)
            session.add(tenant)
            session.flush()

        member = (
            session.query(TenantMember)
            .filter(TenantMember.tenant_id == tenant.id, TenantMember.user_id == account.id)
            .one_or_none()
        )
        if member is None:
            member = TenantMember(tenant_id=tenant.id, user_id=account.id, role="owner")
            session.add(member)
            session.flush()

        owner_role = self._ensure_owner_role(session, tenant)
        self._ensure_member_role(session, tenant, member, owner_role)

        return BootstrapTenantResult(tenant=tenant, account=account, member=member)

    def _ensure_owner_role(self, session: Session, tenant: Tenant) -> Role:
        role = session.query(Role).filter(Role.tenant_id == tenant.id, Role.code == "owner").one_or_none()
        if role is None:
            role = Role(tenant_id=tenant.id, code="owner", name="Owner", description="Tenant owner")
            session.add(role)
            session.flush()

        permission = session.query(Permission).filter(Permission.code == "*").one_or_none()
        if permission is None:
            permission = Permission(code="*", name="All permissions", resource="*", action="*")
            session.add(permission)
            session.flush()

        role_permission = (
            session.query(RolePermission)
            .filter(RolePermission.role_id == role.id, RolePermission.permission_id == permission.id)
            .one_or_none()
        )
        if role_permission is None:
            session.add(RolePermission(tenant_id=tenant.id, role_id=role.id, permission_id=permission.id))
            session.flush()

        return role

    def _ensure_member_role(self, session: Session, tenant: Tenant, member: TenantMember, role: Role) -> None:
        member_role = (
            session.query(MemberRole)
            .filter(MemberRole.member_id == member.id, MemberRole.role_id == role.id)
            .one_or_none()
        )
        if member_role is None:
            session.add(MemberRole(tenant_id=tenant.id, member_id=member.id, role_id=role.id))
            session.flush()
