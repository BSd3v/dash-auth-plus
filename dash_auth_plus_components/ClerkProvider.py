# AUTO GENERATED FILE - DO NOT EDIT

from dash.development.base_component import Component, _explicitize_args


class ClerkProvider(Component):
    """A ClerkProvider component.
        ClerkProvider wraps your app to provide authentication context.

    Keyword arguments:

    - children (a list of or a singular dash component, string or number; optional):
        The components to render within the provider.

    - id (string; optional):
        The ID used to identify this component in Dash callbacks.

    - PUBLISHABLE_KEY (string; required):
        The Clerk publishable key for your application.

    - afterSignOutUrl (string; optional):
        URL to redirect to after sign out."""

    _children_props = []
    _base_nodes = ["children"]
    _namespace = "dash_auth_plus_components"
    _type = "ClerkProvider"

    @_explicitize_args
    def __init__(
        self,
        children=None,
        id=Component.UNDEFINED,
        PUBLISHABLE_KEY=Component.REQUIRED,
        afterSignOutUrl=Component.UNDEFINED,
        **kwargs
    ):
        self._prop_names = ["children", "id", "PUBLISHABLE_KEY", "afterSignOutUrl"]
        self._valid_wildcard_attributes = []
        self.available_properties = [
            "children",
            "id",
            "PUBLISHABLE_KEY",
            "afterSignOutUrl",
        ]
        self.available_wildcard_properties = []
        _explicit_args = kwargs.pop("_explicit_args")
        _locals = locals()
        _locals.update(kwargs)  # For wildcard attrs and excess named props
        args = {k: _locals[k] for k in _explicit_args}

        for k in ["PUBLISHABLE_KEY"]:
            if k not in args:
                raise TypeError("Required argument `" + k + "` was not specified.")

        super(ClerkProvider, self).__init__(**args)
