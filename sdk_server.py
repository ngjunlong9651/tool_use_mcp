"""The same idea as mini_mcp_server.py, written with the official MCP Python SDK (MCPServer).

Note: in MCP Python SDK v1 this class was called FastMCP (from mcp.server.fastmcp import FastMCP). In v2 it is
MCPServer. If you pin mcp<2 and see old tutorials, that is the only difference you need for this file.

Compare the two files: the SDK derives each tool's name, description and JSON Schema from your Python function
signature and docstring, and handles initialize, capability negotiation, validation and transports for you.

Run it directly (stdio):   python sdk_server.py
"""
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("notes-sdk")

NOTES = {"1": "Standup: ship the retriever on Friday.", "2": "Q3 planning: budget review on the 14th."}


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers and return the sum."""      # the docstring becomes the tool description the model sees
    return a + b


@mcp.tool()
def search_notes(query: str) -> str:
    """Search the user's notes by keyword."""
    hits = [f"{k}: {v}" for k, v in NOTES.items() if query.lower() in v.lower()]
    return "\n".join(hits) or "no matching notes"


@mcp.resource("notes://{note_id}")
def read_note(note_id: str) -> str:
    """Read one note by id."""
    return NOTES[note_id]


@mcp.prompt()
def summarize_notes() -> str:
    """A reusable prompt template a user can pick from a menu."""
    return "Summarize all of my notes in three bullet points."


if __name__ == "__main__":
    mcp.run()          # defaults to the stdio transport
