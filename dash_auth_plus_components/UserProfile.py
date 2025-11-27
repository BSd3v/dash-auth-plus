# AUTO GENERATED FILE - DO NOT EDIT

from dash.development.base_component import Component, _explicitize_args


class UserProfile(Component):
    """A UserProfile component.
        UserProfile displays the user's profile management interface from Clerk.

    Keyword arguments:

    - children (a list of or a singular dash component, string or number; optional):
        Custom pages to add to the user profile.

    - id (string; optional):
        The ID used to identify this component in Dash callbacks."""

    _children_props = []
    _base_nodes = ["children"]
    _namespace = "dash_auth_plus_components"
    _type = "UserProfile"

    @_explicitize_args
    def __init__(self, children=None, id=Component.UNDEFINED, **kwargs):
        self._prop_names = ["children", "id"]
        self._valid_wildcard_attributes = []
        self.available_properties = ["children", "id"]
        self.available_wildcard_properties = []
        _explicit_args = kwargs.pop("_explicit_args")
        _locals = locals()
        _locals.update(kwargs)  # For wildcard attrs and excess named props
        args = {k: _locals[k] for k in _explicit_args}

        super(UserProfile, self).__init__(**args)
