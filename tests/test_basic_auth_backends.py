import asyncio
import base64

import pytest
from dash import Dash, Input, Output, dcc, html

from dash_auth_plus import BasicAuth, protected_callback


@pytest.mark.parametrize("backend", ["flask", "quart", "fastapi"])
@pytest.mark.parametrize("auth_func", [False, True])
def test_basic_auth_protected_callback_session(backend, auth_func):
    if backend == "quart":
        server = pytest.importorskip("quart").Quart(__name__)
    elif backend == "fastapi":
        server = pytest.importorskip("fastapi").FastAPI()
    else:
        server = True
    app = Dash(__name__, server=server)
    output_id = f"output-{backend}-{auth_func}"
    app.layout = html.Div([dcc.Input(id="input"), html.Div(id=output_id)])

    @protected_callback(
        Output(output_id, "children"),
        Input("input", "value"),
        groups=["admin"],
        unauthenticated_output="unauthenticated",
        missing_permissions_output="forbidden",
    )
    def update_output(value):
        return value

    credentials = {"admin": "test-password", "user": "test-password"}
    BasicAuth(
        app,
        auth_func=(
            (lambda username, password: credentials.get(username) == password)
            if auth_func else None
        ),
        username_password_list=None if auth_func else credentials,
        user_groups={"admin": ["admin"]},
        secret_key="test-session-key",
    )
    payload = {
        "output": f"{output_id}.children",
        "outputs": {"id": output_id, "property": "children"},
        "inputs": [{"id": "input", "property": "value", "value": "success"}],
        "changedPropIds": ["input.value"],
        "state": [],
    }

    async def exercise_client():
        for username, password, expected in [
            ("admin", "test-password", "success"),
            ("admin", "test-password", "success"),
            ("user", "test-password", "forbidden"),
            ("admin", "wrong-password", "unauthenticated"),
            (None, None, "unauthenticated"),
        ]:
            headers = {}
            if username is not None:
                encoded = base64.b64encode(
                    f"{username}:{password}".encode()
                ).decode()
                headers["Authorization"] = f"Basic {encoded}"
            if backend == "quart":
                client = app.server.test_client()
                await client.get("/", headers=headers)
                response = await client.post(
                    "/_dash-update-component", json=payload, headers=headers
                )
                result = await response.get_json()
            else:
                client = (
                    pytest.importorskip("fastapi.testclient").TestClient(app.server)
                    if backend == "fastapi" else app.server.test_client()
                )
                client.get("/", headers=headers)
                response = client.post(
                    "/_dash-update-component", json=payload, headers=headers
                )
                result = (
                    response.json() if backend == "fastapi" else response.get_json()
                )
            assert response.status_code == 200
            assert result["response"][output_id]["children"] == expected

        for header in ["******", "Basic !", "Basic bm9jb2xvbg=="]:
            response = client.post(
                "/_dash-update-component",
                json=payload,
                headers={"Authorization": header},
            )
            if backend == "quart":
                response = await response
                result = await response.get_json()
            else:
                result = (
                    response.json() if backend == "fastapi" else response.get_json()
                )
            assert response.status_code == 200
            assert result["response"][output_id]["children"] == "unauthenticated"

    asyncio.run(exercise_client())
