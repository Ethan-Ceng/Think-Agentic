from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base

from app.infrastructure.db import SQLAlchemy

Base = declarative_base()


class FacadeItem(Base):
    __tablename__ = "facade_items"

    id = Column(Integer, primary_key=True)
    name = Column(String(32), nullable=False)


def test_sqlalchemy_facade_supports_legacy_session_and_auto_commit() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        db = SQLAlchemy(session)
        with db.auto_commit():
            db.session.add(FacadeItem(name="item"))

        item = db.session.query(FacadeItem).one()

    assert item.name == "item"


def test_sqlalchemy_facade_supports_legacy_paginate() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([FacadeItem(name=f"item-{idx}") for idx in range(3)])
        session.commit()

        db = SQLAlchemy(session)
        page = db.paginate(db.session.query(FacadeItem).order_by(FacadeItem.id), page=2, per_page=2)

    assert [item.name for item in page.items] == ["item-2"]
    assert page.total == 3
    assert page.page == 2
    assert page.per_page == 2

