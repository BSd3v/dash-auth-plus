import asyncio
from unittest.mock import patch

from dash_auth_plus import list_groups, check_groups, protected
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
