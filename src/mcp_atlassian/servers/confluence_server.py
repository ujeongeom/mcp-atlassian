"""Confluence-only MCP server entry point for Container Apps deployment."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.servers.context import ConfluenceAppContext
from mcp_atlassian.utils.io import is_read_only_mode
from mcp_atlassian.utils.tools import get_enabled_tools

from .confluence import confluence_mcp

from mcp_atlassian.utils.logging import get_logger

logger = get_logger("confluence")

@asynccontextmanager
async def confluence_standalone_lifespan(app) -> AsyncIterator[dict]:
    """Confluence 전용 lifespan 컨텍스트"""
    logger.info("Confluence-only MCP server lifespan starting...")
    
    read_only = is_read_only_mode()
    enabled_tools = get_enabled_tools()
    
    # 환경 변수에서 기본 Confluence 설정 시도 (선택적)
    confluence_config = None
    confluence_fetcher = None
    
    try:
        # 기본 설정이 있다면 로드 (없어도 괜찮음)
        confluence_config = ConfluenceConfig.from_env()
        if confluence_config and confluence_config.is_auth_configured():
            try:
                confluence_fetcher = ConfluenceFetcher(confluence_config)
                logger.info("Global Confluence client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize global Confluence client: {e}")
                logger.info("Will rely on user-specific authentication only")
        else:
            logger.info("No global Confluence configuration found. User-specific auth required.")
    except Exception as e:
        logger.info(f"No global Confluence config available: {e}. Using user-specific auth only.")
    
    # Confluence 전용 컨텍스트 생성
    confluence_context = ConfluenceAppContext(
        confluence_config=confluence_config,
        confluence_fetcher=confluence_fetcher,
        read_only=read_only,
        enabled_tools=enabled_tools,
    )
    
    context = {
        "app_lifespan_context": confluence_context,
        "confluence_fetcher": confluence_fetcher,
        "confluence_config": confluence_config,
        "read_only": read_only,
        "enabled_tools": enabled_tools,
    }
    
    logger.info(f"Confluence context initialized - Global config: {'Yes' if confluence_config else 'No'}, Read-only: {read_only}")
    
    yield context
    
    logger.info("Confluence-only MCP server lifespan ending...")


def main() -> None:
    """Confluence-only MCP server entry point for Container Apps deployment."""
    from .common import setup_server_logging, get_server_config, add_user_token_middleware, run_mcp_server
    
    # 공통 로깅 설정
    current_logging_level = setup_server_logging()
    logger.info("Starting Confluence-only MCP server for Container Apps deployment")

    # 공통 서버 설정 읽기
    server_config = get_server_config()
    logger.info(f"Confluence-only server configuration: transport={server_config['transport']}, host:port-path={server_config['host']}:{server_config['port']}{server_config['path']}")

    # Confluence URL은 이제 헤더에서 동적으로 받음 (환경변수 체크 제거)
    logger.info("Confluence URL will be read from X-Confluence-URL header dynamically")

    # Confluence 전용 서버를 위해 lifespan 설정
    confluence_mcp.lifespan = confluence_standalone_lifespan

    # 공통 middleware 추가 함수 사용
    add_user_token_middleware(confluence_mcp, "Confluence-only")

    # 공통 서버 실행 함수 사용
    run_mcp_server(confluence_mcp, server_config, current_logging_level, "Confluence-only")


if __name__ == "__main__":
    main() 