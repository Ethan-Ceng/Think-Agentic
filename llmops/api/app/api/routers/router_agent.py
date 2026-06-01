from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_current_tenant, get_db_session, get_router_agent_manager_service
from app.core.tenant import TenantContext
from app.models.account import Account
from app.schemas.router_agent import (
    BindRouterWorkerRequest,
    CreateAppWorkerAgentRequest,
    CreateRouterAgentRequest,
    RouterAgentResponse,
    RouterBindingResponse,
    RouterManagerRunRequest,
    RouterManagerRunResponse,
)
from app.services.router_agent_manager_service import RouterAgentManagerService
from app.shared.response import success_json

router = APIRouter(prefix="/router-agents", tags=["router-agent"])


@router.post("")
def create_router_agent(
    req: CreateRouterAgentRequest,
    session: Session = Depends(get_db_session),
    tenant: TenantContext = Depends(get_current_tenant),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    agent, version = svc.create_router_agent(
        session,
        tenant_id=tenant.tenant_id,
        created_by=current_user.id,
        name=req.name,
        description=req.description,
        model_config=req.llm_model_config,
        prompt_config=req.prompt_config,
        router_config=req.router_config,
        policies=req.policies,
        status=req.status,
    )
    return success_json(
        RouterAgentResponse(
            id=agent.id,
            version_id=version.id,
            name=agent.name,
            status=agent.status,
            runtime_type=agent.runtime_type,
            target_ref_type=agent.target_ref_type,
            target_ref_id=agent.target_ref_id,
        ).model_dump()
    )


@router.post("/workers/from-app")
def create_worker_from_app(
    req: CreateAppWorkerAgentRequest,
    session: Session = Depends(get_db_session),
    tenant: TenantContext = Depends(get_current_tenant),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    agent, version = svc.create_worker_agent_from_app(
        session,
        tenant_id=tenant.tenant_id,
        app_id=req.app_id,
        account=current_user,
        status=req.status,
    )
    return success_json(
        RouterAgentResponse(
            id=agent.id,
            version_id=version.id,
            name=agent.name,
            status=agent.status,
            runtime_type=agent.runtime_type,
            target_ref_type=agent.target_ref_type,
            target_ref_id=agent.target_ref_id,
        ).model_dump()
    )


@router.post("/{router_agent_id}/workers")
def bind_router_worker(
    router_agent_id: UUID,
    req: BindRouterWorkerRequest,
    session: Session = Depends(get_db_session),
    tenant: TenantContext = Depends(get_current_tenant),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    binding = svc.bind_worker(
        session,
        tenant_id=tenant.tenant_id,
        router_agent_id=router_agent_id,
        worker_agent_id=req.worker_agent_id,
        priority=req.priority,
        conditions=req.conditions,
        enabled=req.enabled,
    )
    return success_json(
        RouterBindingResponse(
            id=binding.id,
            router_agent_id=binding.router_agent_id,
            worker_agent_id=binding.worker_agent_id,
            enabled=binding.enabled,
            priority=binding.priority,
            conditions=binding.conditions,
        ).model_dump()
    )


@router.post("/{router_agent_id}/manager-runs")
def create_manager_run(
    router_agent_id: UUID,
    req: RouterManagerRunRequest,
    session: Session = Depends(get_db_session),
    tenant: TenantContext = Depends(get_current_tenant),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    user_input = {"query": req.query, **req.input}
    result = svc.create_manager_run(
        session,
        tenant_id=tenant.tenant_id,
        router_agent_id=router_agent_id,
        user_input=user_input,
        requested_worker_ids=req.worker_agent_ids,
        user_id=current_user.id,
        session_id=req.session_id,
        conversation_id=req.conversation_id,
    )
    if req.execute:
        result = svc.execute_manager_run_steps(session, run=result, account=current_user)
    return success_json(
        RouterManagerRunResponse(
            task_id=result.task.id,
            plan_id=result.plan.id,
            trace_id=result.trace_id,
            status=result.task.status,
            steps=[
                {
                    "id": step.id,
                    "step_key": step.step_key,
                    "worker_agent_id": step.worker_agent_id,
                    "status": step.status,
                    "dependencies": step.dependencies,
                }
                for step in result.steps
            ],
        ).model_dump()
    )
