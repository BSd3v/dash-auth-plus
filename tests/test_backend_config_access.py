from types import SimpleNamespace

from dash import Dash

from dash_auth_plus.auth import Auth
from dash_auth_plus.public_routes import add_public_routes, get_public_routes


class DummyAuth(Auth):
    def is_authorized(self):
        return True

    def login_request(self):
        return None


def test_auth_config_helpers_support_non_flask_server_config():
    auth = object.__new__(DummyAuth)
    auth.app = SimpleNamespace(
        config={"SESSION_COOKIE_SECURE": True},
        server=SimpleNamespace(),
    )

    assert auth._session_cookie_secure is True
    auth._set_secret_key("test-secret")
    assert auth._get_secret_key() == "test-secret"


def test_public_routes_stored_in_dash_config():
    app = Dash(__name__)
    add_public_routes(app, ["/public"])

    public_routes = get_public_routes(app)
    assert public_routes.test("/public")
