from app.integrations.oauth import GithubOAuth, OAuthUserInfo


def test_github_authorization_url() -> None:
    oauth = GithubOAuth(client_id="client-id", client_secret="secret", redirect_uri="https://example.test/callback")

    url = oauth.get_authorization_url()

    assert url.startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=client-id" in url
    assert "redirect_uri=https%3A%2F%2Fexample.test%2Fcallback" in url
    assert "scope=user%3Aemail" in url


def test_github_user_info_transform_falls_back_to_no_reply_email() -> None:
    oauth = GithubOAuth(client_id="client-id", client_secret="secret", redirect_uri="https://example.test/callback")

    user = oauth._transform_user_info({"id": 1, "login": "octo", "name": "Octo", "email": None})

    assert user == OAuthUserInfo(id="1", name="Octo", email="1+octo@user.no-reply.github.com")

