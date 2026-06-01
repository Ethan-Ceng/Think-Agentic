#!/usr/bin/env python
# -*- coding: utf-8 -*-
from collections.abc import Callable

from app.extensions.database import get_db
from app.repositories.db_uow import DBUnitOfWork
from app.repositories.uow import IUnitOfWork


def get_uow() -> IUnitOfWork:
    return DBUnitOfWork(session_factory=get_db().session_factory)


UowFactory = Callable[[], IUnitOfWork]
