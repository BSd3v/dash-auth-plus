## Dash Authorization and Login

Offshoot authentication based upon the open source `dash-auth` library from Plotly. Plotly Docs: [https://dash.plotly.com/authentication](https://dash.plotly.com/authentication)

License: MIT

For local testing, create a virtualenv, install the dev requirements, and run individual
tests or test classes:

```
python -m venv venv
. venv/bin/activate
pip install -r dev-requirements.txt
python -k ba001
```

Note that Python 3.8 or greater is required.

> As Plotly will not add new features to the `dash-auth` library, this was created to allow for new features to be added.
> However, please note that you are entirely responsible maintaining the security with using this open source package.
> If you are looking for a full fledged solution with little work, check out what Dash Enterprise offers. Learn more at: https://plotly.com/dash/authentication/

## Usage

### Basic Authentication

To add basic authentication, add the following to your Dash app:

```python
from dash import Dash
from dash_auth_plus import BasicAuth

app = Dash(__name__)
USER_PWD = {
  "username": "password",
  "user2": "useSomethingMoreSecurePlease",
}
BasicAuth(app, USER_PWD)
```

One can also use an authorization python function instead of a dictionary/list of usernames and passwords:

```python
from dash import Dash
from dash_auth_plus import BasicAuth


def authorization_function(username, password):
  if (username == "hello") and (password == "world"):
    return True
  else:
    return False


app = Dash(__name__)
BasicAuth(app, auth_func=authorization_function)
```

### Public routes

You can whitelist routes from authentication with the `add_public_routes` utility function,
or by passing a `public_routes` argument to the Auth constructor.
The public routes should follow [Flask's route syntax](https://flask.palletsprojects.com/en/2.3.x/quickstart/#routing).

```python
from dash import Dash
from dash_auth_plus import BasicAuth, add_public_routes

app = Dash(__name__)
USER_PWD = {
  "username": "password",
  "user2": "useSomethingMoreSecurePlease",
}
BasicAuth(app, USER_PWD, public_routes=["/"])

add_public_routes(app, public_routes=["/user/<user_id>/public"])
```

NOTE: If you are using server-side callbacks on your public routes, you should also use dash_auth's new `public_callback` rather than the default Dash callback.
Below is an example of a public route and callbacks on a multi-page Dash app using Dash's pages API:

*app.py*

```python
from dash import Dash, html, dcc, page_container
from dash_auth_plus import BasicAuth

app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)
USER_PWD = {
  "username": "password",
  "user2": "useSomethingMoreSecurePlease",
}
BasicAuth(app, USER_PWD, public_routes=["/", "/user/<user_id>/public"])

app.layout = html.Div(
  [
    html.Div(
      [
        dcc.Link("Home", href="/"),
        dcc.Link("John Doe", href="/user/john_doe/public"),
      ],
      style={"display": "flex", "gap": "1rem", "background": "lightgray", "padding": "0.5rem 1rem"},
    ),
    page_container,
  ],
  style={"display": "flex", "flexDirection": "column"},
)

if __name__ == "__main__":
  app.run(debug=True)
```

---
*pages/home.py*

```python
from dash import Input, Output, html, register_page
from dash_auth_plus import public_callback

register_page(__name__, "/")

layout = [
  html.H1("Home Page"),
  html.Button("Click me", id="home-button"),
  html.Div(id="home-contents"),
]


# Note the use of public callback here rather than the default Dash callback
@public_callback(
  Output("home-contents", "children"),
  Input("home-button", "n_clicks"),
)
def home(n_clicks):
  if not n_clicks:
    return "You haven't clicked the button."
  return "You clicked the button {} times".format(n_clicks)
```

---
*pages/public_user.py*
```python
from dash import html, dcc, register_page

register_page(__name__, path_template="/user/<user_id>/public")

def layout(user_id: str):
    return [
        html.H1(f"User {user_id} (public)"),
        dcc.Link("Authenticated user content", href=f"/user/{user_id}/private"),
    ]
```

---
*pages/private_user.py*
```python
from dash import html, register_page

register_page(__name__, path_template="/user/<user_id>/private")

def layout(user_id: str):
    return [
        html.H1(f"User {user_id} (authenticated only)"),
        html.Div("Members-only information"),
    ]
```

### OIDC Authentication

To add authentication with OpenID Connect, you will first need to set up an OpenID Connect provider (IDP).
This typically requires creating
* An application in your IDP
* Defining the redirect URI for your application, for testing locally you can use http://localhost:8050/oidc/callback
* A client ID and secret for the application

Once you have set up your IDP, you can add it to your Dash app as follows:

```python
from dash import Dash
from dash_auth_plus import OIDCAuth

app = Dash(__name__)

auth = OIDCAuth(app, secret_key="aStaticSecretKey!")
auth.register_provider(
  "idp",
  token_endpoint_auth_method="client_secret_post",
  # Replace the below values with your own
  # NOTE: Do not hardcode your client secret!
  client_id="<my-client-id>",
  client_secret="<my-client-secret>",
  server_metadata_url="<my-idp-.well-known-configuration>",
)
```

Once this is done, connecting to your app will automatically redirect to the IDP login page.

#### Multiple OIDC Providers

For multiple OIDC providers, you can use `register_provider` to add new ones after the OIDCAuth has been instantiated.

```python
from dash import Dash, html
from dash_auth_plus import OIDCAuth
from flask import request, redirect, url_for

app = Dash(__name__)

app.layout = html.Div([
  html.Div("Hello world!"),
  html.A("Logout", href="/oidc/logout"),
])

auth = OIDCAuth(
  app,
  secret_key="aStaticSecretKey!", # be sure to replace this key and make it strong as this is how cookies are generated in the application
  # Set the route at which the user will select the IDP they wish to login with
  idp_selection_route="/login",
)
auth.register_provider(
  "IDP 1",
  token_endpoint_auth_method="client_secret_post",
  client_id="<my-client-id>",
  client_secret="<my-client-secret>",
  server_metadata_url="<my-idp-.well-known-configuration>",
)
auth.register_provider(
  "IDP 2",
  token_endpoint_auth_method="client_secret_post",
  client_id="<my-client-id2>",
  client_secret="<my-client-secret2>",
  server_metadata_url="<my-idp2-.well-known-configuration>",
)


@app.server.route("/login", methods=["GET", "POST"])
def login_handler():
  if request.method == "POST":
    idp = request.form.get("idp")
  else:
    idp = request.args.get("idp")

  if idp is not None:
    return redirect(url_for("oidc_login", idp=idp))

  return """<div>
        <form>
            <div>How do you wish to sign in:</div>
            <select name="idp">
                <option value="IDP 1">IDP 1</option>
                <option value="IDP 2">IDP 2</option>
            </select>
            <input type="submit" value="Login">
        </form>
    </div>"""


if __name__ == "__main__":
  app.run(debug=True)
```

#### Mixed Logins

To utilize OIDC and legacy logins, you need to provide a `idp_selection_route`, here is an example flow
using `Flask-Login`. 
The `login_user_callback` is also utilized so that you can configure the session cookies to 
be a similar format, or log the OIDC user into the `Flask-Login`

```python
from dash import Dash, html
from dash_auth import OIDCAuth
from flask import request, redirect, url_for, session
from flask_login import current_user, LoginManager, login_user, UserMixin

app = Dash(__name__)

login_manager = LoginManager()
login_manager.init_app(app.server)
class User(UserMixin):
    pass

@login_manager.user_loader
def user_loader(username):
    user = User()
    user.id = username
    return user

def all_login_method(user_info, idp=None):
    if idp:
        session["user"] = user_info
        session["idp"] = idp
        session['user']['groups'] = ['this', 'is', 'a', 'testing']
        user = User()
        user.id = user_info['email']
        login_user(user)
    else:
        user = User()
        user.id = user_info.get('user')
        login_user(user)
        session['user'] = {}
        session['user']['groups'] = ['nah']
        session['user']['email'] = user_info.get('user')
    return redirect(app.config.get("url_base_pathname") or "/")

def layout():
    if request:
        if current_user:
            try:
                return html.Div([
                    html.Div(f"Hello {current_user.id}!"),
                    html.Button(id='change_users', children='change restrictions'),
                    html.Button(id='test', children='you cant use me'),
                    html.A("Logout", href="/oidc/logout"),
                ])
            except:
                pass
        if 'user' in session:
            return html.Div([
                html.Div(f"""Hello {session['user'].get('email')}!
                        You have access to these groups: {session['user'].get('groups')}"""),
                html.Button(id='change_users', children='change restrictions'),
                html.Button(id='test', children='you cant use me'),
                html.A("Logout", href="/oidc/logout"),
            ])
    return html.Div([
        html.Div("Hello world!"),
        html.Button(id='change_users', children='change restrictions'),
        html.Button(id='test', children='you cant use me'),
        html.A("Logout", href="/oidc/logout"),
    ])

app.layout = layout

auth = OIDCAuth(
    app,
    secret_key="aStaticSecretKey!",
    # Set the route at which the user will select the IDP they wish to login with
    idp_selection_route="/login",
    login_user_callback=all_login_method
)
auth.register_provider(
    "IDP 1",
    token_endpoint_auth_method="client_secret_post",
    client_id="<my-client-id>",
    client_secret="<my-client-secret>",
    server_metadata_url="<my-idp-.well-known-configuration>",
)

@app.server.route("/login", methods=["GET", "POST"])
def login_handler():
    if request.method == 'POST':
        form_data = request.form
    else:
        form_data = request.args

    if form_data.get('user') and form_data.get('password'):
        return all_login_method(form_data)

    if form_data.get('IDP 1'):
        return redirect(url_for("oidc_login", idp='IDP 1'))

    return """<div>
        <form method="POST">
            <div>How do you wish to sign in:</div>
            <button type="submit" name="IDP 1" value="true">Microsoft</button>
            <div><input name="user"/>
            <input name="password"/></div>
            <input type="submit" value="Login">
        </form>
    </div>"""


if __name__ == "__main__":
    app.run_server(debug=True)
```

### User-group-based permissions

`dash_auth` provides a convenient way to secure parts of your app based on user groups.

The following utilities are defined:
* `list_groups`: Returns the groups of the current user, or None if the user is not authenticated.
* `check_groups`: Checks the current user groups against the provided list of groups.
  Available group checks are `one_of`, `all_of` and `none_of`.
  The function returns None if the user is not authenticated.
* `protected`: A function decorator that modifies the output if the user is unauthenticated
  or missing group permission.
* `protected_callback`: A callback that only runs if the user is authenticated
  and with the right group permissions.
* `protect_layouts`: A function that will iterate through all pages and called `protected` on the `layout`, 
  * passes `kwargs` to `protected` if not already defined in the `layout`
  * eg `protect_layouts(missing_permissions_output=html.Div("I'm sorry, Dave, I'm afraid I can't do that"))`

NOTE: user info is stored in the session so make sure you define a secret_key on the Flask server
to use this feature.

If you wish to use this feature with BasicAuth, you will need to define the groups for individual
basicauth users:

```python
from dash_auth_plus import BasicAuth

app = Dash(__name__)
USER_PWD = {
  "username": "password",
  "user2": "useSomethingMoreSecurePlease",
}
BasicAuth(
  app,
  USER_PWD,
  user_groups={"user1": ["group1", "group2"], "user2": ["group2"]},
  secret_key="Test!",
)


# You can also use a function to get user groups
def check_user(username, password):
  if username == "user1" and password == "password":
    return True
  if username == "user2" and password == "useSomethingMoreSecurePlease":
    return True
  return False


def get_user_groups(user):
  if user == "user1":
    return ["group1", "group2"]
  elif user == "user2":
    return ["group2"]
  return []


BasicAuth(
  app,
  auth_func=check_user,
  user_groups=get_user_groups,
  secret_key="Test!",
)
```

### User-based restrictions

`dash_auth` also allows for certain users to be restricted from content and callbacks,
even when they are assigned to a group which grants them access. 
This allows for more granular control. This is done by passing a list of users to `restricted_users`.
To check if a user is in the list, it needs the key from the `session["user"]` to compare, 
this is defaulted as `"email"`.

eg
```python
"""
where session['user'] = {'email': 'me@email.com'}
the below callback will not work
"""

@protected_callback(
    Output('test', 'children'),
    Input('test', 'n_clicks'),
    prevent_initial_call=True,
    restricted_users=['me@email.com']
)
def testing(n):
    return 'I was clicked'
```

### Additional flexibility

`dash_auth` has functions enabled for `groups` and `restricted_users`, this allows for dynamic 
control after application spinup.

When using the functions, the following dictionaries will be passed respectively as `kwargs` to 
the function you provide:
 - `group_lookup`: `{'path': '/test'}` => `pull_groups(path)`
 - `restricted_users_lookup`: `{'path': '/test'}` => `pull_users(path)`

### Restricting layouts

`dash_auth_plus` by default protects routes at the HTTP level: an unauthenticated routing callback for a private page is rejected server-side and the user is redirected to the login page.
Setting `auth_protect_layouts=True` takes a different approach: the routing callback is allowed through for any registered page, but each page's `layout` function is wrapped server-side with `protected()`, so the server returns a placeholder response instead of private content for unauthenticated users. This also provides a single, global place to define access control for all layouts in the application.

```python
from dash import html
from dash_auth_plus import BasicAuth

BasicAuth(
    app,
    USER_PWD,
    public_routes=['/'],
    auth_protect_layouts=True,
    auth_protect_layouts_kwargs=dict(missing_permissions_output=html.Div('You do not have access to this page.')),
    page_container='_pages_content',
)
```

- `auth_protect_layouts=True` — wraps every non-public page's layout with `protected()`, so unauthenticated routing callbacks return a placeholder instead of real content.
- `auth_protect_layouts_kwargs` — keyword arguments forwarded to `protected()`, such as a custom `missing_permissions_output`.
- `page_container` — the `id` of your `page_container` element. When set, only the routing callback targeting that element is intercepted; without it, all callbacks using `pathname` as an input are checked.

See the [Clerk Authentication](#clerk-authentication) section for a detailed explanation and comparison table of default vs layout-protected behaviour.

## Clerk Authentication

[Clerk](https://clerk.com) is a complete authentication and user management solution. `ClerkAuth` integrates Clerk's backend SDK with your Dash app to provide seamless, secure authentication.

### Prerequisites

Before using `ClerkAuth`, you need a Clerk account and application. Set the following environment variables (or pass them directly to `ClerkAuth`):

| Variable | Description |
|---|---|
| `CLERK_SECRET_KEY` | Your Clerk secret key (e.g. `sk_live_...`) |
| `CLERK_PUBLISHABLE_KEY` | Your Clerk publishable key (e.g. `pk_live_...`) |
| `CLERK_DOMAIN` | Your Clerk Frontend API URL (e.g. `https://accounts.your-app.clerk.accounts.dev`) |
| `CLERK_ALLOWED_PARTIES` | *(optional)* Comma-separated list of allowed party URLs |

Install the required backend SDK:

```
pip install clerk-backend-api
```

### Basic ClerkAuth Setup

```python
import os
from dash import Dash, html, dcc, page_container
from dash_auth_plus import ClerkAuth, public_callback
from dash import Input, Output, register_page

app = Dash(__name__, use_pages=True, pages_folder='', suppress_callback_exceptions=True)

# Initialize ClerkAuth — reads CLERK_* env vars automatically
auth = ClerkAuth(
    app,
    secret_key="aStaticSecretKey!",  # protect Flask session cookies
    log_signins=True,
    auth_protect_layouts=True,       # protect page layouts, not just routes
    page_container='_pages_content', # id of your page_container element
    public_routes=['/', '/user/<user_id>/public'],
)

# Main layout with navigation
app.layout = html.Div(
    [
        html.Div(
            [
                dcc.Link("Home", href="/"),
                dcc.Link("John Doe", href="/user/john_doe/public"),
                dcc.Link('Logout', href='/logout', refresh=True),
            ],
            style={"display": "flex", "gap": "1rem", "background": "lightgray", "padding": "0.5rem 1rem"},
        ),
        page_container,
    ],
    style={"display": "flex", "flexDirection": "column"},
)

# Home page (public)
home_layout = [
    html.H1("Home Page"),
    html.Button("Click me", id="home-button"),
    html.Div(id="home-contents"),
]
register_page('home', "/", layout=home_layout)

@public_callback(
    Output("home-contents", "children"),
    Input("home-button", "n_clicks"),
)
def home(n_clicks):
    if not n_clicks:
        return "You haven't clicked the button."
    return f"You clicked the button {n_clicks} times"

# Public user page
def user_layout(user_id: str, **kwargs):
    return [
        html.H1(f"User {user_id} (public)"),
        dcc.Link("Authenticated user content", href=f"/user/{user_id}/private"),
    ]
register_page('user', path_template="/user/{user_id}/public", layout=user_layout)

# Private user page (protected)
def user_private(user_id: str, **kwargs):
    return [
        html.H1(f"User {user_id} (authenticated only)"),
        html.Div("Members-only information"),
    ]
register_page('private', path_template="/user/{user_id}/private", layout=user_private)

if __name__ == "__main__":
    app.run(debug=True)
```

### `auth_protect_layouts` — Layout-Level Protection

By default, `ClerkAuth` (and other auth classes) protect access at the HTTP request level: an unauthenticated routing callback for a private page is rejected server-side and the user is redirected to the login page.

Setting `auth_protect_layouts=True` takes a different approach: the routing callback is **allowed through** for any registered page, but each page's `layout` function is wrapped server-side with `protected()`. The server's response already contains only the placeholder content for unauthenticated users — no private data is ever sent to the client. This also provides a single, global place to define access control for the entire application.

```python
auth = ClerkAuth(
    app,
    secret_key="aStaticSecretKey!",
    auth_protect_layouts=True,
    # Customise what unauthenticated users see in place of private page content
    auth_protect_layouts_kwargs=dict(
        missing_permissions_output=html.Div("Please log in to view this page.")
    ),
    page_container='_pages_content',  # id of the page_container element
    public_routes=['/'],
)
```

When `page_container` is set to the `id` of your `page_container` element, only the routing callback that targets that element is intercepted. Without it, *all* callbacks that use `pathname` as an input are checked—which may be overly broad.

**Summary of behaviour:**

| Setting | Unauthenticated routing callback | Unauthenticated direct URL |
|---|---|---|
| default (`auth_protect_layouts=False`) | ❌ Server rejects → redirect to login | ❌ Server rejects → redirect to login |
| `auth_protect_layouts=True` | ✅ Server allows → layout returns placeholder (server-side) | ✅ Server allows → layout returns placeholder (server-side) |

### Custom Login Page (Embedded Sign-In)

By default, `ClerkAuth` redirects unauthenticated users to Clerk's hosted sign-in page on your Clerk domain. While simple, this means users leave your application's visual environment to log in.

A better user experience keeps the user on your domain throughout the login flow. You can achieve this by serving a Dash page (or a plain Flask route) that embeds Clerk's `<clerk-sign-in>` web component. When the user authenticates via the embedded component, the Clerk JS listener that `ClerkAuth` injects automatically calls your app's `/auth_callback` endpoint and redirects the user back to the page they were trying to reach.

#### Step 1 — Create a custom login page

Add a page to your Dash app (using Dash Pages) that renders the Clerk sign-in component:

*pages/login.py*
```python
from dash import html, register_page, dcc

register_page(__name__, path="/login", title="Sign In")

layout = html.Div(
    [
        html.Div(
            [
                html.H2("Sign in", style={"marginBottom": "1rem"}),
                # The <clerk-sign-in> web component is injected by Clerk's JS SDK.
                # It renders Clerk's sign-in UI inline — no redirect to Clerk's hosted page.
                html.Div(id="clerk-sign-in-container"),
                dcc.Interval(id="_clerk_mount_interval", interval=300, max_intervals=20),
            ],
            style={
                "display": "flex",
                "flexDirection": "column",
                "alignItems": "center",
                "justifyContent": "center",
                "minHeight": "60vh",
            },
        )
    ]
)
```

*app.py (clientside callback to mount the Clerk sign-in UI)*
```python
from dash import Dash, html, dcc, page_container, clientside_callback, Input, Output, State
from dash_auth_plus import ClerkAuth, public_callback

app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)

auth = ClerkAuth(
    app,
    secret_key="aStaticSecretKey!",
    auth_protect_layouts=True,
    page_container='_pages_content',
    public_routes=['/login', '/'],  # /login must be public
)

app.layout = html.Div(
    [
        html.Div(
            [
                dcc.Link("Home", href="/"),
                dcc.Link("Sign in", href="/login"),
                dcc.Link("Logout", href="/logout", refresh=True),
            ],
            style={"display": "flex", "gap": "1rem", "padding": "0.5rem 1rem", "background": "lightgray"},
        ),
        page_container,
    ],
    style={"display": "flex", "flexDirection": "column"},
)

# Mount the Clerk <clerk-sign-in> web component once Clerk JS is ready
clientside_callback(
    """
    function(n) {
        if (typeof window.Clerk === 'undefined') return window.dash_clientside.no_update;
        var container = document.getElementById('clerk-sign-in-container');
        if (!container) return window.dash_clientside.no_update;
        // Only mount once
        if (container.querySelector('.cl-rootBox')) return window.dash_clientside.no_update;
        window.Clerk.mountSignIn(container);
        return window.dash_clientside.no_update;
    }
    """,
    Output("clerk-sign-in-container", "children"),
    Input("_clerk_mount_interval", "n_intervals"),
    prevent_initial_call=True,
)

if __name__ == "__main__":
    app.run(debug=True)
```

> **How it works:** `ClerkAuth` injects Clerk's JavaScript SDK into every page. When the user fills in the embedded sign-in form and authenticates, Clerk fires a session event. The listener injected by `ClerkAuth` detects the new session and automatically calls `/auth_callback`, which creates the server-side session and redirects the user to their original destination.

> **Important:** Add `/login` (or whichever path you choose) to `public_routes` so unauthenticated users can reach the sign-in page.

#### Step 2 (optional) — Override `login_request` to redirect to your custom page

By default, unauthenticated users are redirected to Clerk's hosted sign-in page. To send them to your embedded login page instead, subclass `ClerkAuth` and override `login_request`:

```python
from flask import redirect, session
from dash_auth_plus import ClerkAuth

class EmbeddedClerkAuth(ClerkAuth):
    """ClerkAuth that redirects to a local login page instead of Clerk's hosted page."""

    def login_request(self):
        # Save where the user was trying to go
        self._redirect_test()
        # Redirect to your Dash login page
        return redirect("/login")


auth = EmbeddedClerkAuth(
    app,
    secret_key="aStaticSecretKey!",
    auth_protect_layouts=True,
    page_container='_pages_content',
    public_routes=['/login', '/'],
)
```

With this setup the full login flow stays within your application:

1. User visits a protected page → redirected to `/login` (your Dash page)
2. User authenticates via the embedded `<clerk-sign-in>` component
3. Clerk JS listener calls `/auth_callback`, creating the server-side session
4. User is redirected back to the page they originally requested

### User Groups with ClerkAuth

User groups work the same way as with other auth providers. Pass a dict or callable as `user_groups`:

```python
# Static group mapping by email
auth = ClerkAuth(
    app,
    secret_key="aStaticSecretKey!",
    user_groups={
        "alice@example.com": ["admin", "editor"],
        "bob@example.com": ["viewer"],
    },
)

# Dynamic group lookup function
def get_groups(email: str):
    # look up groups from your database
    return fetch_groups_from_db(email)

auth = ClerkAuth(
    app,
    secret_key="aStaticSecretKey!",
    user_groups=get_groups,
)
```

The resolved groups are stored in `session["user"]["groups"]` and can be used with `check_groups`, `protected`, and `protected_callback` just like any other auth provider.

### Customising the Post-Login Callback

Use `login_user_callback` to run custom logic (e.g. fetching additional user data, logging) after a successful Clerk authentication:

```python
from flask import session, redirect

def my_post_login(user, idp):
    """
    user : Clerk user object
    idp  : always 'clerk' for ClerkAuth
    """
    session["user"] = {
        "email": user.email_addresses[0].email_address,
        "name": f"{user.first_name} {user.last_name}",
        "role": fetch_role_from_db(user.id),
    }
    return redirect("/dashboard")

auth = ClerkAuth(
    app,
    secret_key="aStaticSecretKey!",
    login_user_callback=my_post_login,
)
```

### Customising the Logout Flow

Use `before_logout` to run cleanup logic before the session is cleared (e.g. audit logging):

```python
from flask import session
import logging

def on_logout():
    email = session.get("user", {}).get("email")
    logging.info("User %s is logging out.", email)

auth = ClerkAuth(
    app,
    secret_key="aStaticSecretKey!",
    before_logout=on_logout,
    # Optionally replace the default "Logged out" page with custom HTML:
    logout_page="<h1>You've been signed out. <a href='/'>Go home</a></h1>",
)
```

### Important Notes

- If you implement your own logout mechanism (outside of the `/logout` route), set the `clerk_logged_in` localStorage flag to `false` so the Clerk JS listener knows the session has ended:

```html
<!-- Client-Side Logout State Reset -->
<script>
  localStorage.setItem('clerk_logged_in', 'false');
</script>
```

- The full Clerk JS API (`window.Clerk`) is available in the browser on every page after `ClerkAuth` is initialised. You can use any method from the [Clerk JS documentation](https://clerk.com/docs/references/javascript/overview), such as `window.Clerk.user` to access the current user's profile client-side.