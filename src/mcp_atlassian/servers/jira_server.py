"""Jira-only MCP server entry point for Container Apps deployment."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.servers.context import JiraAppContext
from mcp_atlassian.utils.io import is_read_only_mode
from mcp_atlassian.utils.tools import get_enabled_tools

logger = logging.getLogger("mcp-atlassian.jira-server")

@asynccontextmanager
async def jira_standalone_lifespan(app) -> AsyncIterator[dict]:
    """Jira 전용 lifespan 컨텍스트"""
    logger.info("Jira-only MCP server lifespan starting...")
    
    read_only = is_read_only_mode()
    enabled_tools = get_enabled_tools()
    
    # 환경 변수에서 기본 Jira 설정 시도 (선택적)
    jira_config = None
    jira_fetcher = None
    
    try:
        # 기본 설정이 있다면 로드 (없어도 괜찮음)
        jira_config = JiraConfig.from_env()
        if jira_config and jira_config.is_auth_configured():
            try:
                jira_fetcher = JiraFetcher(jira_config)
                logger.info("Global Jira client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize global Jira client: {e}")
                logger.info("Will rely on user-specific authentication only")
        else:
            logger.info("No global Jira configuration found. User-specific auth required.")
    except Exception as e:
        logger.info(f"No global Jira config available: {e}. Using user-specific auth only.")
    
    # Jira 전용 컨텍스트 생성
    jira_context = JiraAppContext(
        jira_config=jira_config,
        jira_fetcher=jira_fetcher,
        read_only=read_only,
        enabled_tools=enabled_tools,
    )
    
    context = {
        "app_lifespan_context": jira_context,
        "jira_fetcher": jira_fetcher,
        "jira_config": jira_config,
        "read_only": read_only,
        "enabled_tools": enabled_tools,
    }
    
    logger.info(f"Jira context initialized - Global config: {'Yes' if jira_config else 'No'}, Read-only: {read_only}")
    
    yield context
    
    logger.info("Jira-only MCP server lifespan ending...")


def main() -> None:
    """Jira-only MCP server entry point for Container Apps deployment."""
    from .common import setup_server_logging, get_server_config, add_user_token_middleware, run_mcp_server
    
    # 공통 로깅 설정
    current_logging_level = setup_server_logging()
    logger.info("Starting Jira-only MCP server for Container Apps deployment")

    # 공통 서버 설정 읽기
    server_config = get_server_config()
    logger.info(f"Server config: {server_config['transport']} on {server_config['host']}:{server_config['port']}{server_config['path']}")
    
    # 인증 방식 로깅
    jira_url = os.getenv("JIRA_URL")
    if jira_url:
        logger.info(f"Global Jira URL configured: {jira_url}")
    else:
        logger.info("No global Jira URL. Will use X-Jira-URL header for user requests.")

    # jira_mcp import
    from .jira import jira_mcp

    # Jira 전용 서버를 위해 lifespan 설정
    jira_mcp.lifespan = jira_standalone_lifespan

    # 공통 middleware 추가 함수 사용
    add_user_token_middleware(jira_mcp, "Jira-only")

    # 공통 서버 실행 함수 사용
    run_mcp_server(jira_mcp, server_config, current_logging_level, "Jira-only")

if __name__ == "__main__":
    main() 