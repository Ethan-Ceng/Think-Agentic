from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_db_session, get_workflow_service
from app.models.account import Account
from app.schemas.workflow import (
    CreateWorkflowRequest,
    GetWorkflowsWithPageRequest,
    UpdateWorkflowRequest,
    WorkflowResponse,
)
from app.services.workflow_service import WorkflowService
from app.shared.paginator import PageModel
from app.shared.response import compact_generate_response, success_json, success_message

router = APIRouter(prefix="/workflows", tags=["workflow"])


@router.post("")
def create_workflow(
    req: CreateWorkflowRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WorkflowService = Depends(get_workflow_service),
):
    workflow = svc.create_workflow(session, req, current_user)
    return success_json({"id": workflow.id})


@router.get("")
def get_workflows(
    req: GetWorkflowsWithPageRequest = Depends(),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WorkflowService = Depends(get_workflow_service),
):
    workflows, paginator = svc.get_workflows_with_page(session, req, current_user)
    return success_json(
        PageModel(
            list=[
                WorkflowResponse.from_workflow(workflow, use_draft_graph=False).model_dump()
                for workflow in workflows
            ],
            paginator=paginator,
        )
    )


@router.get("/{workflow_id}")
def get_workflow(
    workflow_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WorkflowService = Depends(get_workflow_service),
):
    workflow = svc.get_workflow(session, workflow_id, current_user)
    return success_json(WorkflowResponse.from_workflow(workflow).model_dump())


@router.put("/{workflow_id}")
def update_workflow(
    workflow_id: UUID,
    req: UpdateWorkflowRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WorkflowService = Depends(get_workflow_service),
):
    svc.update_workflow(session, workflow_id, req, current_user)
    return success_message("Update workflow success")


@router.delete("/{workflow_id}")
def delete_workflow(
    workflow_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WorkflowService = Depends(get_workflow_service),
):
    svc.delete_workflow(session, workflow_id, current_user)
    return success_message("Delete workflow success")


@router.get("/{workflow_id}/draft-graph")
def get_draft_graph(
    workflow_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WorkflowService = Depends(get_workflow_service),
):
    return success_json(svc.get_draft_graph(session, workflow_id, current_user))


@router.put("/{workflow_id}/draft-graph")
async def update_draft_graph(
    workflow_id: UUID,
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WorkflowService = Depends(get_workflow_service),
):
    draft_graph: dict[str, Any] = await request.json() or {"nodes": [], "edges": []}
    svc.update_draft_graph(session, workflow_id, draft_graph, current_user)
    return success_message("Update workflow draft graph success")


@router.post("/{workflow_id}/debug")
async def debug_workflow(
    workflow_id: UUID,
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WorkflowService = Depends(get_workflow_service),
):
    inputs: dict[str, Any] = await request.json() or {}
    return compact_generate_response(svc.debug_workflow(session, workflow_id, inputs, current_user))


@router.post("/{workflow_id}/publish")
def publish_workflow(
    workflow_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WorkflowService = Depends(get_workflow_service),
):
    svc.publish_workflow(session, workflow_id, current_user)
    return success_message("Publish workflow success")


@router.post("/{workflow_id}/cancel-publish")
def cancel_publish_workflow(
    workflow_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WorkflowService = Depends(get_workflow_service),
):
    svc.cancel_publish_workflow(session, workflow_id, current_user)
    return success_message("Cancel workflow publish success")

