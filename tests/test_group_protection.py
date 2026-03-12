import asyncio

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


def test_gp005_protected_async_callable_outputs():
    """Async protected functions with no-arg callable outputs (sync and async)."""
    app = Flask(__name__)
    app.secret_key = "Test!"

    async def async_func():
        return "success"

    def sync_unauth():
        return "unauthenticated_callable"

    def sync_forbidden():
        return "forbidden_callable"

    async def async_unauth():
        return "unauthenticated_async_callable"

    async def async_forbidden():
        return "forbidden_async_callable"

    with app.test_request_context("/", method="GET"):
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
            "tenant": "ABC",
        }

        # --- sync no-arg callables ---
        f_authorized = protected(
            unauthenticated_output=sync_unauth,
            missing_permissions_output=sync_forbidden,
            groups=["default"],
        )(async_func)
        assert asyncio.run(f_authorized()) == "success"

        f_forbidden = protected(
            unauthenticated_output=sync_unauth,
            missing_permissions_output=sync_forbidden,
            groups=["admin"],
        )(async_func)
        assert asyncio.run(f_forbidden()) == "forbidden_callable"

        del session["user"]
        assert asyncio.run(f_forbidden()) == "unauthenticated_callable"

        # --- async no-arg callables ---
        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
            "tenant": "ABC",
        }

        f_authorized_async = protected(
            unauthenticated_output=async_unauth,
            missing_permissions_output=async_forbidden,
            groups=["default"],
        )(async_func)
        assert asyncio.run(f_authorized_async()) == "success"

        f_forbidden_async = protected(
            unauthenticated_output=async_unauth,
            missing_permissions_output=async_forbidden,
            groups=["admin"],
        )(async_func)
        assert asyncio.run(f_forbidden_async()) == "forbidden_async_callable"

        del session["user"]
        assert asyncio.run(f_forbidden_async()) == "unauthenticated_async_callable"


def test_gp006_protected_callable_outputs_with_path():
    app = Flask(__name__)
    app.secret_key = "Test!"

    def func():
        return "success"

    async def async_func():
        return "success"

    def sync_unauth(path):
        return f"unauth:{path}"

    def sync_forbidden(path):
        return f"forbidden:{path}"

    async def async_unauth(path):
        return f"unauth_async:{path}"

    async def async_forbidden(path):
        return f"forbidden_async:{path}"

    def sync_unauth_no_args():
        return "unauth_no_args"

    with app.test_request_context("/", method="GET"):
        # Sync protected output callables can receive path for triage
        f_sync = protected(
            unauthenticated_output=sync_unauth,
            missing_permissions_output=sync_forbidden,
            groups=["admin"],
            path="/triage-sync",
        )(func)

        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
            "tenant": "ABC",
        }
        assert f_sync() == "forbidden:/triage-sync"

        del session["user"]
        assert f_sync() == "unauth:/triage-sync"

        # Async protected output callables can receive path for triage
        f_async = protected(
            unauthenticated_output=async_unauth,
            missing_permissions_output=async_forbidden,
            groups=["admin"],
            path="/triage-async",
        )(async_func)

        session["user"] = {
            "email": "a.b@mail.com",
            "groups": ["default"],
            "tenant": "ABC",
        }
        assert asyncio.run(f_async()) == "forbidden_async:/triage-async"

        del session["user"]
        assert asyncio.run(f_async()) == "unauth_async:/triage-async"

        # Backward compatibility: no-arg callables still work even when path is set
        f_no_arg = protected(
            unauthenticated_output=sync_unauth_no_args,
            groups=["admin"],
            path="/triage-unused",
        )(func)
        assert f_no_arg() == "unauth_no_args"
