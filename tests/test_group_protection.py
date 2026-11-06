import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import dash
from dash_auth_plus import list_groups, check_groups, protected
from dash_auth_plus.group_protection import protected_callback
from flask import Flask, session


def test_gp001_list_groups():
    app = Flask(__name__)
    app.secret_key = "Test!"
    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
            "tenant": "ABC",
        }
        assert list_groups() == ["default"]
        assert list_groups(groups_key="tenant", groups_str_split=",") == ["ABC"]


def test_gp002_check_groups():
    app = Flask(__name__)
    app.secret_key = "Test!"
    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
            "tenant": "ABC",
        }
        assert check_groups(["default"]) is True
        assert check_groups(["other"]) is False
        assert check_groups(["default", "other"]) is True
        assert check_groups(["other", "default"], check_type="all_of") is False
        assert check_groups(["default"], check_type="all_of") is True
        assert check_groups(["other", "default"], check_type="none_of") is False
        assert check_groups(["other"], check_type="none_of") is True


def test_gp003_protected():
    app = Flask(__name__)
    app.secret_key = "Test!"

    def func():
        return "success"

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
            "tenant": "ABC",
        }
        f0 = protected(
            unauthenticated_output="unauthenticated",
            missing_permissions_output="forbidden",
            groups=["default"],
        )(func)
        assert f0() == "success"

        f1 = protected(
            unauthenticated_output="unauthenticated",
            missing_permissions_output="forbidden",
            groups=["admin"],
        )(func)
        assert f1() == "forbidden"

        del session["user"]
        assert f1() == "unauthenticated"


def test_gp004_protected_async():
    app = Flask(__name__)
    app.secret_key = "Test!"

    async def async_func():
        return "success"

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
            "tenant": "ABC",
        }

        # Authorized: user is in the required group → async callback is awaited
        f_authorized = protected(
            unauthenticated_output="unauthenticated",
            missing_permissions_output="forbidden",
            groups=["default"],
        )(async_func)
        assert asyncio.run(f_authorized()) == "success"

        # Unauthorized: user is not in the required group → static forbidden output
        f_forbidden = protected(
            unauthenticated_output="unauthenticated",
            missing_permissions_output="forbidden",
            groups=["admin"],
        )(async_func)
        assert asyncio.run(f_forbidden()) == "forbidden"

        # Unauthenticated: no session user → static unauthenticated output
        del session["user"]
        assert asyncio.run(f_forbidden()) == "unauthenticated"


def test_gp005_callable_groups_without_path():
    """Callable groups that don't accept 'path' must not receive it (backwards compat)."""
    app = Flask(__name__)
    app.secret_key = "Test!"

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        def groups_no_path():
            return ["default"]

        # This would raise TypeError before the fix if path was unconditionally passed
        assert check_groups(groups_no_path, path="/some/path") is True

        def groups_only_kwargs(**kwargs):
            return ["default"]

        assert check_groups(groups_only_kwargs, path="/some/path") is True


def test_gp006_callable_groups_with_path():
    """Callable groups that accept 'path' should receive it."""
    app = Flask(__name__)
    app.secret_key = "Test!"
    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["admin"],
        }

        received_path = {}

        def groups_with_path(path=None):
            received_path["path"] = path
            return ["admin"]

        assert check_groups(groups_with_path, path="/dashboard") is True
        assert received_path["path"] == "/dashboard"


def test_gp007_callable_groups_path_in_group_lookup_precedence():
    """Explicit group_lookup['path'] should be preserved for callable groups."""
    app = Flask(__name__)
    app.secret_key = "Test!"
    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["admin"],
        }

        received_path = {}

        def groups_with_path(path=None):
            received_path["path"] = path
            return ["admin"]

        assert (
            check_groups(
                groups_with_path,
                path="/from-arg",
                group_lookup={"path": "/from-lookup"},
            )
            is True
        )
        assert received_path["path"] == "/from-lookup"


def test_gp008_protected_async_callable_outputs():
    """Callable unauthenticated/missing_permissions outputs must not receive
    unexpected keyword arguments (e.g. ``path``) in the async branch."""
    app = Flask(__name__)
    app.secret_key = "Test!"

    async def async_func():
        return "success"

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        # Lambda (no-arg callable) as missing_permissions_output must not raise
        f_forbidden = protected(
            unauthenticated_output=lambda: "unauthenticated",
            missing_permissions_output=lambda: "forbidden",
            groups=["admin"],
        )(async_func)
        assert asyncio.run(f_forbidden()) == "forbidden"

        # Lambda as unauthenticated_output must not raise
        del session["user"]
        assert asyncio.run(f_forbidden()) == "unauthenticated"


def test_gp009_protected_async_async_callable_outputs():
    """Async callable outputs should be awaited based on the returned value
    being awaitable, not solely on ``iscoroutinefunction``."""
    app = Flask(__name__)
    app.secret_key = "Test!"

    async def async_func():
        return "success"

    async def async_unauth():
        return "unauthenticated"

    async def async_forbidden():
        return "forbidden"

    with app.test_request_context("/", method="GET"):
        # Unauthorized path with async callable output
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }
        f_forbidden = protected(
            unauthenticated_output=async_unauth,
            missing_permissions_output=async_forbidden,
            groups=["admin"],
        )(async_func)
        assert asyncio.run(f_forbidden()) == "forbidden"

        # Unauthenticated path with async callable output
        del session["user"]
        assert asyncio.run(f_forbidden()) == "unauthenticated"


def test_gp010_protected_async_callable_outputs_with_path():
    app = Flask(__name__)
    app.secret_key = "Test!"

    async def async_func():
        return "success"

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        f_forbidden = protected(
            unauthenticated_output=lambda path: f"unauthenticated:{path}",
            missing_permissions_output=lambda path: f"forbidden:{path}",
            groups=["admin"],
            path="/triage-path",
        )(async_func)
        assert asyncio.run(f_forbidden()) == "forbidden:/triage-path"

        del session["user"]
        assert asyncio.run(f_forbidden()) == "unauthenticated:/triage-path"


def test_gp011_protected_async_callable_outputs_with_path_kwargs():
    app = Flask(__name__)
    app.secret_key = "Test!"

    async def async_func():
        return "success"

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        def missing_permissions_output(**kwargs):
            return f"forbidden:{kwargs['path']}"

        def unauthenticated_output(**kwargs):
            return f"unauthenticated:{kwargs['path']}"

        f_forbidden = protected(
            unauthenticated_output=unauthenticated_output,
            missing_permissions_output=missing_permissions_output,
            groups=["admin"],
            path="/triage-kwargs",
        )(async_func)
        assert asyncio.run(f_forbidden()) == "forbidden:/triage-kwargs"

        del session["user"]
        assert asyncio.run(f_forbidden()) == "unauthenticated:/triage-kwargs"


def test_gp012_protected_sync_callable_outputs_no_args():
    app = Flask(__name__)
    app.secret_key = "Test!"

    def sync_func():
        return "success"

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        f_forbidden = protected(
            unauthenticated_output=lambda: "unauthenticated",
            missing_permissions_output=lambda: "forbidden",
            groups=["admin"],
        )(sync_func)
        assert f_forbidden() == "forbidden"

        del session["user"]
        assert f_forbidden() == "unauthenticated"


def test_gp013_protected_sync_callable_outputs_with_path_and_kwargs():
    app = Flask(__name__)
    app.secret_key = "Test!"

    def sync_func():
        return "success"

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        f_forbidden_with_path = protected(
            unauthenticated_output=lambda path: f"unauthenticated:{path}",
            missing_permissions_output=lambda path: f"forbidden:{path}",
            groups=["admin"],
            path="/triage-sync",
        )(sync_func)
        assert f_forbidden_with_path() == "forbidden:/triage-sync"

        del session["user"]
        assert f_forbidden_with_path() == "unauthenticated:/triage-sync"

        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        def missing_permissions_output(**kwargs):
            return f"forbidden:{kwargs['path']}"

        def unauthenticated_output(**kwargs):
            return f"unauthenticated:{kwargs['path']}"

        f_forbidden_with_kwargs = protected(
            unauthenticated_output=unauthenticated_output,
            missing_permissions_output=missing_permissions_output,
            groups=["admin"],
            path="/triage-sync-kwargs",
        )(sync_func)
        assert f_forbidden_with_kwargs() == "forbidden:/triage-sync-kwargs"

        del session["user"]
        assert f_forbidden_with_kwargs() == "unauthenticated:/triage-sync-kwargs"


def test_gp014_callable_groups_signature_failure_does_not_inject_path():
    """If inspect.signature fails, check_groups should not inject path kwarg."""
    app = Flask(__name__)
    app.secret_key = "Test!"
    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        def groups_no_path():
            return ["default"]

        with patch("dash_auth_plus.group_protection.signature", side_effect=TypeError):
            assert check_groups(groups_no_path, path="/should-not-be-passed") is True


def test_gp015_callable_groups_posonly_path_in_lookup_raises_clear_error():
    app = Flask(__name__)
    app.secret_key = "Test!"
    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        def groups_with_posonly_path(path, /):
            return ["default"]

        with pytest.raises(TypeError, match="positional-only 'path' parameter"):
            check_groups(groups_with_posonly_path, group_lookup={"path": "/from-lookup"})


def test_gp016_list_groups_falls_back_to_dash_auth_session():
    app = Flask(__name__)
    app.secret_key = "Test!"

    fake_dash_app = SimpleNamespace(
        _dash_auth_plus_auth=SimpleNamespace(
            _get_session=lambda: {
                "user": {
                    "email": "a.b@mail.com",
                    "groups": ["admin"],
                    "tenant": "ABC",
                }
            }
        )
    )

    with app.test_request_context("/", method="GET"):
        with patch(
            "dash_auth_plus.group_protection.dash.get_app",
            return_value=fake_dash_app,
        ):
            assert list_groups() == ["admin"]
            assert list_groups(groups_key="tenant", groups_str_split=",") == ["ABC"]


def test_gp017_check_groups_falls_back_to_dash_auth_session():
    app = Flask(__name__)
    app.secret_key = "Test!"

    fake_dash_app = SimpleNamespace(
        _dash_auth_plus_auth=SimpleNamespace(
            _get_session=lambda: {
                "user": {
                    "email": "a.b@mail.com",
                    "groups": ["admin"],
                }
            }
        )
    )

    with app.test_request_context("/", method="GET"):
        with patch(
            "dash_auth_plus.group_protection.dash.get_app",
            return_value=fake_dash_app,
        ):
            assert check_groups(["admin"]) is True
            assert check_groups(["viewer"]) is False


def test_gp018_protected_async_generator_authorized_streams_values():
    app = Flask(__name__)
    app.secret_key = "Test!"

    async def stream_func():
        yield "step-1"
        yield "step-2"

    async def collect(async_iterable):
        values = []
        async for item in async_iterable:
            values.append(item)
        return values

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        wrapped = protected(
            unauthenticated_output="unauthenticated",
            missing_permissions_output="forbidden",
            groups=["default"],
        )(stream_func)

        assert asyncio.run(collect(wrapped())) == ["step-1", "step-2"]


def test_gp019_protected_async_generator_uses_fallback_without_manual_auth_check():
    app = Flask(__name__)
    app.secret_key = "Test!"

    async def stream_func():
        yield "should-not-run"

    async def collect(async_iterable):
        values = []
        async for item in async_iterable:
            values.append(item)
        return values

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        wrapped = protected(
            unauthenticated_output="unauthenticated",
            missing_permissions_output="forbidden",
            groups=["admin"],
        )(stream_func)

        assert asyncio.run(collect(wrapped())) == ["forbidden"]

        del session["user"]
        assert asyncio.run(collect(wrapped())) == ["unauthenticated"]


def test_gp020_protected_callback_async_generator_unauth_yields_default_fallback():
    app = Flask(__name__)
    app.secret_key = "Test!"

    async def collect(async_iterable):
        values = []
        async for item in async_iterable:
            values.append(item)
        return values

    with app.test_request_context("/", method="GET"):
        with patch("dash_auth_plus.group_protection.dash.callback") as callback_mock:
            callback_mock.side_effect = lambda *a, **k: (lambda f: f)

            @protected_callback()
            async def stream_func():
                yield "should-not-run"

            assert asyncio.run(collect(stream_func())) == [dash.no_update]


def test_gp021_protected_callback_async_generator_forbidden_yields_default_fallback():
    app = Flask(__name__)
    app.secret_key = "Test!"

    async def collect(async_iterable):
        values = []
        async for item in async_iterable:
            values.append(item)
        return values

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
        }

        with patch("dash_auth_plus.group_protection.dash.callback") as callback_mock:
            callback_mock.side_effect = lambda *a, **k: (lambda f: f)

            @protected_callback(groups=["admin"])
            async def stream_func():
                yield "should-not-run"

            assert asyncio.run(collect(stream_func())) == [dash.no_update]


def test_gp022_protected_callback_registers_callback_id_for_middleware_allowlist():
    app = Flask(__name__)
    app.secret_key = "Test!"

    with app.test_request_context("/", method="GET"):
        fake_dash_app = SimpleNamespace(_dash_auth_plus_public_callbacks=[])

        with patch("dash_auth_plus.group_protection.get_app", return_value=fake_dash_app):
            callback_map = {}

            def fake_callback(*_a, **_k):
                def decorator(f):
                    callback_map["callback-id-1"] = {"callback": f}
                    return f

                return decorator

            with patch("dash_auth_plus.group_protection.dash.callback", side_effect=fake_callback):
                with patch(
                    "dash_auth_plus.group_protection.GLOBAL_CALLBACK_MAP",
                    callback_map,
                ):

                    @protected_callback()
                    async def stream_func():
                        yield "x"

                    assert "callback-id-1" in fake_dash_app._dash_auth_plus_public_callbacks
                    assert "callback-id-1" in fake_dash_app._dash_auth_plus_protected_callbacks


@pytest.mark.parametrize("flask_session", [True, False])
@pytest.mark.parametrize("fallback_type", ["default", "static", "async", "stream"])
def test_protected_stream_rechecks_authentication_before_each_yield(
    flask_session, fallback_type
):
    app = Flask(__name__)
    app.secret_key = "Test!"
    auth = SimpleNamespace(
        is_authorized=Mock(side_effect=[True, False]),
        _get_session=lambda: {"user": {"email": "a.b@mail.com", "groups": []}},
    )
    fake_dash_app = SimpleNamespace(_dash_auth_plus_auth=auth)
    closed = []

    async def async_fallback():
        return "unauthenticated"

    async def stream_fallback():
        yield "unauthenticated"

    fallback_kwargs = {
        "default": {},
        "static": {"unauthenticated_output": "unauthenticated"},
        "async": {"unauthenticated_output": async_fallback},
        "stream": {"unauthenticated_output": stream_fallback},
    }[fallback_type]

    async def collect(stream):
        return [item async for item in stream]

    with app.test_request_context("/_dash-update-component", method="POST"):
        if flask_session:
            session["user"] = {"email": "a.b@mail.com", "groups": []}
        with patch("dash_auth_plus.group_protection.get_app", return_value=fake_dash_app):
            with patch(
                "dash_auth_plus.group_protection.dash.get_app",
                return_value=fake_dash_app,
            ):
                with patch("dash_auth_plus.group_protection.dash.callback") as callback:
                    callback.side_effect = lambda *a, **k: (lambda f: f)

                    @protected_callback(**fallback_kwargs)
                    async def stream_func():
                        try:
                            yield "step-1"
                            yield "must-not-leak"
                            yield "must-not-run"
                        finally:
                            closed.append(True)

                    expected_fallback = (
                        dash.no_update if fallback_type == "default" else "unauthenticated"
                    )
                    assert asyncio.run(collect(stream_func())) == [
                        "step-1",
                        expected_fallback,
                    ]
                    assert auth.is_authorized.call_count == 2
                    assert closed == [True]


@pytest.mark.parametrize("initial_state", ["unauthenticated", "forbidden", "allowed"])
def test_protected_stream_initial_authorization_precedes_rechecks(initial_state):
    app = Flask(__name__)
    app.secret_key = "Test!"
    auth = SimpleNamespace(is_authorized=Mock(return_value=True))
    fake_dash_app = SimpleNamespace(_dash_auth_plus_auth=auth)
    called = []

    async def collect(stream):
        return [item async for item in stream]

    with app.test_request_context("/_dash-update-component", method="POST"):
        if initial_state != "unauthenticated":
            session["user"] = {
                "email": "a.b@mail.com",
                "groups": ["admin"] if initial_state == "allowed" else [],
            }
        with patch("dash_auth_plus.group_protection.get_app", return_value=fake_dash_app):
            with patch("dash_auth_plus.group_protection.dash.callback") as callback:
                callback.side_effect = lambda *a, **k: (lambda f: f)

                @protected_callback(
                    groups=["admin"],
                    unauthenticated_output="unauthenticated",
                    missing_permissions_output="forbidden",
                )
                async def stream_func():
                    called.append(True)
                    yield "step-1"
                    yield "step-2"

                expected = (
                    ["step-1", "step-2"]
                    if initial_state == "allowed"
                    else [initial_state]
                )
                assert asyncio.run(collect(stream_func())) == expected
                assert called == ([True] if initial_state == "allowed" else [])
                assert auth.is_authorized.call_count == (
                    2 if initial_state == "allowed" else 0
                )


@pytest.mark.parametrize("protected_stream", [True, False])
def test_stream_session_loss_without_auth_backend(protected_stream):
    app = Flask(__name__)
    app.secret_key = "Test!"

    async def collect(stream):
        return [item async for item in stream]

    with app.test_request_context("/_dash-update-component", method="POST"):
        session["user"] = {"email": "a.b@mail.com", "groups": []}
        with patch(
            "dash_auth_plus.group_protection.get_app",
            return_value=SimpleNamespace(),
        ):
            with patch("dash_auth_plus.group_protection.dash.callback") as callback:
                callback.side_effect = lambda *a, **k: (lambda f: f)
                decorator = protected_callback if protected_stream else protected

                @decorator(unauthenticated_output="unauthenticated")
                async def stream_func():
                    yield "step-1"
                    del session["user"]
                    yield "step-2"

                assert asyncio.run(collect(stream_func())) == [
                    "step-1",
                    "unauthenticated" if protected_stream else "step-2",
                ]
