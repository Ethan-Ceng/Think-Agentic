from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_dataset_service, get_db_session
from app.models.account import Account
from app.schemas.dataset import (
    CreateDatasetRequest,
    DatasetQueryResponse,
    DatasetResponse,
    HitRequest,
    UpdateDatasetRequest,
)
from app.services.dataset_service import DatasetService
from app.shared.response import success_json, success_message

router = APIRouter(prefix="/datasets", tags=["dataset"])


@router.get("")
def get_datasets(
    current_page: int = Query(default=1, ge=1, le=9999),
    page_size: int = Query(default=20, ge=1, le=50),
    search_word: str = Query(default=""),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DatasetService = Depends(get_dataset_service),
):
    datasets, total_record, total_page = svc.get_datasets_with_page(
        session,
        current_user,
        search_word,
        current_page,
        page_size,
    )
    stats = svc.get_dataset_stats(session, [dataset.id for dataset in datasets])
    return success_json(
        {
            "list": [
                DatasetResponse.from_dataset(dataset, stats.get(dataset.id)).model_dump()
                for dataset in datasets
            ],
            "total_page": total_page,
            "total_record": total_record,
            "current_page": current_page,
            "page_size": page_size,
        }
    )


@router.post("")
def create_dataset(
    req: CreateDatasetRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DatasetService = Depends(get_dataset_service),
):
    svc.create_dataset(session, req.name, str(req.icon), req.description, current_user)
    return success_message("Create dataset success")


@router.get("/{dataset_id}")
def get_dataset(
    dataset_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DatasetService = Depends(get_dataset_service),
):
    dataset = svc.get_dataset(session, dataset_id, current_user)
    stats = svc.get_dataset_stats(session, [dataset.id])
    return success_json(DatasetResponse.from_dataset(dataset, stats.get(dataset.id)).model_dump())


@router.put("/{dataset_id}")
def update_dataset(
    dataset_id: UUID,
    req: UpdateDatasetRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DatasetService = Depends(get_dataset_service),
):
    svc.update_dataset(session, dataset_id, req.name, str(req.icon), req.description, current_user)
    return success_message("Update dataset success")


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DatasetService = Depends(get_dataset_service),
):
    svc.delete_dataset(session, dataset_id, current_user)
    return success_message("Delete dataset success")


@router.get("/{dataset_id}/queries")
def get_dataset_queries(
    dataset_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DatasetService = Depends(get_dataset_service),
):
    queries = svc.get_dataset_queries(session, dataset_id, current_user)
    return success_json([DatasetQueryResponse.from_query(query).model_dump() for query in queries])


@router.post("/{dataset_id}/hit")
def hit_dataset(
    dataset_id: UUID,
    req: HitRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: DatasetService = Depends(get_dataset_service),
):
    return success_json(
        svc.hit(
            session,
            dataset_id,
            req.query,
            req.retrieval_strategy.value,
            req.k,
            req.score,
            current_user,
        )
    )
