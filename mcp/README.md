# Waves MCP server

This minimal stdio MCP server wraps the deployed Waves API. It contains no
local risk logic and exposes only privacy-safe, structured inputs: no names,
symptoms, or complete raw health profiles.

## Install and run

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r mcp/requirements.txt
.venv/bin/python mcp/waves_mcp.py
```

The last command starts a stdio server, so it waits silently for an MCP client.
It does not need `MISTRAL_API_KEY`; both tools call the already-deployed Waves
API at `https://waves-nine-gold.vercel.app`.

## Mistral Vibe CLI

Paste this block into the `mcp servers` section of `.vibe/config.toml` for this
project, or `~/.vibe/config.toml` for user-wide registration. Replace the paths
if the repository lives elsewhere.

```toml
[[mcp_servers]]
name = "waves"
transport = "stdio"
command = "/Users/volodymyrborysenko/Code/waves/.venv/bin/python"
args = ["/Users/volodymyrborysenko/Code/waves/mcp/waves_mcp.py"]
```

The tools are:

- `get_heat_risk`: sends a city or coordinate pair plus the existing
  vulnerability, exposure, and protection models to `/api/profile-risk`.
- `get_action_plan`: sends only the existing calculated risk subset and `en` or
  `uk` to `/api/mistral-action-plan`.

## Tests

```bash
.venv/bin/python -m pip install -r mcp/requirements-dev.txt
.venv/bin/python -m pytest mcp/tests -q
```
