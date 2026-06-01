from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_db_session, get_document_service
from app.models.account import Account
from app.schemas.document import (
    CreateDocumentsRequest,
    CreateDocumentsResponse,
    DocumentResponse,
    UpdateDocumentEnabledRequest,
    UpdateDocumentNameRequest,
)
from app.services.document_service import DocumentService
from app.shared.response import success_json, success_message

router = APIRouter(prefix="/datasets/{dataset_id}/documents", tags=["document"])


@router.post("")
def create_documents(
    dataset_id: UUID,
    req: CreateDocumentsRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DocumentService = Depends(get_document_service),
):
    documents, batch = svc.create_documents(
        session,
        dataset_id,
        upload_file_ids=req.upload_file_ids,
        process_type=req.process_type,
        rule=req.rule,
        account=current_user,
    )
    return success_json(
        CreateDocumentsResponse(
            documents=[DocumentResponse.from_document(document) for document in documents],
            batch=batch,
        ).model_dump()
    )


@router.get("")
def get_documents(
    dataset_id: UUID,
    current_page: int = Query(default=1, ge=1, le=9999),
    page_size: int = Query(default=20, ge=1, le=50),
    search_word: str = Query(default=""),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DocumentService = Depends(get_document_service),
):
    documents, total_record, total_page = svc.get_documents_with_page(
        session,
        dataset_id,
        current_user,
        search_word,
        current_page,
        page_size,
    )
    return success_json(
        {
            "list": [
                DocumentResponse.from_document(
                    document,
                    svc.get_document_hit_count(session, document.id),
                ).model_dump()
                for document in documents
            ],
            "total_page": total_page,
            "total_record": total_record,
            "current_page": current_page,
            "page_size": page_size,
        }
    )


@router.get("/status/{batch}")
def get_documents_status(
    dataset_id: UUID,
    batch: str,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DocumentService = Depends(get_document_service),
):
    return success_json(svc.get_documents_status(session, dataset_id, batch, current_user))


@router.get("/{document_id}")
def get_document(
    dataset_id: UUID,
    document_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DocumentService = Depends(get_document_service),
):
    document = svc.get_document(session, dataset_id, document_id, current_user)
    hit_count = svc.get_document_hit_count(session, document.id)
    return success_json(DocumentResponse.from_document(document, hit_count).model_dump())


@router.put("/{document_id}/name")
def update_document_name(
    dataset_id: UUID,
    document_id: UUID,
    req: UpdateDocumentNameRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DocumentService = Depends(get_document_service),
):
    svc.update_document(session, dataset_id, document_id, current_user, name=req.name)
    return success_message("Update document name success")


@router.put("/{document_id}/enabled")
def update_document_enabled(
    dataset_id: UUID,
    document_id: UUID,
    req: UpdateDocumentEnabledRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DocumentService = Depends(get_document_service),
):
    svc.update_document_enabled(session, dataset_id, document_id, req.enabled, current_user)
    return success_message("Update document enabled state success")


@router.delete("/{document_id}")
def delete_document(
    dataset_id: UUID,
    document_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DocumentService = Depends(get_document_service),
):
    svc.delete_document(session, dataset_id, document_id, current_user)
    return success_message("Delete document success")
