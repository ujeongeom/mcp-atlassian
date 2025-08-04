"""Context classes for MCP server lifespan management."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_atlassian.confluence import ConfluenceFetcher
    from mcp_atlassian.confluence.config import ConfluenceConfig
    from mcp_atlassian.jira import JiraFetcher
    from mcp_atlassian.jira.config import JiraConfig


class BaseAppContext:
    """Base context class for MCP server applications."""

    def __init__(
        self,
        read_only: bool = False,
        enabled_tools: list[str] | None = None,
    ):
        self.read_only = read_only
        self.enabled_tools = enabled_tools or []


class MainAppContext(BaseAppContext):
    """Context for main MCP server with both Jira and Confluence support."""

    def __init__(
        self,
        full_jira_config: JiraConfig | None = None,
        full_confluence_config: ConfluenceConfig | None = None,
        read_only: bool = False,
        enabled_tools: list[str] | None = None,
    ):
        super().__init__(read_only=read_only, enabled_tools=enabled_tools)
        self.full_jira_config = full_jira_config
        self.full_confluence_config = full_confluence_config


class JiraAppContext(BaseAppContext):
    """Context for Jira-only MCP server."""

    def __init__(
        self,
        jira_config: JiraConfig | None = None,
        jira_fetcher: JiraFetcher | None = None,
        read_only: bool = False,
        enabled_tools: list[str] | None = None,
    ):
        super().__init__(read_only=read_only, enabled_tools=enabled_tools)
        self.jira_config = jira_config
        self.full_jira_config = jira_config  # dependencies.py에서 기대하는 속성명
        self.jira_fetcher = jira_fetcher


class ConfluenceAppContext(BaseAppContext):
    """Context for Confluence-only MCP server."""

    def __init__(
        self,
        confluence_config: ConfluenceConfig | None = None,
        confluence_fetcher: ConfluenceFetcher | None = None,
        read_only: bool = False,
        enabled_tools: list[str] | None = None,
    ):
        super().__init__(read_only=read_only, enabled_tools=enabled_tools)
        self.confluence_config = confluence_config
        self.full_confluence_config = confluence_config  # dependencies.py에서 기대하는 속성명
        self.confluence_fetcher = confluence_fetcher
