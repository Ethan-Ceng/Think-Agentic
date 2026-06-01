from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ai_service, get_current_account, get_db_session
from app.models.account import Account
from app.schemas.ai import GenerateSuggestedQuestionsRequest, OptimizePromptRequest
from app.services.ai_service import AIService
from app.shared.response import compact_generate_response, success_json

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/optimize-prompt")
def optimize_prompt(
    req: OptimizePromptRequest,
    _: Account = Depends(get_current_account),
    svc: AIService = Depends(get_ai_service),
):
    return compact_generate_response(svc.optimize_prompt(req.prompt))


@router.post("/suggested-questions")
def generate_suggested_questions(
    req: GenerateSuggestedQuestionsRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AIService = Depends(get_ai_service),
):
    questions = svc.generate_suggested_questions_from_message_id(session, req.message_id, current_user)
    return success_json(questions)
