import logging
import os
import re
import traceback
from typing import Any, Dict, List, Optional, Union, Callable

import dash
from dash_auth_plus.auth import Auth, _get_page_paths_and_adapter
from dotenv import load_dotenv
from itsdangerous import BadSignature, URLSafeSerializer
from urllib.parse import urljoin, quote, unquote, urlparse
from werkzeug.routing import Rule, Map

load_dotenv()

UserGroups = Dict[str, List[str]]

# UI/UX Design tokens following best practices from the guide
DESIGN_TOKENS = {
    # Colors following proper contrast ratios (WCAG AA)
    "colors": {
        "primary": "#0066cc",
        "primary_hover": "#0052a3",
        "danger": "#dc3545",
        "danger_hover": "#c82333",
        "text_primary": "#212529",  # Not pure black as per guide
        "text_secondary": "#6c757d",
        "background": "#ffffff",
        "background_secondary": "#f8f9fa",
        "border": "#dee2e6",
        "shadow": "rgba(0, 0, 0, 0.1)",  # Soft shadows as recommended
    },
    # Typography following the guide's recommendations
    "typography": {
        "font_family": '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        "font_size_base": "14px",  # Readable size
        "font_size_small": "12px",
        "font_weight_normal": "400",
        "font_weight_medium": "500",
        "font_weight_semibold": "600",
        "line_height": "1.5",
    },
    # Spacing system using base unit of 4px as recommended
    "spacing": {
        "xs": "4px",
        "sm": "8px",
        "md": "12px",
        "lg": "16px",
        "xl": "24px",
    },
    # Border radius for consistency
    "border_radius": {
        "sm": "4px",
        "md": "8px",
        "full": "50%",
    },
    # Transitions for smooth interactions
    "transitions": {
        "fast": "all 0.15s ease",
        "medium": "all 0.2s ease",
    },
}


class ClerkAuth(Auth):
    """Implements auth via Clerk."""

    def __init__(
        self,
        app: dash.Dash,
        secret_key: str = Optional[None],
        force_https_callback: Optional[Union[bool, str]] = None,
        clerk_secret_key: str = os.environ.get("CLERK_SECRET_KEY"),
        clerk_domain: str = os.environ.get("CLERK_DOMAIN"),
        clerk_publishable_key: str = os.environ.get("CLERK_PUBLISHABLE_KEY"),
        allowed_parties: Optional[List[str]] = (
            os.environ.get("CLERK_ALLOWED_PARTIES", "").split(",")
            if os.environ.get("CLERK_ALLOWED_PARTIES")
            else []
        ),
        log_signins: bool = False,
        public_routes: Optional[list] = None,
        logout_page: Optional[Union[str, Any]] = None,
        secure_session: bool = False,
        user_groups: Optional[Union[UserGroups, Callable[[str], List[str]]]] = None,
        login_user_callback: Callable = None,
        auth_protect_layouts: Optional[bool] = False,
        auth_protect_layouts_kwargs: Optional[dict] = None,
        page_container: Optional[str] = None,
        default_html_style: Optional[str] = None,
        before_logout: Optional[Callable] = None,
    ):
        """Secure a Dash app through OpenID Connect.

        Parameters
        ----------
        app : Dash
            The Dash app to secure
        secret_key : str, optional
            A string to protect the Flask session, by default None.
            Generate a secret key in your Python session
            with the following commands:
            >>> import os
            >>> import base64
            >>> base64.b64encode(os.urandom(30)).decode('utf-8')
            Note that you should not do this dynamically:
            you should create a key and then assign the value of
            that key in your code.
        force_https_callback : Union[bool, str], optional
            Whether to force redirection to https, by default None
            This is useful when the HTTPS termination is upstream of the server
            If a string is passed, this will check for the existence of
            an envvar with that name and force https callback if it exists.
        login_route : str, optional
            The route for the login function, it requires a <idp>
            placeholder, by default "/oidc/<idp>/login".
        logout_route : str, optional
            The route for the logout function, by default "/oidc/logout".
        callback_route : str, optional
            The route for the OIDC redirect URI, it requires a <idp>
            placeholder, by default "/oidc/<idp>/callback".
        log_signins : bool, optional
            Whether to log signins, by default False
        public_routes : list, optional
            List of public routes, routes should follow the
            Flask route syntax
        logout_page : str or Response, optional
            Page seen by the user after logging out,
            by default None which will default to a simple logged out message
        secure_session: bool, optional
            Whether to ensure the session is secure, setting the flask config
            SESSION_COOKIE_SECURE and SESSION_COOKIE_HTTPONLY to True,
            by default False
        user_groups: a dict or a function returning a dict
            Optional group for each user, allowing to protect routes and
            callbacks depending on user groups
        login_user_callback: python function accepting two arguments
            (userinfo, idp), where userinfo is normally a dict
            (request form or results from the idp).
            This must return a flask response or redirect.
        :param auth_protect_layouts: bool, defaults to False.
            If true, runs protect_layout()
        :param auth_protect_layouts_kwargs: dict, if provided is passed to the
            protect_layout as kwargs
        :param page_container: string, id of the page container in the app.
            If not provided, this will set the page_container_test to True,
            meaning all pathname callbacks will be judged.
        :param default_html_style: str, optional
            Custom CSS styles to inject into the HTML head, by default None.
        :param before_logout: Callable, optional
            A function to call before logging out the user, by default None.
            This can be used to perform cleanup actions or logging before the user is logged out.

        Raises
        ------
        Exception
            Raise an exception if the app.server.secret_key is not defined
        """
        super().__init__(
            app,
            public_routes=public_routes,
            auth_protect_layouts=auth_protect_layouts,
            auth_protect_layouts_kwargs=auth_protect_layouts_kwargs,
            page_container=page_container,
        )

        try:
            from clerk_backend_api import Clerk
            from clerk_backend_api.jwks_helpers import AuthenticateRequestOptions
        except ImportError:
            raise ImportError(
                "clerk-backend-api is required for dash-clerk-auth. "
                "Install it with: pip install clerk-backend-api"
            )

        if isinstance(force_https_callback, str):
            self.force_https_callback = force_https_callback in os.environ
        elif force_https_callback is not None:
            self.force_https_callback = force_https_callback
        else:
            self.force_https_callback = False

        self.initialized = False
        self.default_html_style = (
            "<style>\n" + default_html_style + "\n</style>"
            if default_html_style
            else ""
        )
        self.clerk_secret_key = clerk_secret_key
        self.clerk_domain = clerk_domain
        self.clerk_publishable_key = clerk_publishable_key
        self.log_signins = log_signins
        self.logout_page = logout_page
        self._user_groups = user_groups
        self.login_user_callback = login_user_callback
        self.login_route = "/login"
        self.logout_route = "/logout"
        self.authenticate_request_options = AuthenticateRequestOptions
        self.before_logout = before_logout or (lambda: None)
        host = self._get_config_value("SERVER_NAME", "127.0.0.1")
        port = self._get_config_value("SERVER_PORT", 8050)
        self.allowed_parties = (
            allowed_parties
            + [
                f"http://{host}:{port}",
                f"http://localhost:{port}",
                f"https://localhost:{port}",
            ]
            if allowed_parties
            else [
                f"http://{host}:{port}",
                f"http://localhost:{port}",
                f"https://localhost:{port}",
            ]
        )
        self.callback_route = "/auth_callback"

        # Validate required configuration
        if not self.clerk_secret_key:
            raise ValueError(
                "clerk_secret_key is required (set CLERK_SECRET_KEY env var)"
            )
        if not self.clerk_publishable_key:
            raise ValueError(
                "clerk_publishable_key is required (set CLERK_PUBLISHABLE_KEY env var)"
            )
        if not self.clerk_domain:
            raise ValueError("clerk_domain is required (set CLERK_SIGN_IN_URL env var)")

        self.clerk_client = Clerk(bearer_auth=self.clerk_secret_key)
        self.initialized = True

        if secret_key is not None:
            self._set_secret_key(secret_key)

        if self._get_secret_key() is None:
            raise RuntimeError("""
                app.server.secret_key is missing.
                Generate a secret key in your Python session
                with the following commands:
                >>> import os
                >>> import base64
                >>> base64.b64encode(os.urandom(30)).decode('utf-8')
                and assign it to the property app.server.secret_key
                (where app is your dash app instance), or pass is as
                the secret_key argument to OIDCAuth.__init__.
                Note that you should not do this dynamically:
                you should create a key and then assign the value of
                that key in your code/via a secret.
                """)

        if secure_session:
            self._set_config_value("SESSION_COOKIE_SECURE", True)
            self._set_config_value("SESSION_COOKIE_HTTPONLY", True)

        self.session_cookie_name = "dash_auth_plus_session"
        self.session_serializer = URLSafeSerializer(
            self._get_secret_key(),
            salt="dash-auth-plus-clerk-session",
        )
        self.session_cookie_secure = secure_session

        if getattr(app.backend, "server_type", None) == "fastapi":
            from fastapi import Request as FastAPIRequest
            from dash.backends._fastapi import (
                set_current_request,
                reset_current_request,
            )

            def logout_view(request: FastAPIRequest):
                token = set_current_request(request)
                try:
                    return self.logout()
                finally:
                    reset_current_request(token)

            def callback_view(request: FastAPIRequest):
                token = set_current_request(request)
                try:
                    return self.check_clerk_auth()
                finally:
                    reset_current_request(token)

            app.backend.add_url_rule(
                self.logout_route,
                endpoint="oidc_logout",
                view_func=logout_view,
                methods=["GET"],
            )

            app.backend.add_url_rule(
                self.callback_route,
                endpoint="oidc_callback",
                view_func=callback_view,
                methods=["GET", "POST"],
            )
        else:
            app.backend.add_url_rule(
                self.logout_route,
                endpoint="oidc_logout",
                view_func=self.logout,
                methods=["GET"],
            )

            app.backend.add_url_rule(
                self.callback_route,
                endpoint="oidc_callback",
                view_func=self.check_clerk_auth,
                methods=["GET", "POST"],
            )

        clerk_script = f"""
            <script
                async
                crossorigin="anonymous"
                data-clerk-publishable-key="{self.clerk_publishable_key}"
                src="{self.clerk_domain}/npm/@clerk/clerk-js@5/dist/clerk.browser.js"
                type="text/javascript">
            </script>
        """

        # Enhanced initialization with smart auth checking
        init_script = (
            """
                        <script>
                            """
            + f"const logout_path = '{self.logout_route}';"
            + """
            const is_logout_route = logout_path === window.location.pathname;
            const login_sync_key = 'clerk_login_sync_in_progress';
            if (logout_path === window.location.pathname) {
                                localStorage.setItem('clerk_logged_in', false)
                                sessionStorage.removeItem(login_sync_key)
                            }
                            // Helper to ensure Clerk is ready
                            var waitForClerk = function() {
                                return new Promise((resolve) => {
                                    let attempts = 0;
                                    const interval = setInterval(() => {
                                        attempts++;
                                        if (typeof window.Clerk !== 'undefined') {
                                            clearInterval(interval);

                                            // CRITICAL: Always call load() to ensure Clerk initializes properly
                                            window.Clerk.load().then(() => {
                                                // Set up session sync listener
                                                if (window.location.pathname == logout_path) {
                                                    window.Clerk.signOut().then(() => {
                                                        localStorage.setItem('clerk_logged_in', false);
                                                        console.log('User signed out via logout route');
                                                        return;
                                                    }).catch(err => {
                                                        console.error('Error signing out:', err);
                                                        return;
                                                    });
                                                };
                                                if (window.Clerk.addListener) {
                                                    window.Clerk.addListener((resources) => {
                                                        if (is_logout_route) {
                                                            localStorage.setItem('clerk_logged_in', false);
                                                            sessionStorage.removeItem(login_sync_key);
                                                            return;
                                                        }
                                                        var clerk_logged_in = JSON.parse(localStorage.getItem('clerk_logged_in')) || false;
                                                        var login_sync_in_progress = sessionStorage.getItem(login_sync_key) === '1';
                                                        // Store auth state in localStorage for persistence
                                                        if (resources.user && resources.session) {
                                                            if (!clerk_logged_in && !login_sync_in_progress) {
                                                                sessionStorage.setItem(login_sync_key, '1');
                                                                console.log('logging in Clerk user');
                                                                setTimeout(async () => {
                                                                var callbackUrl = window.location.origin + (window.location.pathname == '/auth_callback' ? window.location.pathname : '/auth_callback?redirect_url=' + encodeURIComponent(window.location.href))
                                                                var token = null;
                                                                try {
                                                                    if (resources && resources.session && typeof resources.session.getToken === 'function') {
                                                                        token = await resources.session.getToken();
                                                                    } else if (window.Clerk && window.Clerk.session && typeof window.Clerk.session.getToken === 'function') {
                                                                        token = await window.Clerk.session.getToken();
                                                                    }
                                                                } catch (err) {
                                                                    console.warn('Could not obtain Clerk token for callback sync:', err);
                                                                }
                                                                var headers = token ? { 'Authorization': 'Bearer ' + token } : {};
                                                                fetch(callbackUrl, {
                                                                    method: 'POST',
                                                                    redirect: 'follow',
                                                                    credentials: 'same-origin',
                                                                    headers: headers
                                                                }).then(response => {
                                                                    localStorage.setItem('clerk_logged_in', true);
                                                                    if (response.url && response.url !== window.location.href) {
                                                                        window.location.replace(response.url);
                                                                    }
                                                                }).catch(err => {
                                                                    console.error('Error syncing Clerk session:', err);
                                                                }).finally(() => {
                                                                    sessionStorage.removeItem(login_sync_key);
                                                                });
                                                                }, 150);
                                                            } else {
                                                                console.log('Clerk session updated');
                                                            }
                                                        }
                                                        else if (clerk_logged_in) {
                                                            localStorage.setItem('clerk_logged_in', false);
                                                            sessionStorage.removeItem(login_sync_key);
                                                            console.log('session ended, logging out');
                                                            """
            + f"""newLoc = window.location.origin + '{self.logout_route}';"""
            + """
                                                            window.location.href = newLoc;
                                                        }
                                                        else {
                                                            localStorage.setItem('clerk_logged_in', false);
                                                            sessionStorage.removeItem(login_sync_key);
                                                        }

                                                    });
                                                }

                                                resolve(window.Clerk);
                                            }).catch(err => {
                                                console.error('Clerk load failed:', err);
                                                // Clerk load failed
                                                resolve(null);
                                            });
                                        }
                                        if (attempts > 100) {
                                            clearInterval(interval);
                                            console.warn('Clerk not initialized after multiple attempts');
                                            // Clerk not found after timeout
                                            resolve(null);
                                        }
                                    }, 100);
                                });
                            };

                            // Initialize on load
                            document.addEventListener('DOMContentLoaded', () => {
                                waitForClerk().then(clerk => {
                                    if (clerk) {
                                        // Dispatch event to trigger initial auth check
                                        window.dispatchEvent(new Event('clerk-loaded'));
                                    }
                                });
                            });
                        </script>
                        """
        )

        self.clerk_script = f"{clerk_script}\n{init_script}\n{self.default_html_style}"

        if dash.__version__ >= "3.0":
            # Use the new OAuth2App class for Dash 3+
            @dash.hooks.layout()
            def append_clerk_url(layout):
                return [
                    dash.dcc.Location(id="_clerk_login_url", refresh=True),
                    dash.dcc.Store(id="clerk_logged_in", storage_type="local"),
                    dash.dcc.Store(id="clerk_user_update", storage_type="local"),
                    dash.dcc.Store(id="show_user_profile", data=False),
                    layout,
                ]

            @dash.hooks.index()
            def add_clerk_script(index_string):
                """Inject Clerk script into the HTML head"""
                if not self.initialized:
                    return index_string

                if self.clerk_script and "</head>" in index_string:
                    # Inject scripts and styles before closing head tag
                    index_string = index_string.replace(
                        "</head>",
                        f"{self.clerk_script}\n</head>",
                    )

                return index_string

        else:
            app.index_string.replace(
                "</head>",
                f"{self.clerk_script}\n</head>",
            )

    def _redirect_test(self):
        req = self._get_request()
        session_data = self._get_session(req)
        registered_paths = []
        map_adapter = None

        app_config = getattr(getattr(self, "app", None), "config", {})
        if "pages_folder" in app_config:
            # Use the cached helper to avoid rebuilding paths/adapters on every
            # request and to safely handle Dash versions without page_registry.
            registered_paths, map_adapter = _get_page_paths_and_adapter()

        # Extract the intended URL and preserve path + query + fragment
        request_method = self._request_method(req)
        source_url = req.url if request_method == "GET" else req.headers.get("referer")
        if request_method != "GET" and not source_url:
            logging.debug(
                "Missing Referer header; using request root for redirect path."
            )
            source_url = req.root
        parsed_url = urlparse(source_url)
        url_path = parsed_url.path
        url_relative = parsed_url.path
        if parsed_url.query:
            url_relative += "?" + parsed_url.query
        if parsed_url.fragment:
            url_relative += "#" + parsed_url.fragment

        # Determine validity of the path against registered Dash Pages, if any
        if registered_paths or map_adapter is not None:
            # Check static paths
            valid = url_path in registered_paths
            # Check templates using the pre-built cached adapter
            if not valid and map_adapter is not None:
                try:
                    map_adapter.match(url_path)
                    valid = True
                except Exception:
                    valid = False
        else:
            # When no pages are registered (e.g. single-page apps), accept the URL
            valid = True

        session_data["url"] = url_relative if valid else "/"
        # Avoid redirecting back to the login route itself
        if (
            "url" in session_data
            and urlparse(session_data["url"]).path == self.login_route
        ):
            del session_data["url"]

    def _get_session(self, req=None):
        """Return backend-agnostic session data cached in the request context."""
        req = req if req is not None else self._get_request()
        ctx = self._get_request_context(req)
        cached = self._context_get(ctx, "_dash_auth_plus_session")
        if cached is not None:
            return cached

        raw = req.cookies.get(self.session_cookie_name)
        if not raw:
            session_data = {}
        else:
            try:
                data = self.session_serializer.loads(raw)
                session_data = data if isinstance(data, dict) else {}
            except BadSignature:
                logging.warning(
                    "Discarding tampered %s cookie due to invalid signature.",
                    self.session_cookie_name,
                )
                session_data = {}
        self._context_set(ctx, "_dash_auth_plus_session", session_data)
        return session_data

    def _set_session_cookie(self, response, session_data):
        """Persist the current session data as a signed auth cookie."""
        response.set_cookie(
            self.session_cookie_name,
            self.session_serializer.dumps(session_data),
            secure=self.session_cookie_secure,
            httponly=True,
            samesite="Lax",
            path=self.app.config.get("url_base_pathname") or "/",
        )
        return response

    def _clear_session_cookie(self, response):
        response.delete_cookie(
            self.session_cookie_name,
            path=self.app.config.get("url_base_pathname") or "/",
        )
        return response

    def _clear_clerk_cookies(self, response, req):
        """Best-effort deletion of auth cookies present on this app domain."""
        if not req:
            return response
        base_path = self.app.config.get("url_base_pathname") or "/"
        cookie_paths = {"/", base_path.rstrip("/") or "/"}
        for cookie in req.cookies:
            if not re.match(r"^[A-Za-z0-9_.-]+$", cookie):
                logging.debug(
                    "Skipping cookie deletion for invalid cookie name: %r", cookie
                )
                continue
            if (
                cookie == self.session_cookie_name
                or cookie.startswith("__clerk")
                or cookie == "__session"
                or cookie.startswith("__session_")
                or cookie.startswith("__client_uat")
            ):
                for path in cookie_paths:
                    response.delete_cookie(cookie, path=path)
        return response

    def _select_session_token(self, req):
        """Select a deterministic __session token when duplicate cookies exist."""
        raw_cookie_header = req.headers.get("cookie", "") or ""
        header_tokens = []
        active_context = req.cookies.get("clerk_active_context")
        if raw_cookie_header:
            for chunk in raw_cookie_header.split(";"):
                name, _, value = chunk.strip().partition("=")
                if (name == "__session" or name.startswith("__session_")) and value:
                    header_tokens.append(unquote(value))

        adapter_token = req.cookies.get("__session")
        if adapter_token:
            header_tokens.append(adapter_token)

        for key, value in (req.cookies or {}).items():
            if (key == "__session" or key.startswith("__session_")) and value:
                header_tokens.append(value)

        if active_context:
            scoped_key = f"__session_{active_context}"
            scoped_token = req.cookies.get(scoped_key)
            if scoped_token:
                # Prefer current Clerk context token by appending last.
                header_tokens.append(scoped_token)

        if not header_tokens:
            return None

        unique_tokens = []
        for token in header_tokens:
            if token not in unique_tokens:
                unique_tokens.append(token)

        jwt_like = [token for token in unique_tokens if token.count(".") == 2]
        chosen = jwt_like[-1] if jwt_like else unique_tokens[-1]

        if len(unique_tokens) > 1:
            logging.warning(
                "Multiple __session cookie values detected; using the most recent candidate."
            )

        return chosen

    def _request_method(self, req):
        """Read HTTP method from request adapters with a compatibility fallback."""
        method = getattr(req, "method", None)
        if method:
            return str(method).upper()
        request_obj = getattr(req, "_request", None)
        if request_obj is not None and hasattr(request_obj, "method"):
            return str(request_obj.method).upper()
        logging.warning(
            "Could not determine request method from adapter; defaulting to GET."
        )
        return "GET"

    def _build_clerk_request(self, req):
        """Build a request-like object that prioritizes the exact __session cookie token."""
        headers = dict(req.headers or {})
        # Ensure header lookup is consistent across adapters that may expose
        # lowercase-only header keys.
        if "Authorization" not in headers and headers.get("authorization"):
            headers["Authorization"] = headers.get("authorization")
        session_token = self._select_session_token(req)
        has_auth_header = bool(
            headers.get("Authorization") or headers.get("authorization")
        )
        if session_token and not has_auth_header:
            headers["Authorization"] = f"Bearer {session_token}"

        class _RequestProxy:
            def __init__(self, proxied_headers):
                self.headers = proxied_headers

        return _RequestProxy(headers)

    def _redirect_response(self, target_url):
        response = self.app.backend.make_response("", status=302)
        response.headers["Location"] = target_url
        return response

    def _create_redirect_uri(self):
        """Create the redirect uri based on callback endpoint and idp."""
        req = self._get_request()
        kwargs = {"_external": True}
        if self.force_https_callback:
            kwargs["_scheme"] = "https"

        redirect_uri = urljoin(
            self.clerk_domain,
            "/sign-in?redirect_url="
            + quote(req.root.rstrip("/") + self.callback_route, safe=""),
        )
        session_data = self._get_session(req)
        if not session_data.get("url"):
            self._redirect_test()
        if req.headers.get("X-Forwarded-Host"):
            host = req.headers.get("X-Forwarded-Host")
            redirect_uri = redirect_uri.replace(urlparse(req.root).netloc, host, 1)
        return redirect_uri

    def login_request(self):
        """Start the login process."""
        req = self._get_request()
        session_data = self._get_session(req)
        resp = self._create_redirect_uri()
        if self._request_method(req) == "POST":
            response = self.app.backend.jsonify(
                {
                    "multi": True,
                    "sideUpdate": {"_clerk_login_url": {"href": resp}},
                }
            )
            return self._set_session_cookie(response, session_data)
        return self._set_session_cookie(self._redirect_response(resp), session_data)

    def logout(self):  # pylint: disable=C0116
        """Logout the user."""
        req = self._get_request()
        try:
            session_data = self._get_session(req)
        except Exception as e:
            logging.error(
                "Error getting session data during logout: %s\n%s",
                e,
                traceback.format_exc(),
            )
            session_data = {}
        session_sid = session_data.get("sid")
        try:
            self.before_logout()
        except Exception as e:
            logging.error(
                "Error in before_logout hook: %s\n%s", e, traceback.format_exc()
            )
        if "user" in session_data:
            try:
                request_state = self.clerk_client.authenticate_request(
                    self._build_clerk_request(req),
                    self.authenticate_request_options(
                        authorized_parties=self.allowed_parties,
                    ),
                )
                if request_state.is_signed_in:
                    try:
                        self.clerk_client.sessions.revoke(
                            session_id=request_state.payload.get("sid")
                        )
                    except Exception as e:
                        logging.error(
                            "Error revoking Clerk session during logout: %s\n%s",
                            e,
                            traceback.format_exc(),
                        )
            except Exception as e:
                logging.error(
                    "Error authenticating Clerk request during logout: %s\n%s",
                    e,
                    traceback.format_exc(),
                )
            if session_sid:
                try:
                    self.clerk_client.sessions.revoke(session_id=session_sid)
                except Exception as e:
                    logging.error(
                        "Error revoking Clerk session using stored sid during logout: %s\n%s",
                        e,
                        traceback.format_exc(),
                    )
        session_data.clear()
        response = self.app.backend.make_response(
            self.logout_page or f"""
        <div style="display: flex; flex-direction: column;
        gap: 0.75rem; padding: 3rem 5rem;">
            <div>Logged out successfully</div>
            <div><a href="{self.app.config.get("url_base_pathname") or "/"}">Go back</a></div>
        </div>
        {self.clerk_script}
        """,
            content_type="text/html",
        )
        self._clear_clerk_cookies(response, req)
        return self._clear_session_cookie(response)

    def after_logged_in(self, user: Optional[dict], sid):
        """
        Post-login actions after successful OIDC authentication.
        For example, allows to pass custom attributes to the user session:
        class MyOIDCAuth(OIDCAuth):
            def after_logged_in(self, user, idp, token):
                if user:
                    user["params"] = value1
                return super().after_logged_in(user, idp, token)
        """
        req = self._get_request()
        session_data = self._get_session(req)
        if self.login_user_callback:
            return self.login_user_callback(user, "clerk", sid)
        elif user:
            email = (
                [
                    x.email_address
                    for x in user.email_addresses
                    if x.id == user.primary_email_address_id
                ][0]
                if user.email_addresses
                else None
            )
            session_data["user"] = {
                "clerk_user_id": user.id,
                "userid": user.username,
                "email": email,
            }
            session_data["sid"] = sid
            if callable(self._user_groups):
                session_data["user"]["groups"] = self._user_groups(email) + (
                    session_data["user"].get("groups") or []
                )
            elif self._user_groups:
                session_data["user"]["groups"] = self._user_groups.get(email, []) + (
                    session_data["user"].get("groups") or []
                )
            if self.log_signins:
                logging.info(
                    "User %s is logging in.", session_data["user"].get("email")
                )
        if session_data.get("url"):
            url = session_data["url"]
            del session_data["url"]
            return self._set_session_cookie(self._redirect_response(url), session_data)
        response = self.app.backend.jsonify(
            {"status": "ok", "content": "User logged in successfully."}
        )
        return self._set_session_cookie(response, session_data)

    def _get_safe_redirect_url(self, url: str, req=None) -> Optional[str]:
        """
        Validate a user-supplied redirect URL and return a safe relative URL or None.

        The function accepts:
        - Relative URLs without scheme/netloc that start with a single '/'.
        - Absolute URLs with scheme/netloc only if they are same-origin with the
          current request (same scheme and host); these are normalized to a
          relative URL (path + optional query/fragment) before being returned.

        Any URL that does not meet these criteria is rejected to prevent
        open-redirects to external domains.

        :param req: Optional request object override. If omitted, the current
            backend request adapter is used.
        """
        if not url:
            return None

        # Reject URLs containing ASCII control characters (including CR/LF) to
        # prevent header injection and issues in Flask/Werkzeug redirect().
        for ch in url:
            codepoint = ord(ch)
            if codepoint < 32 or codepoint == 127:
                return None

        parsed = urlparse(url)

        # If scheme or netloc are present, only allow same-origin absolute URLs
        if parsed.scheme or parsed.netloc:
            try:
                request_ref = req if req is not None else self._get_request()
                parsed_current = urlparse(request_ref.url)
                current_scheme = parsed_current.scheme
                current_host = parsed_current.netloc
            except RuntimeError:
                # Outside of a request context; be conservative and reject
                return None
            # Reject if the absolute URL is not same-origin
            if parsed.scheme != current_scheme or parsed.netloc != current_host:
                return None

            # Normalize same-origin absolute URL to a relative path (+query/fragment)
            url = parsed.path or "/"
            if parsed.query:
                url += "?" + parsed.query
            if parsed.fragment:
                url += "#" + parsed.fragment

            parsed = urlparse(url)

        # At this point, only relative URLs without scheme/netloc are allowed
        if parsed.scheme or parsed.netloc:
            return None

        # Require a leading '/' and disallow protocol-relative URLs starting with '//'
        if not url.startswith("/") or url.startswith("//"):
            return None

        return url

    def check_clerk_auth(self):
        """Pulls Clerk user data from the request and stores it in the session."""
        req = self._get_request()
        session_data = self._get_session(req)
        if req.args.get("redirect_url"):
            # If redirect_uri is provided, validate and use it only if safe.
            # Allow it to overwrite session["url"] when the current value is
            # unset or points to the login/callback route, to avoid redirect loops.
            raw_redirect_url = unquote(req.args.get("redirect_url"))
            safe_url = self._get_safe_redirect_url(raw_redirect_url, req=req)
            if safe_url:
                current_url = session_data.get("url")
                current_path = urlparse(current_url).path if current_url else None
                if not current_path or current_path in (
                    self.login_route,
                    self.callback_route,
                ):
                    session_data["url"] = safe_url

        request_state = self.clerk_client.authenticate_request(
            self._build_clerk_request(req),
            self.authenticate_request_options(
                authorized_parties=self.allowed_parties,
            ),
        )

        reason = getattr(request_state, "reason", None)
        reason_name = getattr(reason, "name", "")
        if reason_name == "JWK_KID_MISMATCH":
            logging.warning(
                "Clerk token validation failed with JWK_KID_MISMATCH. "
                "Clearing local auth state and restarting login flow."
            )
            session_data.clear()
            recovery_target = self.app.config.get("url_base_pathname") or "/"
            response = self._redirect_response(recovery_target)
            self._clear_clerk_cookies(response, req)
            return self._clear_session_cookie(response)

        if request_state.is_signed_in:
            sid = request_state.payload.get("sid")
            sess = self.clerk_client.sessions.get(session_id=sid)
            user_data = self.clerk_client.users.get(user_id=sess.user_id)
            return self.after_logged_in(user_data, sid)
        response = self.app.backend.make_response(
            f"""
        <div>logging in...</div>
        {self.clerk_script}
        """,
            content_type="text/html",
        )
        return self._set_session_cookie(response, session_data)

    def is_authorized(self):  # pylint: disable=C0116
        """Check whether the user is authenticated."""
        req = self._get_request()
        req_path = self._normalized_request_path(getattr(req, "path", None))
        session_data = self._get_session(req)

        map_adapter = Map(
            [
                Rule(x)
                for x in [self.login_route, self.logout_route, self.callback_route]
                if x
            ]
        ).bind("")

        if (
            "user" in session_data
            or self._path_matches_map(map_adapter, req_path)
            or self.clerk_domain in req.url
            or (req_path and req_path.startswith("/.well-known/"))
        ):
            return True
        return False

    def get_user_data(self):
        req = self._get_request()
        request_state = self.clerk_client.authenticate_request(
            self._build_clerk_request(req),
            self.authenticate_request_options(
                authorized_parties=self.allowed_parties,
            ),
        )

        if request_state.is_signed_in:
            sid = request_state.payload.get("sid")
            sess = self.clerk_client.sessions.get(session_id=sid)
            user_data = self.clerk_client.users.get(user_id=sess.user_id)
            return {**user_data.__dict__}
        return False  # "user not authenticated"
