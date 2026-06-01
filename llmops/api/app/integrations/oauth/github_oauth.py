import urllib.parse
from typing import Any

import httpx

from .oauth import OAuth, OAuthUserInfo


class GithubOAuth(OAuth):
    _AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    _ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
    _USER_INFO_URL = "https://api.github.com/user"
    _EMAIL_INFO_URL = "https://api.github.com/user/emails"

    def get_provider(self) -> str:
        return "github"

    def get_authorization_url(self) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "user:email",
        }
        return f"{self._AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def get_access_token(self, code: str) -> str:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        headers = {"Accept": "application/json"}

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(self._ACCESS_TOKEN_URL, data=data, headers=headers)
        resp.raise_for_status()
        resp_json = resp.json()

        access_token = resp_json.get("access_token")
        if not access_token:
            raise ValueError(f"Github OAuth authorization failed: {resp_json}")

        return str(access_token)

    def get_raw_user_info(self, token: str) -> dict[str, Any]:
        headers = {"Authorization": f"token {token}"}

        with httpx.Client(timeout=15.0) as client:
            user_resp = client.get(self._USER_INFO_URL, headers=headers)
            user_resp.raise_for_status()
            raw_info = user_resp.json()

            email_resp = client.get(self._EMAIL_INFO_URL, headers=headers)
            email_resp.raise_for_status()
            email_info = email_resp.json()

        primary_email = next((email for email in email_info if email.get("primary")), None)
        return {**raw_info, "email": primary_email.get("email") if primary_email else None}

    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        email = raw_info.get("email")
        if not email:
            email = f"{raw_info.get('id')}+{raw_info.get('login')}@user.no-reply.github.com"

        return OAuthUserInfo(
            id=str(raw_info.get("id")),
            name=str(raw_info.get("name")),
            email=str(email),
        )

