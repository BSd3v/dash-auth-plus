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


def test_gp006_protected_async_async_callable_outputs():
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
