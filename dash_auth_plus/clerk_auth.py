import logging
import os
import traceback
from typing import Dict, List, Optional, Union, Callable

import dash
import flask
from authlib.integrations.flask_client import OAuth
from dash_auth_plus.auth import Auth
from flask import Response, redirect, request, session, jsonify
from werkzeug.routing import Map, Rule
from dotenv import load_dotenv
from urllib.parse import urljoin, quote, unquote

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
        logout_page: Union[str, Response] = None,
        secure_session: bool = False,
        user_groups: Optional[Union[UserGroups, Callable[[str], List[str]]]] = None,
        login_user_callback: Callable = None,
        auth_protect_layouts: Optional[bool] = False,
        auth_protect_layouts_kwargs: Optional[dict] = None,
        page_container: Optional[str] = None,
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
        self.app.server.after_request(self.set_loggedin_if_user_session)
        host = app.server.config.get("SERVER_NAME") or "127.0.0.1"
        port = app.server.config.get("SERVER_PORT", 8050)
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
            app.server.secret_key = secret_key

        if app.server.secret_key is None:
            raise RuntimeError(
                """
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
                """
            )

        if secure_session:
            app.server.config["SESSION_COOKIE_SECURE"] = True
            app.server.config["SESSION_COOKIE_HTTPONLY"] = True

        self.oauth = OAuth(app.server)

        app.server.add_url_rule(
            self.logout_route,
            endpoint="oidc_logout",
            view_func=self.logout,
            methods=["GET"],
        )

        app.server.add_url_rule(
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
            + f"if (window.location.pathname == '{self.logout_route}') "
            + """{
                                localStorage.setItem('clerk_logged_in', false)
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
                                                if (window.Clerk.addListener) {
                                                    window.Clerk.addListener((resources) => {
                                                        var clerk_logged_in = JSON.parse(localStorage.getItem('clerk_logged_in')) || false;
                                                        // Store auth state in localStorage for persistence
                                                        if (resources.user && resources.session) {
                                                            window?.dash_clientside?.set_props('clerk_user_update', {data: new Date().toISOString()});
                                                            if (!clerk_logged_in) {
                                                                console.log('logging in Clerk user');
                                                                setTimeout(() => {
                                                                var callbackUrl = window.location.origin + (window.location.pathname == '/auth_callback' ? window.location.pathname : '/auth_callback?redirect_url=' + encodeURIComponent(window.location.href))
                                                                fetch(callbackUrl, {
                                                                    method: 'POST',
                                                                    redirect: 'follow',
                                                                    credentials: 'same-origin'
                                                                }).then(response => {
                                                                    localStorage.setItem('clerk_logged_in', true);
                                                                    window.location.href = response.url;
                                                                });
                                                                }, 400);
                                                            } else {
                                                                console.log('Clerk session updated');
                                                            }
                                                        }
                                                        else if (clerk_logged_in) {
                                                            localStorage.setItem('clerk_logged_in', false);
                                                            console.log('session ended, logging out');
                                                            """
            + f"""newLoc = window.location.origin + '{self.logout_route}';"""
            + """
                                                            window.location.href = newLoc;
                                                        }
                                                        else {
                                                            localStorage.setItem('clerk_logged_in', false);
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

        self.clerk_script = f"{clerk_script}\n{init_script}\n"

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

    def _create_redirect_uri(self):
        """Create the redirect uri based on callback endpoint and idp."""
        kwargs = {"_external": True}
        if self.force_https_callback:
            kwargs["_scheme"] = "https"

        redirect_uri = urljoin(
            self.clerk_domain,
            "/sign-in?redirect_url="
            + quote(request.host_url[:-1] + self.callback_route, safe=""),
        )
        session["url"] = (
            request.url
            if request.method == "GET"
            else request.headers.get("referer", request.host_url)
        )
        if request.headers.get("X-Forwarded-Host"):
            host = request.headers.get("X-Forwarded-Host")
            redirect_uri = redirect_uri.replace(request.host, host, 1)
        return redirect_uri

    def login_request(self):
        """Start the login process."""
        if request.method == "POST":
            return jsonify(
                {
                    "multi": True,
                    "sideUpdate": {
                        "_clerk_login_url": {"href": self._create_redirect_uri()}
                    },
                }
            )
        return redirect(self._create_redirect_uri())

    def logout(self):  # pylint: disable=C0116
        """Logout the user."""
        if "user" in session:
            try:
                self.clerk_client.sessions.revoke(
                    session_id=session.get("user", {}).get("session_id", "")
                )
            except Exception as e:
                logging.error(
                    "Failed to revoke Clerk session: %s\n%s", e, traceback.format_exc()
                )
        session.clear()
        response = Response(
            self.logout_page
            or f"""
        <div style="display: flex; flex-direction: column;
        gap: 0.75rem; padding: 3rem 5rem;">
            <div>Logged out successfully</div>
            <div><a href="{self.app.config.get("url_base_pathname") or "/"}">Go back</a></div>
        </div>
        {self.clerk_script}
        """,
            mimetype="text/html",
        )
        for cookie in request.cookies:
            response.delete_cookie(cookie)
        return response

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
            session["user"] = {
                "clerk_user_id": user.id,
                "userid": user.username,
                "email": email,
                "session_id": sid,
            }
            if callable(self._user_groups):
                session["user"]["groups"] = self._user_groups(email) + (
                    session["user"].get("groups") or []
                )
            elif self._user_groups:
                session["user"]["groups"] = self._user_groups.get(email, []) + (
                    session["user"].get("groups") or []
                )
            if self.log_signins:
                logging.info("User %s is logging in.", session["user"].get("email"))
        if session.get("url"):
            url = session["url"]
            del session["url"]
            return redirect(url)
        return {"status": "ok", "content": "User logged in successfully."}

    def check_clerk_auth(self):
        """Pulls Clerk user data from the request and stores it in the session."""
        if request.args.get("redirect_url"):
            # If redirect_uri is provided, use it
            session["url"] = unquote(request.args.get("redirect_url"))

        request_state = self.clerk_client.authenticate_request(
            request,
            self.authenticate_request_options(
                authorized_parties=self.allowed_parties,
            ),
        )

        if request_state.is_signed_in:
            sid = request_state.payload.get("sid")
            sess = self.clerk_client.sessions.get(session_id=sid)
            user_data = self.clerk_client.users.get(user_id=sess.user_id)
            return self.after_logged_in(user_data, sid)
        return f"""<div>logging in...</div>{self.clerk_script}"""

    def is_authorized(self):  # pylint: disable=C0116
        """Check whether the user is authenticated."""

        map_adapter = Map(
            [
                Rule(x)
                for x in [self.login_route, self.logout_route, self.callback_route]
                if x
            ]
        ).bind("")

        if (
            "user" in session
            or map_adapter.test(request.path)
            or self.clerk_domain in request.url
            or request.path.startswith("/.well-known/")
        ):
            return True
        return False

    def set_loggedin_if_user_session(self, response: Response):
        """Set the response data to indicate if the user is logged in."""
        try:
            if session.get("user") and request.path == "/_dash-update-component":
                response_data = response.get_json()
                sideUpdate = response_data.get("sideUpdate", {})
                response_data["sideUpdate"] = {
                    **sideUpdate,
                    "clerk_logged_in": {"data": True},
                }
                return flask.make_response(response_data)
        except Exception:
            logging.error(
                "Error setting logged in state: %s\n%s",
                traceback.format_exc(),
                exc_info=True,
            )
            pass
        return response

    def get_user_data(self):
        request_state = self.clerk_client.authenticate_request(
            request,
            self.authenticate_request_options(
                authorized_parties=self.allowed_parties,
            ),
        )

        if request_state.is_signed_in:
            sid = request_state.payload.get("sid")
            sess = self.clerk_client.sessions.get(session_id=sid)
            user_data = self.clerk_client.users.get(user_id=sess.user_id)
            return user_data.__dict__
        return False  # "user not authenticated"
