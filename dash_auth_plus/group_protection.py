import logging
import re
from typing import Any, Callable, List, Literal, Optional, Union
from werkzeug.routing import MapAdapter

import dash
from dash.exceptions import PreventUpdate
from flask import session, has_request_context
from dash import html
from inspect import Parameter, iscoroutinefunction, isawaitable, signature
from functools import lru_cache

OutputVal = Union[Callable[..., Any], Any]
CheckType = Literal["one_of", "all_of", "none_of"]


@lru_cache(maxsize=256)
def _cached_signature(func: Callable[..., Any]):
    """
    Cached wrapper around inspect.signature to avoid repeated introspection
    on the same callable in hot paths.
    """
    return signature(func)


def _process_output(output, *args, path=None, **kwargs):
    if not callable(output):
        return output
    if path is None:
        return output(*args, **kwargs)

    try:
        output_signature = _cached_signature(output)
    except (TypeError, ValueError):
        return output(*args, **kwargs)

    supports_kwargs = any(
        param.kind == Parameter.VAR_KEYWORD
        for param in output_signature.parameters.values()
    )
    path_param = output_signature.parameters.get("path")
    if supports_kwargs or (
        path_param is not None and path_param.kind is not Parameter.POSITIONAL_ONLY
    ):
        # Merge/override 'path' into kwargs so it is only passed once.
        merged_kwargs = dict(kwargs)
        merged_kwargs["path"] = path
        return output(*args, **merged_kwargs)
    return output(*args, **kwargs)


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
    path: Optional[str] = None,
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
    :param path: Current route path. When ``groups`` is callable, this is only
        forwarded as a ``path`` keyword argument if the callable accepts
        ``path`` as a keyword argument or arbitrary keyword arguments via
        ``**kwargs``.
    :param group_lookup: A dictionary of kwargs to be passed
        if groups is a function.
        e.g. {"path": "/test"} will work with this as a
        groups function: check_path(path). If ``group_lookup`` already contains
        ``path``, that explicit value is used instead of ``path=...``.
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
        has_posonly_path = False
        requires_path = False
        try:
            params = signature(groups).parameters
        except (TypeError, ValueError):
            # Fall back to calling without injecting a 'path' kwarg if the
            # callable's signature cannot be inspected (e.g. some built-ins).
            accepts_path = False
        else:
            has_kw_path = any(
                p.name == "path"
                and p.kind in (Parameter.KEYWORD_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
                for p in params.values()
            )
            has_posonly_path = any(
                p.name == "path" and p.kind is Parameter.POSITIONAL_ONLY
                for p in params.values()
            )
            has_var_kw = any(p.kind == Parameter.VAR_KEYWORD for p in params.values())
            # Only inject 'path' as a keyword if it is accepted as a keyword
            # argument, or if **kwargs is present and there is no positional-only
            # 'path' parameter that would conflict with a 'path=' kwarg.
            accepts_path = has_kw_path or (has_var_kw and not has_posonly_path)
            # Determine whether the callable defines a required 'path' parameter
            param_path = next((p for p in params.values() if p.name == "path"), None)
            if param_path is not None and param_path.default is Parameter.empty:
                requires_path = True
        kwargs = dict(group_lookup or {})
        if has_posonly_path and "path" in kwargs:
            raise TypeError(
                "The 'groups' callable defines a positional-only 'path' parameter, "
                "but 'path' was provided via group_lookup as a keyword argument. "
                "Remove 'path' from group_lookup or update the callable to accept "
                "'path' as a keyword argument."
            )
        # If the callable requires a 'path' argument but none has been provided
        # via group_lookup and no explicit 'path' is available, raise a clear
        # error instead of silently passing path=None.
        if requires_path and "path" not in kwargs and path is None:
            raise TypeError(
                "The 'groups' callable requires a 'path' argument, but neither "
                "'path' nor group_lookup['path'] was provided."
            )
        # Only inject 'path' as a keyword argument when we actually have a
        # non-None path value to pass.
        if accepts_path and "path" not in kwargs and path is not None:
            kwargs["path"] = path
        if has_posonly_path and "path" not in kwargs:
            # For callables with a positional-only 'path' parameter, pass 'path'
            # positionally rather than as a keyword argument when it is available.
            if path is not None:
                groups = groups(path, **kwargs)
            else:
                # No path value to supply positionally; let Python raise a
                # missing-argument error if 'path' is truly required.
                groups = groups(**kwargs)
        else:
            groups = groups(**kwargs)
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
        Note: can be static output, a function with no argument, or a function
        accepting a ``path`` keyword argument (either explicitly or via
        ``**kwargs``).
    :param missing_permissions_output: Output when the user is authenticated
        but does not have the right permissions.
        It defaults to unauthenticated_output when not set.
        Note: can be static output, a function with no argument, or a function
        accepting a ``path`` keyword argument (either explicitly or via
        ``**kwargs``).
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
        if iscoroutinefunction(output):

            async def async_wrap(*args, **kwargs):
                path = _kwargs.get("path_template") or _kwargs.get("path")
                authorized = check_groups(
                    groups=groups,
                    groups_key=groups_key,
                    groups_str_split=groups_str_split,
                    check_type=check_type,
                    group_lookup=group_lookup,
                    restricted_users=restricted_users,
                    restricted_users_lookup=restricted_users_lookup,
                    user_session_key=user_session_key,
                    path=path,
                )
                if authorized is None:
                    result = _process_output(unauthenticated_output, path=path)
                    return await result if isawaitable(result) else result
                if authorized:
                    result = output(*args, **kwargs)
                    return await result if isawaitable(result) else result
                result = _process_output(missing_permissions_output, path=path)
                return await result if isawaitable(result) else result

            return async_wrap
        else:

            def wrap(*args, **kwargs):
                path = _kwargs.get("path_template") or _kwargs.get("path")
                authorized = check_groups(
                    groups=groups,
                    groups_key=groups_key,
                    groups_str_split=groups_str_split,
                    check_type=check_type,
                    group_lookup=group_lookup,
                    restricted_users=restricted_users,
                    restricted_users_lookup=restricted_users_lookup,
                    user_session_key=user_session_key,
                    path=path,
                )
                if authorized is None:
                    result = _process_output(unauthenticated_output, path=path)
                    if isawaitable(result):
                        raise TypeError(
                            "Got awaitable from 'unauthenticated_output' in synchronous "
                            "protected view/callback. Async outputs are only supported "
                            "when the wrapped function is async."
                        )
                    return result
                if authorized:
                    result = _process_output(output, *args, **kwargs)
                    if isawaitable(result):
                        raise TypeError(
                            "Got awaitable from 'output' in synchronous protected "
                            "view/callback. Async outputs are only supported when the "
                            "wrapped function is async."
                        )
                    return result
                result = _process_output(missing_permissions_output, path=path)
                if isawaitable(result):
                    raise TypeError(
                        "Got awaitable from 'missing_permissions_output' in synchronous "
                        "protected view/callback. Async outputs are only supported when "
                        "the wrapped function is async."
                    )
                return result

            return wrap if callable(output) else wrap()

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
