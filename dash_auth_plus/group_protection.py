import logging
import re
from typing import Any, Callable, List, Literal, Optional, Union
from werkzeug.routing import MapAdapter

import dash
from dash.exceptions import PreventUpdate
from flask import session, has_request_context
from dash import html


OutputVal = Union[Callable[[], Any], Any]
CheckType = Literal["one_of", "all_of", "none_of"]


def list_groups(
    *,
    groups_key: str = "groups",
    groups_str_split: str = None,
) -> Optional[List[str]]:
    """List all the groups the user belongs to.

    :param groups_key: Groups key in the user data saved in the Flask session
        e.g. session["user"] == {"email": "a.b@mail.com", "groups": ["admin"]}
    :param groups_str_split: Used to split groups if provided as a string
    :return: None or list[str]:
        * None if the user is not authenticated
        * list[str] otherwise
    """
    if not has_request_context() or "user" not in session:
        return None

    user_groups = session.get("user", {}).get(groups_key, [])
    # Handle cases where groups are ,- or ;-separated string,
    # may depend on OIDC provider
    if isinstance(user_groups, str) and groups_str_split is not None:
        user_groups = re.split(groups_str_split, user_groups)
    return user_groups


def check_groups(
    groups: Optional[Union[Callable, List[str]]] = None,
    *,
    groups_key: str = "groups",
    groups_str_split: str = None,
    check_type: CheckType = "one_of",
    group_lookup: dict = None,
    restricted_users: Optional[Union[Callable, List[str]]] = None,
    restricted_users_lookup: dict = None,
    user_session_key: str = "email",
) -> Optional[bool]:
    """Check whether the current user is authenticated
    and has the specified groups.

    :param groups: List of groups or a python function
        to return a list of groups.
        If this is a function, will be called with group_lookup dict as kwargs.
        The result is used to check for with check_type
    :param groups_key: Groups key in the user data saved in the Flask session
        e.g. session["user"] == {"email": "a.b@mail.com", "groups": ["admin"]}
    :param groups_str_split: Used to split groups if provided as a string
    :param check_type: Type of check to perform.
        Either "one_of", "all_of" or "none_of"
    :param group_lookup: A dictionary of kwargs to be passed
        if groups is a function.
        e.g. {"path": "/test"} will work with this as a
        groups function: check_path(path)
    :param restricted_users: List of restricted users or a python function
        to return a list of users.
         If this is a function, will be called with
         restricted_users_lookup dict as kwargs.
    :param restricted_users_lookup: A dictionary of kwargs to be passed
        if restricted_users is a function.
        e.g. {"path": "/test"} will work with this as a
        restricted_users function: check_users_path(path)
    :param user_session_key: String of a key in the session["user"] cookie
        where the user will be used to determine whether they are
        in the list of restricted_users. Defaults to "email".
    :return: None or boolean:
        * None if the user is not authenticated
        * True if the user is authenticated and has the right permissions
        * False if the user is authenticated but does not have
          the right permissions
    """
    user_groups = list_groups(
        groups_key=groups_key,
        groups_str_split=groups_str_split,
    )

    if user_groups is None:
        # User is not authenticated
        return None

    if restricted_users:
        if callable(restricted_users):
            restricted_users = restricted_users(**(restricted_users_lookup or {}))
        if session["user"][user_session_key] in restricted_users:
            # User is restricted
            return False
    if callable(groups):
        groups = groups(**(group_lookup or {}))
    if groups is None:
        return True

    if check_type == "one_of":
        return bool(set(user_groups).intersection(groups))
    if check_type == "all_of":
        return all(group in user_groups for group in groups)
    if check_type == "none_of":
        return not any(group in user_groups for group in groups)

    raise ValueError(f"Invalid check_type: {check_type}")


def protected(
    unauthenticated_output: OutputVal,
    *,
    missing_permissions_output: Optional[OutputVal] = None,
    groups: Optional[Union[Callable, List[str]]] = None,
    groups_key: str = "groups",
    groups_str_split: str = None,
    check_type: CheckType = "one_of",
    group_lookup: dict = None,
    restricted_users: Optional[Union[Callable, List[str]]] = None,
    restricted_users_lookup: dict = None,
    user_session_key: str = "email",
    **_kwargs,
) -> Callable:
    """Decorate a function or output to alter it depending on the state
    of authentication and permissions.

    :param unauthenticated_output: Output when the user is not authenticated.
        Note: needs to be a function with no argument or static outputs.
    :param missing_permissions_output: Output when the user is authenticated
        but does not have the right permissions.
        It defaults to unauthenticated_output when not set.
        Note: needs to be a function with no argument or static outputs.
    :param groups: List of authorized user groups
        or a python function to return a list of groups.
        If this is a function, will be called with group_lookup dict as kwargs.
        If no groups are passed,
        the decorator will only check whether the user is authenticated.
    :param groups_key: Groups key in the user data saved in the Flask session
        e.g. session["user"] == {"email": "a.b@mail.com", "groups": ["admin"]}
    :param groups_str_split: Used to split groups if provided as a string
    :param check_type: Type of check to perform.
        Either "one_of", "all_of" or "none_of"
    :param group_lookup: A dictionary of kwargs to be passed
        if groups is a function.
        e.g. {"path": "/test"} will work with this as a
        groups function: check_path(path)
    :param restricted_users: List of restricted users or a python function
        to return a list of users.
         If this is a function, will be called with
         restricted_users_lookup dict as kwargs.
    :param restricted_users_lookup: A dictionary of kwargs to be passed
        if restricted_users is a function.
        e.g. {"path": "/test"} will work with this as a
        restricted_users function: check_users_path(path)
    :param user_session_key: String of a key in the session["user"] cookie
        where the user will be used to determine whether they are
        in the list of restricted_users. Defaults to "email".
    """

    if missing_permissions_output is None:
        missing_permissions_output = unauthenticated_output

    def decorator(output: OutputVal):
        def wrap(*args, **kwargs):
            def process_output(output, *args, **kwargs):
                if isinstance(output, Callable):
                    return output(*args, **kwargs)
                return output

            authorized = check_groups(
                groups=groups,
                groups_key=groups_key,
                groups_str_split=groups_str_split,
                check_type=check_type,
                group_lookup=group_lookup,
                restricted_users=restricted_users,
                restricted_users_lookup=restricted_users_lookup,
                user_session_key=user_session_key,
            )
            if authorized is None:
                return process_output(unauthenticated_output)
            if authorized:
                return process_output(output, *args, **kwargs)
            return process_output(missing_permissions_output)

        if isinstance(output, Callable):
            return wrap
        return wrap()

    return decorator


def protected_callback(
    *callback_args,
    unauthenticated_output: Optional[OutputVal] = None,
    missing_permissions_output: Optional[OutputVal] = None,
    groups: Optional[Union[Callable, List[str]]] = None,
    groups_key: str = "groups",
    groups_str_split: str = None,
    check_type: CheckType = "one_of",
    group_lookup: dict = None,
    restricted_users: Optional[Union[Callable, List[str]]] = None,
    restricted_users_lookup: dict = None,
    user_session_key: str = "email",
    **callback_kwargs,
) -> Callable:
    """Protected Dash callback.

    :param **: all args and kwargs passed to a Dash callback
    :param unauthenticated_output: Output when the user is not authenticated.
        **Note**: Needs to be a function with no argument or static outputs.
        You can access the Dash callback context within the function call if
        you need to use some of the inputs/states of the callback.
        If left as None, it will simply raise PreventUpdate, stopping the
        callback from processing.
    :param missing_permissions_output: Output when the user is authenticated
        but does not have the right permissions.
        It defaults to unauthenticated_output when not set.
        **Note**: Needs to be a function with no argument or static outputs.
        You can access the Dash callback context within the function call if
        you need to use some of the inputs/states of the callback.
        If left as None, it will simply raise PreventUpdate, stopping the
        callback from processing.
    :param groups: List of authorized user groups
        or a python function to return a list of groups.
        If this is a function, will be called with group_lookup dict as kwargs.
    :param groups_key: Groups key in the user data saved in the Flask session
        e.g. session["user"] == {"email": "a.b@mail.com", "groups": ["admin"]}
    :param groups_str_split: Used to split groups if provided as a string
    :param check_type: Type of check to perform.
        Either "one_of", "all_of" or "none_of"
    :param group_lookup: A dictionary of kwargs to be passed
        if groups is a function.
        e.g. {"path": "/test"} will work with this as a
        groups function: check_path(path)
    :param restricted_users: List of restricted users or a python function
        to return a list of users.
         If this is a function, will be called with
         restricted_users_lookup dict as kwargs.
    :param restricted_users_lookup: A dictionary of kwargs to be passed
        if restricted_users is a function.
        e.g. {"path": "/test"} will work with this as a
        restricted_users function: check_users_path(path)
    :param user_session_key: String of a key in the session["user"] cookie
        where the user will be used to determine whether they are
        in the list of restricted_users. Defaults to "email".
    """

    def decorator(func):
        def prevent_unauthenticated():
            logging.info(
                "A user tried to run %s without being authenticated.",
                func.__name__,
            )
            raise PreventUpdate

        def prevent_unauthorised():
            logging.info(
                "%s tried to run %s but did not have the right permissions.",
                session["user"]["email"],
                func.__name__,
            )
            raise PreventUpdate

        wrapped_func = dash.callback(*callback_args, **callback_kwargs)(
            protected(
                unauthenticated_output=(
                    unauthenticated_output
                    if unauthenticated_output is not None
                    else prevent_unauthenticated
                ),
                missing_permissions_output=(
                    missing_permissions_output
                    if missing_permissions_output is not None
                    else prevent_unauthorised
                ),
                groups=groups,
                groups_key=groups_key,
                groups_str_split=groups_str_split,
                check_type=check_type,
                group_lookup=group_lookup,
                restricted_users=restricted_users,
                restricted_users_lookup=restricted_users_lookup,
                user_session_key=user_session_key,
            )(func)
        )

        def wrap(*args, **kwargs):
            return wrapped_func(*args, **kwargs)

        return wrap

    return decorator


def protect_layouts(
    public_routes: Union[List[str], MapAdapter] = None, **kwargs
) -> str:
    if "pages_folder" in dash.get_app().config:
        for pg in dash.page_registry.values():
            new_kwargs = {**kwargs, **pg}
            if new_kwargs.get("unauthenticated_output") is None:
                new_kwargs["unauthenticated_output"] = html.Div(
                    "You do not have access to this content."
                )
            if public_routes:
                if isinstance(public_routes, list):
                    if not (
                        pg["path"] in public_routes
                        or pg.get("path_template") in public_routes
                    ):
                        pg["layout"] = protected(**new_kwargs)(pg["layout"])
                elif not (
                    public_routes.test(pg.get("path_template"))
                    or public_routes.test(pg["path"])
                ):
                    pg["layout"] = protected(**new_kwargs)(pg["layout"])
            else:
                pg["layout"] = protected(**new_kwargs)(pg["layout"])
        return "your layouts are now protected"
