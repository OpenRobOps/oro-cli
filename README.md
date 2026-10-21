# ORO CLI

Command line tool for [OpenRobOps (ORO)](https://github.com/openrobops): manage
configuration as code and query your fleet from the terminal, against one or more ORO
instances.

```bash
oro use myinstance
oro apply -f config/
oro get config --kind ActionDefinition
oro get robots
```

## Install

Requires Python 3.12 or newer.

```bash
pip install oro-cli
```

## Contexts

A *context* is one ORO instance plus the API key used to talk to it. Create an API key in
your ORO instance (user menu > API keys), then register the instance:

```bash
oro context add myinstance --url https://oro.example.com/api --api-key oro_xxx
```

The first context you add becomes the current one. Add more and switch between them:

```bash
oro context add local --url http://localhost:3000/api --api-key oro_yyy --verbose
oro use local                 # same as: oro context use local
oro context list              # all contexts, current marked with *
oro context current           # name of the current context
oro context remove local
oro whoami                    # current context, URL, and whether the key authenticates
```

Contexts are stored in `~/.config/oro/config.yaml` (or `$XDG_CONFIG_HOME/oro/config.yaml`),
readable only by you. API keys are stored in plain text. The file looks like this:

```yaml
current: myinstance
contexts:
  myinstance:
    url: https://oro.example.com/api
    api_key: oro_xxx
    verbose: false
  local:
    url: http://localhost:3000/api
    api_key: oro_yyy
    verbose: true
```

You can edit it by hand, but prefer the `oro context` commands: a file that does not
parse makes every command fail until it is fixed. `verbose: true` logs every HTTP request
and response for that context, the same as passing `--verbose`.

### Environment variables

For CI and scripts, environment variables override the file:

| Variable | Effect |
|---|---|
| `ORO_URL` | API base URL, e.g. `https://oro.example.com/api` |
| `ORO_API_KEY` | API key |
| `ORO_CONTEXT` | Use this context instead of the current one |
| `ORO_VERBOSE` | `1`, `true` or `yes` turns on HTTP logging |

When both `ORO_URL` and `ORO_API_KEY` are set, no config file is needed. Setting only one
of them overrides that field of the current context. Empty values count as unset.

## Commands

### Configuration as code

```bash
oro apply -f config.yaml           # show a diff per object, ask, then apply
oro apply -f config.yaml -y        # apply without asking
oro apply -f config.yaml --compare # only show differences
oro apply -f configs/              # every .yaml, .yml and .json file under the directory
oro apply -f configs/ --compare --all              # also list server objects missing locally
oro apply -f configs/ --compare --all --exclude Test

oro get config --kind ActionDefinition             # full objects as YAML
oro get config --kind ActionDefinition wave        # one object
oro get config --kind ActionDefinition --json      # as JSON
oro get config --kind ActionDefinition --summary   # short table
oro get config --kind ActionDefinition --all       # include normally hidden elements
oro list kinds                                     # available kinds

oro delete config --kind ActionDefinition wave
oro delete -f config.yaml                          # delete every object in the file
```

Config files hold one or more objects as YAML documents (or a JSON list):

```yaml
kind: ActionDefinition
metadata:
  id: wave
spec:
  label: Wave
  type: PublishToTopic
```

`apiVersion` is filled in when missing. A `metadata.scope` field is ignored with a
warning, so files written for other tools keep working.

### Robots

```bash
oro get robots        # name, id, agent version
oro describe robots   # also online state and last seen
```

### Global options

```bash
oro --verbose <command>   # log HTTP traffic to stderr
oro --version
oro --help
```

## Development

To try the tool from a checkout without publishing it, install it in editable mode. The
`oro` command then runs the code in your working tree, so edits take effect immediately:

```bash
git clone https://github.com/openrobops/oro-cli.git
cd oro-cli
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

oro --version
oro context add local --url http://localhost:3000/api --api-key oro_xxx
oro whoami
```

Or, without a virtualenv, run it straight from the repo with [uv](https://docs.astral.sh/uv/)
or [pipx](https://pipx.pypa.io/): `uv run oro --help` or `pipx install -e .`.

Tests and lint:

```bash
pytest
ruff check . && ruff format --check .
```

Release: bump `version` in `pyproject.toml`, commit, then publish a GitHub release with a
`vX.Y.Z` tag. The `publish` workflow builds the package and uploads it to PyPI through
trusted publishing (no token needed). To publish by hand instead:

```bash
python -m build
twine upload dist/*
```

## License

Apache 2.0. See [LICENSE](LICENSE).
