"""`MCPServer(...).http(...)` / `.stdio(...)` build a transport without the SDK's params-dict."""

from typing import Any, cast

from agents.mcp import MCPServerStdio, MCPServerStreamableHttp
from agents.mcp.server import MCPServerStdioParams, MCPServerStreamableHttpParams


class MCPServer:
    """Shared server config, finalized by picking a transport.

    Keyword arguments given here (`name`, `require_approval`, `cache_tools_list`, ...) are
    common to every transport and forwarded as-is; `http`/`stdio` take only the params specific
    to that transport (a URL vs. a command) and build the SDK's params dict for you.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Stash config shared by every transport, applied when `http`/`stdio` is called."""
        self._kwargs = kwargs

    def http(self, url: str, **params: Any) -> MCPServerStreamableHttp:
        """Connect over streamable HTTP.

        Extra `params` (`headers`, `timeout`, ...) go to the transport.
        """
        server_params = cast(MCPServerStreamableHttpParams, {"url": url, **params})
        return MCPServerStreamableHttp(server_params, **self._kwargs)

    def stdio(self, command: str, args: list[str] | None = None, **params: Any) -> MCPServerStdio:
        """Spawn a local process over stdio.

        Extra `params` (`env`, `cwd`, ...) go to the transport.
        """
        server_params = cast(
            MCPServerStdioParams, {"command": command, "args": args or [], **params}
        )
        return MCPServerStdio(server_params, **self._kwargs)


__all__ = ["MCPServer", "MCPServerStdio", "MCPServerStreamableHttp"]
