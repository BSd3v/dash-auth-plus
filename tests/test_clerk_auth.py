from selenium.webdriver.common.keys import Keys
from dash import Dash, html, dcc, page_container
from dash_auth_plus import ClerkAuth
import os
import pytest
import flask


def spinup_app():
    from dash import Dash, html, dcc, page_container
    from dash_auth_plus import DashAuthComponents

    app = Dash(
        __name__, use_pages=True, pages_folder="", suppress_callback_exceptions=True
    )

    auth = ClerkAuth(
        app,
        secret_key="aStaticSecretKey!",
        log_signins=True,
        public_routes=["/", "/user/<user_id>/public"],
    )

    app.layout = html.Div(
        [
            DashAuthComponents.ClerkProvider(
                [], publishableKey=os.getenv("CLERK_PUBLISHABLE_KEY")
            ),
            html.Div(
                [
                    dcc.Link("Home", href="/"),
                    dcc.Link("John Doe", href="/user/john_doe/public"),
                    dcc.Link("Logout", href="/logout", refresh=True),
                ],
                style={
                    "display": "flex",
                    "gap": "1rem",
                    "background": "lightgray",
                    "padding": "0.5rem 1rem",
                },
            ),
            page_container,
        ],
        style={"display": "flex", "flexDirection": "column"},
    )

    from dash import Input, Output, html, register_page
    from dash_auth_plus import public_callback

    home_layout = [
        html.H1("Home Page"),
        html.Button("Click me", id="home-button"),
        html.Div(id="home-contents"),
    ]

    register_page("home", "/", layout=home_layout)

    # Note the use of public callback here rather than the default Dash callback
    @public_callback(
        Output("home-contents", "children"),
        Input("home-button", "n_clicks"),
    )
    def home(n_clicks):
        if not n_clicks:
            return "You haven't clicked the button."
        return "You clicked the button {} times".format(n_clicks)

    from dash import html, dcc, register_page

    def user_layout(user_id: str, **kwargs):
        return [
            html.H1(f"User {user_id} (public)"),
            dcc.Link("Authenticated user content", href=f"/user/{user_id}/private"),
        ]

    register_page("user", path_template="/user/<user_id>/public", layout=user_layout)

    from dash import html, register_page

    def user_private(user_id: str, **kwargs):
        return [
            html.H1(f"User {user_id} (authenticated only)"),
            html.Div("Members-only information"),
        ]

    register_page(
        "private", path_template="/user/<user_id>/private", layout=user_private
    )
    return app, auth


@pytest.mark.skipif(
    not all(
        [
            os.getenv("CLERK_SECRET_KEY"),
            os.getenv("CLERK_DOMAIN"),
            os.getenv("CLERK_PUBLISHABLE_KEY"),
            os.getenv("CLERK_TEST_USER"),
            os.getenv("CLERK_TEST_PASSWORD"),
        ]
    ),
    reason="Clerk credentials not available (requires CLERK_SECRET_KEY, CLERK_DOMAIN, CLERK_PUBLISHABLE_KEY, CLERK_TEST_USER, CLERK_TEST_PASSWORD)",
)
def test_clerk_auth_flow(dash_duo):
    app, auth = spinup_app()

    dash_duo.start_server(app)
    auth.allowed_parties = [dash_duo.server_url]

    # Go to the home page (public)
    dash_duo.wait_for_text_to_equal("h1", "Home Page", timeout=10)

    # Navigate to the protected page
    dash_duo.driver.get(dash_duo.server_url + "/user/john_doe/private")

    # Should be redirected to Clerk login (look for a known Clerk element or URL)
    assert (
        "clerk" in dash_duo.driver.page_source.lower()
        or "sign-in" in dash_duo.driver.current_url
    )

    dash_duo.wait_for_text_to_equal("form button.cl-formButtonPrimary", "Continue")

    dash_duo.find_element("#identifier-field").send_keys(os.getenv("CLERK_TEST_USER"))
    dash_duo.find_element("#identifier-field").send_keys(Keys.RETURN)

    dash_duo.wait_for_text_to_equal("form a.cl-formFieldAction", "Forgot password?")
    dash_duo.find_element("#password-field").send_keys(os.getenv("CLERK_TEST_PASSWORD"))
    dash_duo.find_element("#password-field").send_keys(Keys.RETURN)

    dash_duo.wait_for_text_to_equal("body", "logging in...")
    dash_duo.wait_for_text_to_equal(
        "#_pages_content h1", "User john_doe (authenticated only)"
    )

    dash_duo.find_element('a[href="/logout"]').click()
    dash_duo.wait_for_text_to_equal("a[href='/']", "Go back")
    dash_duo.find_element("a[href='/']").click()

    # Go to the home page (public)
    dash_duo.wait_for_text_to_equal("h1", "Home Page", timeout=10)

    # Navigate to the protected page
    dash_duo.driver.get(dash_duo.server_url + "/user/john_doe/private")

    # Should be redirected to Clerk login (look for a known Clerk element or URL)
    assert (
        "clerk" in dash_duo.driver.page_source.lower()
        or "sign-in" in dash_duo.driver.current_url
    )


# ---------------------------------------------------------------------------
# Unit tests for ClerkAuth._get_safe_redirect_url
# ---------------------------------------------------------------------------


@pytest.fixture
def safe_redirect():
    """Return a bound _get_safe_redirect_url method on a bare ClerkAuth instance.

    ``object.__new__`` bypasses ``ClerkAuth.__init__``, so no Dash app or Clerk
    credentials are needed.  The method only uses ``self`` for dispatch and
    reads ``flask.request`` via an explicit request_obj argument when the
    supplied URL is absolute.
    """
    instance = object.__new__(ClerkAuth)
    return lambda url: instance._get_safe_redirect_url(url, req=flask.request)


@pytest.fixture
def http_request_ctx():
    """A Flask test-request context on http://example.com:8050/."""
    app = flask.Flask(__name__)
    with app.test_request_context("/", base_url="http://example.com:8050/"):
        yield


@pytest.fixture
def https_request_ctx():
    """A Flask test-request context on https://example.com:8443/."""
    app = flask.Flask(__name__)
    with app.test_request_context("/", base_url="https://example.com:8443/"):
        yield


class TestGetSafeRedirectUrl:
    """Unit tests for ClerkAuth._get_safe_redirect_url."""

    # ------------------------------------------------------------------
    # Accepted relative URLs
    # ------------------------------------------------------------------

    def test_relative_root(self, safe_redirect):
        assert safe_redirect("/") == "/"

    def test_relative_path(self, safe_redirect):
        assert safe_redirect("/dashboard") == "/dashboard"

    def test_relative_path_with_query(self, safe_redirect):
        assert safe_redirect("/search?q=hello") == "/search?q=hello"

    def test_relative_path_with_fragment(self, safe_redirect):
        assert safe_redirect("/page#section") == "/page#section"

    def test_relative_path_with_query_and_fragment(self, safe_redirect):
        assert safe_redirect("/page?x=1#anchor") == "/page?x=1#anchor"

    def test_relative_nested_path(self, safe_redirect):
        assert safe_redirect("/user/42/profile") == "/user/42/profile"

    # ------------------------------------------------------------------
    # Rejected non-relative / external URLs
    # ------------------------------------------------------------------

    def test_empty_string_rejected(self, safe_redirect):
        assert safe_redirect("") is None

    def test_no_leading_slash_rejected(self, safe_redirect):
        assert safe_redirect("dashboard") is None

    def test_protocol_relative_rejected(self, safe_redirect):
        """URLs beginning with '//' must be rejected (protocol-relative open redirect)."""
        assert safe_redirect("//evil.com/steal") is None

    def test_external_http_rejected(self, safe_redirect):
        assert safe_redirect("http://evil.com/steal") is None

    def test_external_https_rejected(self, safe_redirect):
        assert safe_redirect("https://attacker.example/steal") is None

    # ------------------------------------------------------------------
    # Absolute URLs outside a Flask request context
    # ------------------------------------------------------------------

    def test_absolute_url_outside_request_context_rejected(self, safe_redirect):
        """Without a request context the method must conservatively reject absolute URLs."""
        assert safe_redirect("http://example.com/path") is None

    # ------------------------------------------------------------------
    # Same-origin absolute URLs (accepted and normalised)
    # ------------------------------------------------------------------

    def test_same_origin_absolute_accepted(self, safe_redirect, http_request_ctx):
        assert safe_redirect("http://example.com:8050/path") == "/path"

    def test_same_origin_absolute_root(self, safe_redirect, http_request_ctx):
        """Absolute same-origin URL with no path component normalises to '/'."""
        assert safe_redirect("http://example.com:8050") == "/"

    def test_same_origin_absolute_with_query(self, safe_redirect, http_request_ctx):
        assert safe_redirect("http://example.com:8050/search?q=1") == "/search?q=1"

    def test_same_origin_absolute_with_fragment(self, safe_redirect, http_request_ctx):
        assert safe_redirect("http://example.com:8050/page#sec") == "/page#sec"

    def test_same_origin_absolute_with_query_and_fragment(
        self, safe_redirect, http_request_ctx
    ):
        assert (
            safe_redirect("http://example.com:8050/page?x=1#anchor")
            == "/page?x=1#anchor"
        )

    def test_same_origin_https_accepted(self, safe_redirect, https_request_ctx):
        assert safe_redirect("https://example.com:8443/protected") == "/protected"

    # ------------------------------------------------------------------
    # Cross-origin absolute URLs (rejected)
    # ------------------------------------------------------------------

    def test_different_host_rejected(self, safe_redirect, http_request_ctx):
        assert safe_redirect("http://other.com:8050/path") is None

    def test_different_scheme_rejected(self, safe_redirect, http_request_ctx):
        """Same host but different scheme must be rejected."""
        assert safe_redirect("https://example.com:8050/path") is None

    def test_different_port_rejected(self, safe_redirect, http_request_ctx):
        """Same host but different port is a different origin and must be rejected."""
        assert safe_redirect("http://example.com:9000/path") is None
