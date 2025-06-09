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
try:
    from .oidc_auth import OIDCAuth, get_oauth
    from .clerk_auth import ClerkAuth
except ModuleNotFoundError:
    pass
from .version import __version__, __plotly_dash_auth_version__


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
    "__version__",
    "__plotly_dash_auth_version__",
]
