from __future__ import absolute_import
from abc import ABC, abstractmethod
import inspect
import logging
import os
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
        setattr(self.app, "_dash_auth_plus_auth", self)
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

    def _normalized_request_path(self, path):
        """Normalize a request path against Dash's base pathname.

        Some backends can surface paths with `url_base_pathname` included.
        Public-route and auth route maps are typically defined without that
        prefix, so we strip it when present.
        """
        if not path:
            return "/"

        normalized = str(path)
        if not normalized.startswith("/"):
            normalized = "/" + normalized

        base_path = (self.app.config.get("url_base_pathname") or "/").rstrip("/")
        if base_path and base_path != "/":
            if normalized == base_path:
                return "/"
            prefix = base_path + "/"
            if normalized.startswith(prefix):
                return "/" + normalized[len(prefix) :]

        return normalized

    def _path_matches_map(self, route_map, path):
        """Test path against a Werkzeug map, with base-path normalization."""
        normalized = self._normalized_request_path(path)
        return route_map.test(path) or (
            normalized != path and route_map.test(normalized)
        )

    def _get_callback_body_sync(self, req):
        """Read callback request JSON for sync backends.

        If the backend exposes an async-only getter, return an empty body.
        """
        get_json = getattr(req, "get_json", None)
        if not callable(get_json):
            return {}
        if inspect.iscoroutinefunction(get_json):
            return {}

        body = get_json()
        if inspect.isawaitable(body):
            # Defensive: close unexpected coroutine objects to avoid warnings.
            close = getattr(body, "close", None)
            if callable(close):
                close()
            return {}

        return body if isinstance(body, dict) else {}

    async def _get_callback_body_async(self, req):
        """Read callback request JSON for async-capable backends."""
        get_json = getattr(req, "get_json", None)
        if not callable(get_json):
            return {}

        body = get_json()
        if inspect.isawaitable(body):
            body = await body
        return body if isinstance(body, dict) else {}

    def _wrap_route_with_request_context(self, view_func):
        """Wrap FastAPI auth routes so Dash's request context var is always set."""
        if getattr(self.app.backend, "server_type", None) != "fastapi":
            return view_func

        try:
            from dash.backends._fastapi import (
                set_current_request,
                reset_current_request,
            )
        except Exception:
            return view_func

        def wrapped(request, *args, **kwargs):
            token = set_current_request(request)
            try:
                return view_func(*args, **kwargs)
            finally:
                reset_current_request(token)

        return wrapped

    @property
    def _session_cookie_name(self):
        return "dash_auth_plus_session"

    def _get_server_config(self):
        return getattr(self.app.server, "config", None)

    def _get_auth_settings(self):
        settings = getattr(self.app, "_dash_auth_plus_settings", None)
        if settings is None:
            settings = {}
            setattr(self.app, "_dash_auth_plus_settings", settings)
        return settings

    def _get_config_value(self, key, default=None):
        settings = self._get_auth_settings()
        if key in settings:
            return settings[key]
        if key in self.app.config:
            return self.app.config.get(key)
        server_config = self._get_server_config()
        if server_config is not None and hasattr(server_config, "get"):
            return server_config.get(key, default)
        return default

    def _set_config_value(self, key, value):
        self._get_auth_settings()[key] = value
        server_config = self._get_server_config()
        if server_config is not None:
            try:
                server_config[key] = value
            except Exception:
                pass

    def _get_secret_key(self):
        secret_key = (
            self._get_auth_settings().get("SECRET_KEY")
            or getattr(self.app.server, "secret_key", None)
            or os.environ.get("DASH_AUTH_PLUS_SECRET_KEY")
        )
        return secret_key

    def _set_secret_key(self, secret_key):
        self._get_auth_settings()["SECRET_KEY"] = secret_key
        try:
            self.app.server.secret_key = secret_key
        except Exception:
            pass

    @property
    def _session_cookie_secure(self):
        return bool(self._get_config_value("SESSION_COOKIE_SECURE", False))

    def _session_cookie_path(self):
        return self.app.config.get("url_base_pathname") or "/"

    def _get_session_serializer(self):
        secret_key = self._get_secret_key()
        if secret_key is None:
            raise RuntimeError("Session is not available. Have you set a secret key?")
        return URLSafeSerializer(secret_key, salt="dash-auth-plus-session")

    def _get_request_context(self, request_ref):
        """Return mutable per-request context for Flask/FastAPI adapters."""
        ctx = getattr(request_ref, "context", None)
        if ctx is not None:
            return ctx

        state = getattr(request_ref, "state", None)
        if state is not None:
            return state

        fallback = getattr(request_ref, "_dash_auth_plus_context", None)
        if fallback is None:
            fallback = {}
            try:
                setattr(request_ref, "_dash_auth_plus_context", fallback)
            except Exception:
                pass
        return fallback

    @staticmethod
    def _context_get(ctx, key, default=None):
        if isinstance(ctx, dict):
            return ctx.get(key, default)
        return getattr(ctx, key, default)

    @staticmethod
    def _context_set(ctx, key, value):
        if isinstance(ctx, dict):
            ctx[key] = value
            return
        setattr(ctx, key, value)

    def _get_session(self, req=None):
        """Get backend-agnostic session data from a signed cookie."""
        request_ref = req if req is not None else self._get_request()
        ctx = self._get_request_context(request_ref)
        cached = self._context_get(ctx, "_dash_auth_plus_session")
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

        self._context_set(ctx, "_dash_auth_plus_session", session_data)
        return session_data

    @staticmethod
    def _sync_flask_session(session_data):
        try:
            from flask import has_request_context, session as flask_session
        except Exception:
            return

        if not has_request_context():
            return

        for key, value in session_data.items():
            flask_session[key] = value

    @staticmethod
    def _clear_flask_session():
        try:
            from flask import has_request_context, session as flask_session
        except Exception:
            return

        if has_request_context():
            flask_session.clear()

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
            req_path = self._normalized_request_path(getattr(req, "path", None))
            public_routes = get_public_routes(self.app)
            public_callbacks = get_public_callbacks(self.app)

            # Handle Dash's callback route:
            # * Check whether the callback is marked as public
            # * Check whether the callback is performed on route change in
            #   which case the path should be checked against the public routes
            if req_path == "/_dash-update-component":
                body = self._get_callback_body_sync(req)

                # Check whether the callback is marked as public
                if body.get("output") in public_callbacks:
                    return None

                pathname = next(
                    (
                        inp.get("value")
                        for inp in body.get("inputs", [])
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
                if pathname and page_container_test:
                    if self.auth_protect_layouts or self._path_matches_map(
                        public_routes, pathname
                    ):
                        return None

            # If the route is not a callback route, check whether the path
            # matches a public route, or whether the request is authorised
            if self._path_matches_map(public_routes, req_path) or self.is_authorized():
                return None

            # When auth_protect_layouts is enabled, avoid redirecting only for registered pages
            if self.auth_protect_layouts:
                # Use cached data derived from page_registry to avoid
                # recomputing these structures on every request.
                page_paths, map_adapter = _get_page_paths_and_adapter()

                # Check if req.path matches any page path
                if req_path in page_paths:
                    return None

                # Check if req.path matches any page template
                if map_adapter is not None:
                    try:
                        map_adapter.match(req_path)
                        return None
                    except Exception:
                        pass

                # Also allow Dash internal endpoints
                if req_path in (
                    "/_dash-layout",
                    "/_dash-dependencies",
                ) or req_path.startswith("/_dash-component-suites/"):
                    return None

            # Otherwise, ask the user to log in
            return self.login_request()

        async def before_request_auth_async():
            req = self._get_request()
            req_path = self._normalized_request_path(getattr(req, "path", None))
            public_routes = get_public_routes(self.app)
            public_callbacks = get_public_callbacks(self.app)

            # Handle Dash's callback route:
            # * Check whether the callback is marked as public
            # * Check whether the callback is performed on route change in
            #   which case the path should be checked against the public routes
            if req_path == "/_dash-update-component":
                body = await self._get_callback_body_async(req)

                # Check whether the callback is marked as public
                if body.get("output") in public_callbacks:
                    return None

                pathname = next(
                    (
                        inp.get("value")
                        for inp in body.get("inputs", [])
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
                if pathname and page_container_test:
                    if self.auth_protect_layouts or self._path_matches_map(
                        public_routes, pathname
                    ):
                        return None

            # If the route is not a callback route, check whether the path
            # matches a public route, or whether the request is authorised
            if self._path_matches_map(public_routes, req_path) or self.is_authorized():
                return None

            # When auth_protect_layouts is enabled, avoid redirecting only for registered pages
            if self.auth_protect_layouts:
                # Use cached data derived from page_registry to avoid
                # recomputing these structures on every request.
                page_paths, map_adapter = _get_page_paths_and_adapter()

                # Check if req.path matches any page path
                if req_path in page_paths:
                    return None

                # Check if req.path matches any page template
                if map_adapter is not None:
                    try:
                        map_adapter.match(req_path)
                        return None
                    except Exception:
                        pass

                # Also allow Dash internal endpoints
                if req_path in (
                    "/_dash-layout",
                    "/_dash-dependencies",
                ) or req_path.startswith("/_dash-component-suites/"):
                    return None

            # Otherwise, ask the user to log in
            return self.login_request()

        if getattr(self.app.backend, "server_type", None) in {"quart", "fastapi"}:
            register_hook(before_request_auth_async)
        else:
            register_hook(before_request_auth)

    @abstractmethod
    def is_authorized(self):
        pass

    @abstractmethod
    def login_request(self):
        pass
