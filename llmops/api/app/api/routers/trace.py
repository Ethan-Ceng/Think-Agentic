from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, get_db_session, get_trace_service
from app.core.tenant import TenantContext
from app.schemas.trace import TraceEventResponse
from app.services.trace_service import TraceService
from app.shared.response import success_json

router = APIRouter(prefix="/traces", tags=["trace"])


@router.get("/{trace_id}")
def list_trace_events(
    trace_id: str,
    session: Session = Depends(get_db_session),
    tenant: TenantContext = Depends(get_current_tenant),
    svc: TraceService = Depends(get_trace_service),
):
    events = svc.list_for_trace(session, tenant_id=tenant.tenant_id, trace_id=trace_id)
    return success_json({"list": [TraceEventResponse.from_event(event).model_dump() for event in events]})
