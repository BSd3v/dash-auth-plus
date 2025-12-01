import json
import os


def get_package_info():
    basepath = os.path.dirname(__file__)
    filepath = os.path.abspath(os.path.join(basepath, "package-info.json"))
    with open(filepath) as f:
        return json.load(f)


package = get_package_info()
__version__ = package["version"]
__plotly_dash_auth_version__ = "2.3.0"
