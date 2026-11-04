# Tool Use and MCP: learn by speaking the protocol

Build the function-calling loop, then talk to an MCP server **by hand** (JSON-RPC over stdio), then use the official SDK, then see why tool results are untrusted input.

## Contents
| File | What it is |
|---|---|
| `tooluse_mcp_learning.ipynb` | The lecture notebook (concepts, labs, checkpoints, exercises, glossary, reading list) |
| `tooluse.py` | Argument validator, tool registry, tool loop with parallel calls, a from-scratch MCP client |
| `mini_mcp_server.py` | An MCP server in the standard library only (tools and resources), including a poisoned note for the security demo |
| `sdk_server.py` | The same idea with the official MCP Python SDK (`MCPServer`, called `FastMCP` in SDK v1) |
| `requirements.txt` | numpy, pandas, matplotlib, ipykernel, mcp |

Runs **offline**: the "model" is scripted.

## Slides
A companion slide deck lives on the author's Claude account (shared link): https://claude.ai/artifact/1Y2oPW5Z6MrLcATas7o41f

## Setup
```bash
uv venv .venv
uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/python -m ipykernel install --user --name tool-mcp --display-name "Python (tool-mcp)"
```
Open the notebook and select the **Python (tool-mcp)** kernel.

## Note on SDK versions
This was written against `mcp` 2.x, where `FastMCP` became `MCPServer` (`from mcp.server.mcpserver import MCPServer`). With `mcp<2`, use `from mcp.server.fastmcp import FastMCP`.

## Topics
The tool-call loop, validation and recoverable errors, tool design, MCP architecture (host, client, server; tools, resources, prompts), JSON-RPC lifecycle, official SDK, prompt injection and defenses.

## Series
Part of a small AI engineering learning series: Hybrid RAG, Harness Engineering, LLM Evals, Tool Use and MCP.
