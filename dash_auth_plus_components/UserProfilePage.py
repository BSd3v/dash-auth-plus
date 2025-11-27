# AUTO GENERATED FILE - DO NOT EDIT

from dash.development.base_component import Component, _explicitize_args


class UserProfilePage(Component):
    """A UserProfilePage component.
        UserProfilePage allows you to add custom pages to the UserProfile component.

    Keyword arguments:

    - children (a list of or a singular dash component, string or number; optional):
        The content to render in the custom page.

    - id (string; optional):
        The ID used to identify this component in Dash callbacks.

    - label (string; required):
        The label text for the page in the navigation.

    - labelIcon (a list of or a singular dash component, string or number; optional):
        An optional icon to display next to the label.

    - url (string; required):
        The URL path for this custom page."""

    _children_props = ["labelIcon"]
    _base_nodes = ["children", "labelIcon"]
    _namespace = "dash_auth_plus_components"
    _type = "UserProfilePage"

    @_explicitize_args
    def __init__(
        self,
        children=None,
        id=Component.UNDEFINED,
        label=Component.REQUIRED,
        labelIcon=Component.UNDEFINED,
        url=Component.REQUIRED,
        **kwargs
    ):
        self._prop_names = ["children", "id", "label", "labelIcon", "url"]
        self._valid_wildcard_attributes = []
        self.available_properties = ["children", "id", "label", "labelIcon", "url"]
        self.available_wildcard_properties = []
        _explicit_args = kwargs.pop("_explicit_args")
        _locals = locals()
        _locals.update(kwargs)  # For wildcard attrs and excess named props
        args = {k: _locals[k] for k in _explicit_args}

        for k in ["label", "url"]:
            if k not in args:
                raise TypeError("Required argument `" + k + "` was not specified.")

        super(UserProfilePage, self).__init__(**args)
