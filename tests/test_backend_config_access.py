import asyncio
import sys
import types
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from dash import Dash
from flask import Flask, session
from werkzeug.routing import Map, Rule

from dash_auth_plus.auth import Auth
from dash_auth_plus.oidc_auth import OIDCAuth
from dash_auth_plus.public_routes import add_public_routes, get_public_routes


class DummyAuth(Auth):
    def is_authorized(self):
        return True

    def login_request(self):
        return None


class DenyAuth(Auth):
    def is_authorized(self):
        return False

    def login_request(self):
        return "login"


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


def test_sync_flask_session_helpers_support_flask_request_context():
    auth = cast(Any, object.__new__(DummyAuth))
    auth.app = SimpleNamespace(config={}, server=SimpleNamespace())
    app = Flask(__name__)
    app.secret_key = "Test!"

    with app.test_request_context("/", method="GET"):
        auth._sync_flask_session({"user": {"email": "a.b@mail.com"}, "idp": "oidc"})
        assert session["user"]["email"] == "a.b@mail.com"
        assert session["idp"] == "oidc"

        auth._clear_flask_session()
        assert "user" not in session
        assert "idp" not in session


def test_auth_protect_layouts_allows_page_container_routing_callbacks():
    captured = {}
    request = SimpleNamespace(
        path="/_dash-update-component",
        get_json=lambda: {
            "inputs": [{"property": "pathname", "value": "/private"}],
            "outputs": [{"id": "_pages_content", "property": "children"}],
        },
    )
    backend = SimpleNamespace(
        server_type="flask",
        request_adapter=lambda: request,
        before_request=lambda func: captured.setdefault("hook", func),
    )
    app = SimpleNamespace(config={}, server=SimpleNamespace(), backend=backend)

    with patch("dash_auth_plus.auth.protect_layouts"):
        auth = DenyAuth(
            app,
            auth_protect_layouts=True,
            page_container="_pages_content",
        )

    assert auth is app._dash_auth_plus_auth
    assert captured["hook"]() is None


def test_oidc_auth_accepts_fastapi_backend():
    added_routes = []
    backend = SimpleNamespace(
        server_type="fastapi",
        before_request=lambda func: None,
        add_url_rule=lambda *args, **kwargs: added_routes.append((args, kwargs)),
    )
    app = SimpleNamespace(config={}, server=SimpleNamespace(), backend=backend)
    fake_oauth = SimpleNamespace(_registry={}, _clients={})
    fake_fastapi = types.SimpleNamespace(Request=object)
    fake_dash_fastapi = types.SimpleNamespace(
        set_current_request=lambda request: "token",
        reset_current_request=lambda token: None,
    )

    with patch("dash_auth_plus.oidc_auth.OAuth", return_value=fake_oauth):
        with patch.dict(
            sys.modules,
            {
                "fastapi": fake_fastapi,
                "dash.backends._fastapi": fake_dash_fastapi,
            },
        ):
            OIDCAuth(app, secret_key="Test")

    assert [kwargs["endpoint"] for _, kwargs in added_routes] == [
        "oidc_login",
        "oidc_logout",
        "oidc_callback",
    ]


def test_fastapi_backend_uses_async_callback_hook():
    captured = {}

    async def get_json():
        return {
            "inputs": [{"property": "pathname", "value": "/public"}],
            "outputs": [{"id": "_pages_content", "property": "children"}],
        }

    request = SimpleNamespace(path="/_dash-update-component", get_json=get_json)
    backend = SimpleNamespace(
        server_type="fastapi",
        request_adapter=lambda: request,
        before_request=lambda func: captured.setdefault("hook", func),
    )
    app = SimpleNamespace(config={}, server=SimpleNamespace(), backend=backend)
    add_public_routes(app, ["/public"])

    auth = DenyAuth(app, page_container="_pages_content")

    assert auth is app._dash_auth_plus_auth
    assert asyncio.run(captured["hook"]()) is None
