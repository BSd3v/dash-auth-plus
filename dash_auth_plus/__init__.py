from .public_routes import add_public_routes, public_callback
from .basic_auth import BasicAuth
from .group_protection import (
    list_groups,
    check_groups,
    protected,
    protected_callback,
    protect_layouts,
)

# oidc auth requires authlib, install with `pip install dash-auth-plus[oidc]`
# clerk auth requires authlib, clerk-sdk, clerk-backend-api, install with `pip install dash-auth-plus[clerk]`
try:
    from .oidc_auth import OIDCAuth, get_oauth
    from .clerk_auth import ClerkAuth
    from . import DashAuthComponents

    _css_dist = DashAuthComponents._css_dist
    _js_dist = DashAuthComponents._js_dist
except ModuleNotFoundError:
    pass
from ._version import __version__, __plotly_dash_auth_version__

__all__ = [
    "add_public_routes",
    "check_groups",
    "list_groups",
    "get_oauth",
    "protect_layouts",
    "protected",
    "protected_callback",
    "public_callback",
    "BasicAuth",
    "OIDCAuth",
    "ClerkAuth",
    "DashAuthComponents",
    "__version__",
    "__plotly_dash_auth_version__",
]
