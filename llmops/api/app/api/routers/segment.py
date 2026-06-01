from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_db_session, get_segment_service
from app.models.account import Account
from app.schemas.segment import (
    CreateSegmentRequest,
    SegmentResponse,
    UpdateSegmentEnabledRequest,
    UpdateSegmentRequest,
)
from app.services.segment_service import SegmentService
from app.shared.response import success_json, success_message

router = APIRouter(
    prefix="/datasets/{dataset_id}/documents/{document_id}/segments",
    tags=["segment"],
)


@router.post("")
def create_segment(
    dataset_id: UUID,
    document_id: UUID,
    req: CreateSegmentRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: SegmentService = Depends(get_segment_service),
):
    segment = svc.create_segment(session, dataset_id, document_id, req.content, req.keywords, current_user)
    return success_json(SegmentResponse.from_segment(segment).model_dump())


@router.get("")
def get_segments(
    dataset_id: UUID,
    document_id: UUID,
    current_page: int = Query(default=1, ge=1, le=9999),
    page_size: int = Query(default=20, ge=1, le=50),
    search_word: str = Query(default=""),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: SegmentService = Depends(get_segment_service),
):
    segments, total_record, total_page = svc.get_segments_with_page(
        session,
        dataset_id,
        document_id,
        current_user,
        search_word,
        current_page,
        page_size,
    )
    return success_json(
        {
            "list": [SegmentResponse.from_segment(segment).model_dump() for segment in segments],
            "total_page": total_page,
            "total_record": total_record,
            "current_page": current_page,
            "page_size": page_size,
        }
    )


@router.get("/{segment_id}")
def get_segment(
    dataset_id: UUID,
    document_id: UUID,
    segment_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: SegmentService = Depends(get_segment_service),
):
    segment = svc.get_segment(session, dataset_id, document_id, segment_id, current_user)
    return success_json(SegmentResponse.from_segment(segment).model_dump())


@router.put("/{segment_id}")
def update_segment(
    dataset_id: UUID,
    document_id: UUID,
    segment_id: UUID,
    req: UpdateSegmentRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: SegmentService = Depends(get_segment_service),
):
    segment = svc.update_segment(
        session,
        dataset_id,
        document_id,
        segment_id,
        req.content,
        req.keywords,
        current_user,
    )
    return success_json(SegmentResponse.from_segment(segment).model_dump())


@router.put("/{segment_id}/enabled")
def update_segment_enabled(
    dataset_id: UUID,
    document_id: UUID,
    segment_id: UUID,
    req: UpdateSegmentEnabledRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: SegmentService = Depends(get_segment_service),
):
    svc.update_segment_enabled(session, dataset_id, document_id, segment_id, req.enabled, current_user)
    return success_message("Update segment enabled state success")


@router.delete("/{segment_id}")
def delete_segment(
    dataset_id: UUID,
    document_id: UUID,
    segment_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: SegmentService = Depends(get_segment_service),
):
    svc.delete_segment(session, dataset_id, document_id, segment_id, current_user)
    return success_message("Delete segment success")

