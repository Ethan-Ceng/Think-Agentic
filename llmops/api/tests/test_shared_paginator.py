from sqlalchemy import Column, Integer, String, create_engine, select
from sqlalchemy.orm import Session, declarative_base

from app.shared.paginator import Paginator, PaginatorReq

Base = declarative_base()


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    name = Column(String(32), nullable=False)


def test_paginator_supports_legacy_query_api() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([Item(name=f"item-{idx}") for idx in range(5)])
        session.commit()

        paginator = Paginator(session, PaginatorReq(page=2, page_size=2))
        items = paginator.paginate(session.query(Item).order_by(Item.id))

    assert [item.name for item in items] == ["item-2", "item-3"]
    assert paginator.total_record == 5
    assert paginator.total_page == 3


def test_paginator_supports_sqlalchemy_select_api() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all([Item(name=f"item-{idx}") for idx in range(3)])
        session.commit()

        paginator = Paginator(session, PaginatorReq(page=1, page_size=2))
        items = paginator.paginate(select(Item).order_by(Item.id))

    assert [item.name for item in items] == ["item-0", "item-1"]
    assert paginator.total_record == 3
    assert paginator.total_page == 2

