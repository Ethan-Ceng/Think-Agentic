from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_agent_task_service, get_current_account, get_db_session
from app.models.account import Account
from app.schemas.agent_task import GetAgentTaskMetricsRequest, GetAgentTasksWithPageRequest
from app.services.agent_task_service import AgentTaskService
from app.shared.response import success_json

router = APIRouter(prefix="/apps/{app_id}/agent-tasks", tags=["agent_tasks"])


@router.get("")
def get_app_agent_tasks(
    app_id: UUID,
    req: GetAgentTasksWithPageRequest = Depends(),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AgentTaskService = Depends(get_agent_task_service),
):
    tasks, total_record, total_page, users = svc.list_app_tasks_with_page(
        session,
        app_id=app_id,
        account=current_user,
        page=req.page,
        page_size=req.page_size,
        status=req.status,
        user_id=req.user_id,
        search_word=req.search_word,
    )
    return success_json(
        {
            "list": tasks,
            "total_page": total_page,
            "total_record": total_record,
            "current_page": req.page,
            "page_size": req.page_size,
            "users": users,
        }
    )


@router.get("/metrics")
def get_app_agent_task_metrics(
    app_id: UUID,
    req: GetAgentTaskMetricsRequest = Depends(),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AgentTaskService = Depends(get_agent_task_service),
):
    return success_json(
        svc.get_app_task_runtime_metrics(
            session,
            app_id=app_id,
            account=current_user,
            from_ts=req.from_ts,
            to_ts=req.to_ts,
            status=req.status,
            user_id=req.user_id,
            router_agent_id=req.router_agent_id,
            worker_agent_id=req.worker_agent_id,
            group_by=req.group_by,
        )
    )


@router.get("/{task_id}")
def get_app_agent_task_detail(
    app_id: UUID,
    task_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AgentTaskService = Depends(get_agent_task_service),
):
    return success_json(svc.get_app_task_detail(session, app_id=app_id, task_id=task_id, account=current_user))
