from __future__ import absolute_import
from abc import ABC, abstractmethod
from typing import Optional, Union

from dash import Dash
from flask import request

from .public_routes import (
    add_public_routes,
    get_public_callbacks,
    get_public_routes,
)
from .group_protection import protect_layouts
from werkzeug.routing import Map, Rule

import diskcache
import hashlib

cache = None  # Lazily initialized diskcache.Cache instance


def _get_page_paths_and_adapter():
    global cache

    # Lazily import dash and obtain page_registry if available to
    # preserve compatibility with older Dash versions that lack it.
    try:
        import dash

        registry = getattr(dash, "page_registry", {})
    except ImportError:
        registry = {}

    # Lazily initialize the diskcache.Cache to avoid filesystem side
    # effects at import time. If initialization fails (e.g., on a
    # read-only filesystem), caching is simply disabled.
    if cache is None:
        try:
            cache = diskcache.Cache("./dash-auth-cache")  # or any directory
        except Exception:
            cache = None

    # Build a deterministic signature (hash) of the current registry
    signature = hashlib.sha256(repr(registry).encode()).hexdigest()

    cache_key = f"dash_page_registry_{signature}"

    # Try to load from cache, if available
    result = None
    if cache is not None:
        result = cache.get(cache_key)
    if result:
        return result["paths"], result["adapter"]

    # Compute new values
    page_paths = [pg["path"] for pg in registry.values() if "path" in pg]
    page_templates = [
        pg.get("path_template") for pg in registry.values() if pg.get("path_template")
    ]
    adapter = None
    if page_templates:
        adapter = Map([Rule(t) for t in page_templates]).bind("")

    # Save to cache atomically, if caching is enabled
    if cache is not None:
        cache.set(cache_key, {"paths": page_paths, "adapter": adapter})

    return page_paths, adapter


#
# def _get_page_paths_and_adapter():
#     """
#     Lazily compute and cache page paths and the compiled MapAdapter
#     used to match path templates. This avoids rebuilding these
#     structures on every request in the before_request handler.
#
#     The cache is keyed by a simple, deterministic signature derived
#     from dash.page_registry so that changes to registered pages
#     (e.g. in tests, hot reload, or dynamic registration) will cause
#     the cached data to be refreshed.
#     """
#
#     # Lazily import dash and obtain page_registry if available to
#     # preserve compatibility with older Dash versions that lack it.
#     try:
#         import dash
#
#         registry = getattr(dash, "page_registry", {})
#     except ImportError:
#         registry = {}
#
#     global _cached_page_paths, _cached_page_templates_adapter, _cached_page_registry_signature
#
#     # Build a deterministic signature of the current page_registry
#     # based on the route name, path, and path_template. This is
#     # lightweight and sufficient to detect changes relevant to auth.
#     current_signature = tuple(
#         sorted(
#             (
#                 name,
#                 pg.get("path"),
#                 pg.get("path_template"),
#             )
#             for name, pg in registry.items()
#         )
#     )
#
#     # If already cached and the registry hasn't changed, reuse.
#     if (
#         _cached_page_paths is not None
#         and _cached_page_registry_signature == current_signature
#     ):
#         return _cached_page_paths, _cached_page_templates_adapter
#
#     # For Dash 2.x/3.x, use page_registry to build the paths and templates.
#     page_paths = [pg["path"] for pg in registry.values() if "path" in pg]
#     page_templates = [
#         pg.get("path_template") for pg in registry.values() if pg.get("path_template")
#     ]
#
#     # Cache the simple path list and the signature.
#     _cached_page_paths = page_paths
#     _cached_page_registry_signature = current_signature
#
#     # Build and cache the MapAdapter only if templates exist.
#     if page_templates:
#         _cached_page_templates_adapter = Map([Rule(t) for t in page_templates]).bind("")
#     else:
#         _cached_page_templates_adapter = None
#
#     return _cached_page_paths, _cached_page_templates_adapter


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

    def _protect(self):
        """Add a before_request authentication check on all routes.

        The authentication check will pass if either
            * The endpoint is marked as public via `add_public_routes`
            * The request is authorised by `Auth.is_authorised`
        """

        server = self.app.server

        @server.before_request
        def before_request_auth():
            public_routes = get_public_routes(self.app)
            public_callbacks = get_public_callbacks(self.app)

            # Handle Dash's callback route:
            # * Check whether the callback is marked as public
            # * Check whether the callback is performed on route change in
            #   which case the path should be checked against the public routes
            if request.path == "/_dash-update-component":
                body = request.get_json()

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
            if public_routes.test(request.path) or self.is_authorized():
                return None

            # When auth_protect_layouts is enabled, avoid redirecting only for registered pages
            if self.auth_protect_layouts:
                # Use cached data derived from page_registry to avoid
                # recomputing these structures on every request.
                page_paths, map_adapter = _get_page_paths_and_adapter()

                # Check if request.path matches any page path
                if request.path in page_paths:
                    return None

                # Check if request.path matches any page template
                if map_adapter is not None:
                    try:
                        map_adapter.match(request.path)
                        return None
                    except Exception:
                        pass

                # Also allow Dash internal endpoints
                if request.path in (
                    "/_dash-layout",
                    "/_dash-dependencies",
                ) or request.path.startswith("/_dash-component-suites/"):
                    return None

            # Otherwise, ask the user to log in
            return self.login_request()

    @abstractmethod
    def is_authorized(self):
        pass

    @abstractmethod
    def login_request(self):
        pass
