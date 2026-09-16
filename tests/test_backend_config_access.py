import asyncio
from types import SimpleNamespace
from typing import Any, cast

from dash import Dash
from werkzeug.routing import Map, Rule

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


def test_normalized_request_path_strips_url_base_pathname_prefix():
    auth = cast(Any, object.__new__(DummyAuth))
    auth.app = SimpleNamespace(
        config={"url_base_pathname": "/dash/"},
        server=SimpleNamespace(),
    )

    assert auth._normalized_request_path("/dash/public") == "/public"
    assert auth._normalized_request_path("/dash") == "/"
    assert auth._normalized_request_path("/public") == "/public"


def test_path_matches_map_with_prefixed_path():
    auth = cast(Any, object.__new__(DummyAuth))
    auth.app = SimpleNamespace(
        config={"url_base_pathname": "/dash/"},
        server=SimpleNamespace(),
    )
    route_map = Map([Rule("/public")]).bind("")

    assert auth._path_matches_map(route_map, "/dash/public") is True


def test_get_callback_body_async_awaits_quart_style_get_json():
    auth = cast(Any, object.__new__(DummyAuth))
    auth.app = SimpleNamespace(config={}, server=SimpleNamespace())

    class AsyncReq:
        async def get_json(self):
            return {"output": "x", "inputs": []}

    body = asyncio.run(auth._get_callback_body_async(AsyncReq()))
    assert body == {"output": "x", "inputs": []}
