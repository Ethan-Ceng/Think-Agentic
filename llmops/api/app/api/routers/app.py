from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_app_service, get_current_account, get_db_session, get_router_agent_manager_service
from app.models.account import Account
from app.schemas.app import (
    AppPageResponse,
    AppResponse,
    BindPlannerWorkerRequest,
    CreateAppRequest,
    DebugChatRequest,
    FallbackHistoryToDraftRequest,
    GetAppsWithPageRequest,
    GetDebugConversationMessagesWithPageRequest,
    GetPublishHistoriesWithPageRequest,
    PatchCapabilitySummaryRequest,
    PlannerPreflightRequest,
    PublishHistoryResponse,
    RefreshCapabilitySummaryRequest,
    RoutingPolicyRequest,
    UpdateAppRequest,
    UpdateDebugConversationSummaryRequest,
    UpdatePlannerWorkerBindingRequest,
)
from app.schemas.conversation import MessageResponse
from app.services.app_service import AppService
from app.services.router_agent_manager_service import RouterAgentManagerService
from app.shared.response import compact_generate_response, success_json, success_message

router = APIRouter(prefix="/apps", tags=["app"])


@router.post("")
def create_app(
    req: CreateAppRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    app = svc.create_app(session, req, current_user)
    return success_json({"id": app.id})


@router.get("")
def get_apps(
    req: GetAppsWithPageRequest = Depends(),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    apps, total_record, total_page = svc.get_apps_with_page(session, req, current_user)
    return success_json(
        {
            "list": [
                AppPageResponse.from_app(app, svc.get_active_config_for_page(session, app)).model_dump()
                for app in apps
            ],
            "total_page": total_page,
            "total_record": total_record,
            "current_page": req.page,
            "page_size": req.page_size,
        }
    )


@router.get("/{app_id}")
def get_app(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    app = svc.get_app(session, app_id, current_user)
    return success_json(AppResponse.from_app(app, svc.get_or_create_draft_config(session, app)).model_dump())


@router.put("/{app_id}")
def update_app(
    app_id: UUID,
    req: UpdateAppRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    svc.update_app(session, app_id, req, current_user)
    return success_message("Update app success")


@router.post("/{app_id}/copy")
def copy_app(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    app = svc.copy_app(session, app_id, current_user)
    return success_json({"id": app.id})


@router.delete("/{app_id}")
def delete_app(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    svc.delete_app(session, app_id, current_user)
    return success_message("Delete app success")


@router.get("/{app_id}/planner/workers")
def get_planner_workers(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    return success_json(
        {"list": svc.list_planner_worker_bindings(session, planner_app_id=app_id, account=current_user)}
    )


@router.post("/{app_id}/planner/workers")
def bind_planner_worker(
    app_id: UUID,
    req: BindPlannerWorkerRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    binding = svc.bind_worker_app_to_planner(
        session,
        planner_app_id=app_id,
        worker_app_id=req.worker_app_id,
        account=current_user,
        priority=req.priority,
        conditions=req.conditions,
        enabled=req.enabled,
    )
    return success_json({"id": str(binding.id)})


@router.patch("/{app_id}/planner/workers/{binding_id}")
def update_planner_worker(
    app_id: UUID,
    binding_id: UUID,
    req: UpdatePlannerWorkerBindingRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    svc.update_planner_worker_binding(
        session,
        planner_app_id=app_id,
        binding_id=binding_id,
        account=current_user,
        enabled=req.enabled,
        priority=req.priority,
        conditions=req.conditions,
    )
    return success_message("Update planner worker binding success")


@router.delete("/{app_id}/planner/workers/{binding_id}")
def delete_planner_worker(
    app_id: UUID,
    binding_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    svc.delete_planner_worker_binding(session, planner_app_id=app_id, binding_id=binding_id, account=current_user)
    return success_message("Delete planner worker binding success")


@router.get("/{app_id}/capability-summary")
def get_app_capability_summary(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    return success_json(svc.get_app_worker_capability_summary(session, app_id=app_id, account=current_user))


@router.post("/{app_id}/capability-summary/refresh")
def refresh_app_capability_summary(
    app_id: UUID,
    req: RefreshCapabilitySummaryRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    return success_json(
        svc.refresh_app_worker_capability_summary(
            session,
            app_id=app_id,
            account=current_user,
            preserve_manual_overrides=req.preserve_manual_overrides,
        )
    )


@router.patch("/{app_id}/capability-summary")
def patch_app_capability_summary(
    app_id: UUID,
    req: PatchCapabilitySummaryRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    return success_json(
        svc.patch_app_worker_capability_summary(
            session,
            app_id=app_id,
            account=current_user,
            manual_overrides=req.manual_overrides,
        )
    )


@router.get("/{app_id}/planner/routing-policy")
def get_planner_routing_policy(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    return success_json(svc.get_planner_routing_policy(session, planner_app_id=app_id, account=current_user))


@router.put("/{app_id}/planner/routing-policy")
def save_planner_routing_policy(
    app_id: UUID,
    req: RoutingPolicyRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    return success_json(
        svc.save_planner_routing_policy(
            session,
            planner_app_id=app_id,
            account=current_user,
            routing_policy=req.routing_policy,
        )
    )


@router.post("/{app_id}/planner/routing-policy/validate")
def validate_planner_routing_policy(
    app_id: UUID,
    req: RoutingPolicyRequest,
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    _ = app_id, current_user
    return success_json(svc.validate_planner_routing_policy(req.routing_policy))


@router.post("/{app_id}/planner/preflight")
def preflight_planner_workers(
    app_id: UUID,
    req: PlannerPreflightRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: RouterAgentManagerService = Depends(get_router_agent_manager_service),
):
    return success_json(
        svc.preflight_planner_workers(
            session,
            planner_app_id=app_id,
            account=current_user,
            message=req.message,
            input_modalities=req.input_modalities,
            candidate_worker_ids=req.candidate_worker_ids,
        )
    )


@router.get("/{app_id}/draft-app-config")
def get_draft_app_config(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    return success_json(svc.get_draft_app_config(session, app_id, current_user))


@router.put("/{app_id}/draft-app-config")
@router.post("/{app_id}/draft-app-config")
async def update_draft_app_config(
    app_id: UUID,
    request: Request,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    svc.update_draft_app_config(session, app_id, await request.json(), current_user)
    return success_message("Update app draft config success")


@router.post("/{app_id}/publish")
def publish_app(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    svc.publish_draft_app_config(session, app_id, current_user)
    return success_message("Publish app success")


@router.post("/{app_id}/cancel-publish")
def cancel_publish_app(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    svc.cancel_publish_app_config(session, app_id, current_user)
    return success_message("Cancel app publish success")


@router.post("/{app_id}/fallback-history")
def fallback_history_to_draft(
    app_id: UUID,
    req: FallbackHistoryToDraftRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    svc.fallback_history_to_draft(session, app_id, req.app_config_version_id, current_user)
    return success_message("Fallback app config history success")


@router.get("/{app_id}/publish-histories")
def get_publish_histories(
    app_id: UUID,
    req: GetPublishHistoriesWithPageRequest = Depends(),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    versions, total_record, total_page = svc.get_publish_histories_with_page(session, app_id, req, current_user)
    return success_json(
        {
            "list": [PublishHistoryResponse.from_version(version).model_dump() for version in versions],
            "total_page": total_page,
            "total_record": total_record,
            "current_page": req.page,
            "page_size": req.page_size,
        }
    )


@router.get("/{app_id}/published-config")
def get_published_config(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    return success_json(svc.get_published_config(session, app_id, current_user))


@router.post("/{app_id}/regenerate-web-app-token")
def regenerate_web_app_token(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    return success_json({"token": svc.regenerate_web_app_token(session, app_id, current_user)})


@router.get("/{app_id}/debug-conversation-summary")
def get_debug_conversation_summary(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    return success_json({"summary": svc.get_debug_conversation_summary(session, app_id, current_user)})


@router.put("/{app_id}/debug-conversation-summary")
def update_debug_conversation_summary(
    app_id: UUID,
    req: UpdateDebugConversationSummaryRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    svc.update_debug_conversation_summary(session, app_id, req.summary, current_user)
    return success_message("Update app debug conversation summary success")


@router.delete("/{app_id}/debug-conversation")
def delete_debug_conversation(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    svc.delete_debug_conversation(session, app_id, current_user)
    return success_message("Delete app debug conversation success")


@router.post("/{app_id}/debug-chat")
def debug_chat(
    app_id: UUID,
    req: DebugChatRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    return compact_generate_response(svc.debug_chat(session, app_id, req, current_user))


@router.post("/{app_id}/stop-debug-chat/{task_id}")
def stop_debug_chat(
    app_id: UUID,
    task_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    svc.stop_debug_chat(session, app_id, task_id, current_user)
    return success_message("Stop app debug chat success")


@router.get("/{app_id}/debug-conversation-messages")
def get_debug_conversation_messages(
    app_id: UUID,
    req: GetDebugConversationMessagesWithPageRequest = Depends(),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    messages, total_record, total_page = svc.get_debug_conversation_messages_with_page(
        session,
        app_id,
        req,
        current_user,
    )
    return success_json(
        {
            "list": [MessageResponse.from_message(message).model_dump() for message in messages],
            "total_page": total_page,
            "total_record": total_record,
            "current_page": req.page,
            "page_size": req.page_size,
        }
    )


@router.get("/{app_id}/conversations/messages")
def get_debug_conversation_messages_legacy_path(
    app_id: UUID,
    current_page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    created_at: int = Query(0, ge=0),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AppService = Depends(get_app_service),
):
    req = GetDebugConversationMessagesWithPageRequest(
        page=current_page,
        page_size=page_size,
        created_at=created_at,
    )
    messages, total_record, total_page = svc.get_debug_conversation_messages_with_page(
        session,
        app_id,
        req,
        current_user,
    )
    return success_json(
        {
            "list": [MessageResponse.from_message(message).model_dump() for message in messages],
            "total_page": total_page,
            "total_record": total_record,
            "current_page": current_page,
            "page_size": page_size,
        }
    )
