from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.app import AppConfigType, AppStatus
from app.core.builtin_apps import BuiltinAppManager
from app.core.exceptions import NotFoundException
from app.models.account import Account
from app.models.app import App, AppConfigVersion
from app.services.base_service import BaseService


@dataclass
class BuiltinAppService(BaseService):
    builtin_app_manager: BuiltinAppManager = field(default_factory=BuiltinAppManager)

    def get_categories(self):
        return self.builtin_app_manager.get_categories()

    def get_builtin_apps(self):
        return self.builtin_app_manager.get_builtin_apps()

    def add_builtin_app_to_space(self, session: Session, builtin_app_id: str, account: Account) -> App:
        builtin_app = self.builtin_app_manager.get_builtin_app(builtin_app_id)
        if builtin_app is None:
            raise NotFoundException("Builtin app does not exist")

        app = self.create(
            session,
            App,
            account_id=account.id,
            status=AppStatus.DRAFT.value,
            name=builtin_app.name,
            icon=builtin_app.icon,
            description=builtin_app.description,
        )
        draft_app_config = self.create(
            session,
            AppConfigVersion,
            app_id=app.id,
            model_config=builtin_app.language_model_config,
            config_type=AppConfigType.DRAFT.value,
            dialog_round=builtin_app.dialog_round,
            preset_prompt=builtin_app.preset_prompt,
            tools=builtin_app.tools,
            retrieval_config=builtin_app.retrieval_config,
            long_term_memory=builtin_app.long_term_memory,
            opening_statement=builtin_app.opening_statement,
            opening_questions=builtin_app.opening_questions,
            speech_to_text=builtin_app.speech_to_text,
            text_to_speech=builtin_app.text_to_speech,
            review_config=builtin_app.review_config,
            suggested_after_answer=builtin_app.suggested_after_answer,
        )
        return self.update(session, app, draft_app_config_id=draft_app_config.id)
