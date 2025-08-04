"""Confluence-only MCP server entry point for Container Apps deployment."""

import asyncio
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp_atlassian.utils.logging import setup_logging
from mcp_atlassian.utils.env import is_env_truthy
from mcp_atlassian.utils.tools import get_enabled_tools
from mcp_atlassian.utils.io import is_read_only_mode
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.servers.context import ConfluenceAppContext

# Confluence MCP 인스턴스 import
from .confluence import confluence_mcp

logger = logging.getLogger("mcp-atlassian.confluence-server")

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
    # 로깅 설정 - INFO로 기본 설정
    current_logging_level = logging.INFO
    if is_env_truthy("MCP_VERY_VERBOSE", "false"):
        current_logging_level = logging.DEBUG
    elif is_env_truthy("MCP_VERBOSE", "false"):
        current_logging_level = logging.INFO

    # STDOUT으로 로깅 설정 (Container Apps 환경에 최적화)
    logging_stream = sys.stdout if is_env_truthy("MCP_LOGGING_STDOUT") else sys.stderr
    setup_logging(current_logging_level, logging_stream)
    
    logger.info("Starting Confluence-only MCP server for Container Apps deployment")

    # 환경 변수에서 설정 읽기
    transport = os.getenv("TRANSPORT", "streamable-http").lower()
    port = int(os.getenv("PORT", "9000"))
    host = os.getenv("HOST", "0.0.0.0")  # noqa: S104
    path = os.getenv("STREAMABLE_HTTP_PATH", "/mcp")

    logger.info(f"Confluence-only server configuration: transport={transport}, host:port-path={host}:{port}{path}")

    # Confluence URL은 이제 헤더에서 동적으로 받음 (환경변수 체크 제거)
    logger.info("Confluence URL will be read from X-Confluence-URL header dynamically")

    # Confluence 전용 서버를 위해 lifespan 설정
    confluence_mcp.lifespan = confluence_standalone_lifespan

    # confluence_mcp의 http_app 메서드를 교체하여 UserTokenMiddleware 추가
    from .main import UserTokenMiddleware
    from starlette.middleware import Middleware

    original_http_app = confluence_mcp.http_app
    def patched_http_app(path=None, middleware=None, transport="streamable-http"):
        """UserTokenMiddleware가 포함된 HTTP 앱을 생성합니다."""
        try:
            user_token_mw = Middleware(UserTokenMiddleware, mcp_server_ref=confluence_mcp)
            final_middleware = [user_token_mw]
            if middleware:
                final_middleware.extend(middleware)
            return original_http_app(path=path, middleware=final_middleware, transport=transport)
        except Exception as e:
            logger.error(f"Failed to create HTTP app with middleware: {e}", exc_info=True)
            raise

    confluence_mcp.http_app = patched_http_app

    # 실행 설정
    run_kwargs = {
        "transport": transport,
        "host": host,
        "port": port,
        "log_level": logging.getLevelName(current_logging_level).lower(),
        "path": path,
    }

    try:
        logger.debug("Starting Confluence-only server asyncio event loop...")
        asyncio.run(confluence_mcp.run_async(**run_kwargs))
    except (KeyboardInterrupt, SystemExit) as e:
        logger.info(f"Confluence-only server shutdown initiated: {type(e).__name__}")
    except Exception as e:
        logger.error(f"Confluence-only server encountered an error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main() 