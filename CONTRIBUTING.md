# Contribution guidelines

Contributing to this project should be as easy and transparent as possible,
whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features

## Github is used for everything

Github is used to host code, to track issues and feature requests, as well as
accept pull requests.

Pull requests are the best way to propose changes to the codebase.

1. Fork the repo and create your branch from `main`.
2. If you've changed something, update the documentation.
3. Make sure your code follows the recommendations here.
4. Test you contribution.
5. Issue that pull request!

## Repository tooling and editor expectations

This repository now standardizes contributor workflow around Ruff and the
checked-in VS Code/devcontainer settings. Please use the same setup locally so
formatting, import cleanup, and whitespace handling behave the same for
everyone.

- Use `scripts/ruff` to apply the repository formatter and ruff bast practice fixes before committing.
- Use `scripts/lint` to run the repo checks locally before opening a pull
  request.
- Use `scripts/setup` after cloning or after updating developer dependencies.
- SSH agent forwarding is optional. Uncomment the block in
  `.devcontainer.json` locally when needed and keep that change uncommitted.
- The workspace expects Python to resolve to `/usr/local/bin/python`.
- VS Code is configured for format-on-save with Ruff for Python files.
- Trailing whitespace and final newlines are cleaned automatically by the
  editor and pre-commit hooks.
- YAML files are associated with the Home Assistant language mode in the
  workspace so HA-specific tags and syntax are handled consistently.
- Pre-commit is enabled for file hygiene and Ruff formatting/linting. If your
  hooks modify files, commit the resulting changes instead of bypassing them.

## Any contributions you make will be under the GPL v3 license

In short, when you submit code changes, your submissions are understood to be
under the same [GPL v3 license](license) that covers the project. Feel free to
contact the maintainers if that's a concern.

## Report bugs using Github's [issues](../../issues)

GitHub issues are used to track public bugs. Report a bug by [opening a new
issue](../../issues/new/choose); it's that easy!

## Write bug reports with detail, background, and sample code

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can.
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you
  tried that didn't work)

People *love* thorough bug reports. I'm not even kidding.

## Use a Consistent Coding Style

Use Ruff for formatting and linting. The repository config is in
[pyproject.toml](pyproject.toml), and the expected local commands are:

- `scripts/ruff` for formatting changes
- `scripts/lint` for validation before review

Please avoid rewrapping or whitespace-only changes that are not required by
Ruff or by the actual code change. That keeps diffs focused and avoids churn
for other contributors.

If you need editor guidance, use the checked-in VS Code settings in
[.vscode/settings.json](.vscode/settings.json) and the container setup in
[.devcontainer.json](.devcontainer.json).

## Test your code modification

This custom component is based on [integration_blueprint
template](https://github.com/ludeeus/integration_blueprint).

It comes with development environment in a container, easy to launch if you use
Visual Studio Code. With this container you will have a stand alone Home
Assistant instance running and already configured with the included
[`configuration.yaml`](./config/configuration.yaml) file.

Be aware, that the devcontainer will publish to port 8124 to avoid clashes with
other HA environments.

When you touch Python code, please make sure the following still pass:

- Ruff formatting and best practice fixes: `scripts/ruff`
- Ruff linting: `scripts/lint`
- Home Assistant startup in the devcontainer or via `scripts/develop`

If you change editor or workspace behavior, update the matching settings in
[.vscode/settings.json](.vscode/settings.json) and [.devcontainer.json](.devcontainer.json)
so all contributors get the same defaults.

## License

By contributing, you agree that your contributions will be licensed under its
[GPL v3 license](https://github.com/torbennehmer/hacs-e3dc/blob/main/LICENSE).
