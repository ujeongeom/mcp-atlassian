import asyncio
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp_atlassian.utils.logging import setup_logging
from mcp_atlassian.utils.env import is_env_truthy
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.utils.tools import get_enabled_tools
from mcp_atlassian.utils.io import is_read_only_mode
from mcp_atlassian.servers.context import JiraAppContext
from fastmcp import FastMCP

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
    current_logging_level = logging.INFO
    if is_env_truthy("MCP_VERY_VERBOSE", "false"):
        current_logging_level = logging.DEBUG
    elif is_env_truthy("MCP_VERBOSE", "false"):
        current_logging_level = logging.INFO

    # STDOUT으로 로깅 설정 (Container Apps 환경에 최적화)
    logging_stream = sys.stdout if is_env_truthy("MCP_LOGGING_STDOUT") else sys.stderr
    setup_logging(current_logging_level, logging_stream)
    
    logger.info("Starting Jira-only MCP server for Container Apps deployment")

    # 환경 변수에서 설정 읽기
    transport = os.getenv("TRANSPORT", "streamable-http").lower()
    port = int(os.getenv("PORT", "9000"))
    host = os.getenv("HOST", "0.0.0.0")  # noqa: S104
    path = os.getenv("STREAMABLE_HTTP_PATH", "/mcp")

    logger.info(f"Server config: {transport} on {host}:{port}{path}")
    
    # 인증 방식 로깅
    jira_url = os.getenv("JIRA_URL")
    if jira_url:
        logger.info(f"Global Jira URL configured: {jira_url}")
    else:
        logger.info("No global Jira URL. Will use X-Jira-URL header for user requests.")

    # jira_mcp import
    from .jira import jira_mcp
    from .main import UserTokenMiddleware
    from starlette.middleware import Middleware

    # Jira 전용 서버를 위해 lifespan 교체
    jira_mcp.lifespan = jira_standalone_lifespan

    # jira_mcp의 http_app 메서드를 교체하여 UserTokenMiddleware 추가
    original_http_app = jira_mcp.http_app
    def patched_http_app(path=None, middleware=None, transport="streamable-http"):
        """UserTokenMiddleware가 포함된 HTTP 앱을 생성합니다."""
        try:
            user_token_mw = Middleware(UserTokenMiddleware, mcp_server_ref=jira_mcp)
            final_middleware = [user_token_mw]
            if middleware:
                final_middleware.extend(middleware)
            return original_http_app(path=path, middleware=final_middleware, transport=transport)
        except Exception as e:
            logger.error(f"Failed to create HTTP app with middleware: {e}", exc_info=True)
            raise

    jira_mcp.http_app = patched_http_app

    run_kwargs = {
        "transport": transport,
        "host": host,
        "port": port,
        "log_level": logging.getLevelName(current_logging_level).lower(),
        "path": path,
    }

    try:
        logger.debug("Starting Jira-only server asyncio event loop...")
        asyncio.run(jira_mcp.run_async(**run_kwargs))
    except (KeyboardInterrupt, SystemExit) as e:
        logger.info(f"Jira-only server shutdown initiated: {type(e).__name__}")
    except Exception as e:
        logger.error(f"Jira-only server encountered an error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main() 