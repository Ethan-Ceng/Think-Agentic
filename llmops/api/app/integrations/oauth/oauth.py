from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OAuthUserInfo:
    id: str
    name: str
    email: str


@dataclass
class OAuth(ABC):
    client_id: str
    client_secret: str
    redirect_uri: str

    @abstractmethod
    def get_provider(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_authorization_url(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_access_token(self, code: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_raw_user_info(self, token: str) -> dict:
        raise NotImplementedError

    def get_user_info(self, token: str) -> OAuthUserInfo:
        raw_info = self.get_raw_user_info(token)
        return self._transform_user_info(raw_info)

    @abstractmethod
    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        raise NotImplementedError

