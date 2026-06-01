from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import FailException


class BaseService:
    def create(self, session: Session, model: Any, **kwargs: Any) -> Any:
        model_instance = model(**kwargs)
        session.add(model_instance)
        session.flush()
        session.refresh(model_instance)
        return model_instance

    def delete(self, session: Session, model_instance: Any) -> Any:
        session.delete(model_instance)
        session.flush()
        return model_instance

    def update(self, session: Session, model_instance: Any, **kwargs: Any) -> Any:
        for field, value in kwargs.items():
            if not hasattr(model_instance, field):
                raise FailException("Update field does not exist")
            setattr(model_instance, field, value)
        session.flush()
        session.refresh(model_instance)
        return model_instance

    def get(self, session: Session, model: Any, primary_key: Any) -> Any | None:
        return session.get(model, primary_key)

