from __future__ import absolute_import
from abc import ABC, abstractmethod
import logging
from typing import Optional, Union

from dash import Dash
from itsdangerous import BadSignature, URLSafeSerializer

from .public_routes import (
    add_public_routes,
    get_public_callbacks,
    get_public_routes,
)
from .group_protection import protect_layouts
from werkzeug.routing import Map, Rule

_cached_page_registry_data = (
    None  # In-process cache; page_registry is fixed after startup
)


def _get_page_paths_and_adapter():
    global _cached_page_registry_data

    if _cached_page_registry_data is not None:
        return _cached_page_registry_data

    try:
        import dash

        registry = getattr(dash, "page_registry", {})
    except ImportError:
        registry = {}

    page_paths = [pg["path"] for pg in registry.values() if "path" in pg]
    page_templates = [
        pg.get("path_template") for pg in registry.values() if pg.get("path_template")
    ]

    adapter = None
    if page_templates:
        adapter = Map([Rule(t) for t in page_templates]).bind("")

    _cached_page_registry_data = (page_paths, adapter)
    return _cached_page_registry_data


class Auth(ABC):
    def __init__(
        self,
        app: Dash,
        public_routes: Optional[list] = None,
        auth_protect_layouts: Optional[Union[dict, bool]] = False,
        auth_protect_layouts_kwargs: Optional[dict] = None,
        page_container: Optional[str] = None,
        **obsolete,
    ):
        """Auth base class for authentication in Dash.

        :param app: Dash app
        :param public_routes: list of public routes, routes should follow the
            Flask route syntax
        :param auth_protect_layouts: bool, defaults to False.
            If true, runs protect_layout()
        :param auth_protect_layouts_kwargs: dict, if provided is passed to the
            protect_layout as kwargs
        :param page_container: string, id of the page container in the app.
            If not provided, this will set the page_container_test to True,
            meaning all pathname callbacks will be judged.
        """

        # Deprecated arguments
        if obsolete:
            raise TypeError(f"Auth got unexpected keyword arguments: {list(obsolete)}")

        self.app = app
        self._protect()
        self.auth_protect_layouts = auth_protect_layouts
        self.page_container = page_container
        if public_routes is not None:
            add_public_routes(app, public_routes)
        if self.auth_protect_layouts:
            protect_layouts(
                public_routes=get_public_routes(self.app),
                **(auth_protect_layouts_kwargs or {}),
            )

    def _get_request(self):
        """Return the current request object using a backend-agnostic approach.

        This delegates to Dash's backend request adapter.
        """
        return self.app.backend.request_adapter()

    @property
    def _session_cookie_name(self):
        return "dash_auth_plus_session"

    @property
    def _session_cookie_secure(self):
        return bool(self.app.server.config.get("SESSION_COOKIE_SECURE", False))

    def _session_cookie_path(self):
        return self.app.config.get("url_base_pathname") or "/"

    def _get_session_serializer(self):
        secret_key = getattr(self.app.server, "secret_key", None)
        if secret_key is None:
            raise RuntimeError("Session is not available. Have you set a secret key?")
        return URLSafeSerializer(secret_key, salt="dash-auth-plus-session")

    def _get_session(self, req=None):
        """Get backend-agnostic session data from a signed cookie."""
        request_ref = req if req is not None else self._get_request()
        ctx = request_ref.context

        if isinstance(ctx, dict):
            cached = ctx.get("_dash_auth_plus_session")
        else:
            cached = getattr(ctx, "_dash_auth_plus_session", None)
        if cached is not None:
            return cached

        serializer = self._get_session_serializer()
        raw = request_ref.cookies.get(self._session_cookie_name)
        if not raw:
            session_data = {}
        else:
            try:
                loaded = serializer.loads(raw)
                session_data = loaded if isinstance(loaded, dict) else {}
            except BadSignature:
                logging.warning(
                    "Discarding tampered %s cookie due to invalid signature.",
                    self._session_cookie_name,
                )
                session_data = {}

        if isinstance(ctx, dict):
            ctx["_dash_auth_plus_session"] = session_data
        else:
            setattr(ctx, "_dash_auth_plus_session", session_data)
        return session_data

    def _save_session(self, response, session_data):
        """Persist backend-agnostic session data in a signed cookie."""
        serializer = self._get_session_serializer()
        response.set_cookie(
            self._session_cookie_name,
            serializer.dumps(session_data),
            secure=self._session_cookie_secure,
            httponly=True,
            samesite="Lax",
            path=self._session_cookie_path(),
        )
        return response

    def _clear_session(self, response):
        response.delete_cookie(
            self._session_cookie_name,
            path=self._session_cookie_path(),
        )
        return response

    def _redirect_response(self, target_url):
        response = self.app.backend.make_response("", status=302)
        response.headers["Location"] = target_url
        return response

    def _protect(self):
        """Add a before_request authentication check on all routes.

        The authentication check will pass if either
            * The endpoint is marked as public via `add_public_routes`
            * The request is authorised by `Auth.is_authorised`
        """

        register_hook = self.app.backend.before_request

        def before_request_auth():
            req = self._get_request()
            public_routes = get_public_routes(self.app)
            public_callbacks = get_public_callbacks(self.app)

            # Handle Dash's callback route:
            # * Check whether the callback is marked as public
            # * Check whether the callback is performed on route change in
            #   which case the path should be checked against the public routes
            if req.path == "/_dash-update-component":
                body = req.get_json()

                # Check whether the callback is marked as public
                if body["output"] in public_callbacks:
                    return None

                pathname = next(
                    (
                        inp.get("value")
                        for inp in body["inputs"]
                        if isinstance(inp, dict) and inp.get("property") == "pathname"
                    ),
                    None,
                )
                if self.page_container:
                    page_container_test = next(
                        (
                            out
                            for out in body.get("outputs", [])
                            if isinstance(out, dict)
                            and out.get("id") == self.page_container
                            and out.get("property") == "children"
                        ),
                        None,
                    )
                else:
                    page_container_test = True

                # Check whether the callback has an input using the pathname,
                # such a callback will be a routing callback and the pathname
                # should be checked against the public routes
                if not self.auth_protect_layouts:
                    if (
                        pathname
                        and page_container_test
                        and public_routes.test(pathname)
                    ):
                        return None
                else:
                    # protected by layout
                    if pathname and page_container_test:
                        return None

            # If the route is not a callback route, check whether the path
            # matches a public route, or whether the request is authorised
            if public_routes.test(req.path) or self.is_authorized():
                return None

            # When auth_protect_layouts is enabled, avoid redirecting only for registered pages
            if self.auth_protect_layouts:
                # Use cached data derived from page_registry to avoid
                # recomputing these structures on every request.
                page_paths, map_adapter = _get_page_paths_and_adapter()

                # Check if req.path matches any page path
                if req.path in page_paths:
                    return None

                # Check if req.path matches any page template
                if map_adapter is not None:
                    try:
                        map_adapter.match(req.path)
                        return None
                    except Exception:
                        pass

                # Also allow Dash internal endpoints
                if req.path in (
                    "/_dash-layout",
                    "/_dash-dependencies",
                ) or req.path.startswith("/_dash-component-suites/"):
                    return None

            # Otherwise, ask the user to log in
            return self.login_request()

        register_hook(before_request_auth)

    @abstractmethod
    def is_authorized(self):
        pass

    @abstractmethod
    def login_request(self):
        pass
