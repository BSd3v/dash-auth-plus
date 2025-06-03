# Contributing

## Publishing

This package is available on PyPI. We can create a new version as often as whenever a PR is merged.

1. **Install Dependencies**
- To aid with processes for testing, we have added package.json to install npm dependencies and scripts.
```
python -m venv .venv
source .venv/bin/activate
pip install -r dev-requirements.txt
npm i
```

2. **Changelogs and Version**
- Check the recent commits and PRs and add anything notable to the `CHANGELOG.md` file
- Bump the version number in `dash_auth_plus/version.py`. Follow [Semantic Versioning 2.0.0](https://semver.org/)
- Create a PR
- Once reviewed, merge into main.

3. **Create a Python Build**
```
$ npm run dist
```
- This will create a source distribution and a wheel in the `dist/` folder.

4. **Test it**
- Test your tarball by copying it into a new environment and installing it locally:
```
$ pip install dash_auth_plus-0.0.1.tar.gz
```

5. **Publish a New Release**
- A Github release with package build files is automatically generated when a new tag starting with `v*` is pushed.
- Once a Github release is published, the build is re-generated and pushed to PyPi.
- Create a git tag:
    ```
    git tag -a 'v0.1.0' -m 'v0.1.0'
    git push --tags
    ```
- Wait for the "Generate release" CI job to complete, then check the releases tab to move the release from "Draft" to "Published". Make sure to copy in the Changelog.
- When the release is published to Github, it's automatically pushed to PyPi as well.
