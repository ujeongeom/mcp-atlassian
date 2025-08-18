"""Common utilities for MCP server implementations."""

import asyncio
import logging
import os
import sys
from typing import Any

from fastmcp import FastMCP
from starlette.middleware import Middleware

from mcp_atlassian.utils.env import is_env_truthy
from mcp_atlassian.utils.logging import setup_logging

from .main import UserTokenMiddleware

logger = logging.getLogger("mcp-atlassian.server.common")


def setup_server_logging() -> int:
    """공통 로깅 설정 함수."""
    current_logging_level = logging.INFO  # 기본값을 INFO로 변경
    if is_env_truthy("MCP_VERBOSE", "false"):
        current_logging_level = logging.DEBUG  # DEBUG는 MCP_VERBOSE로만 활성화

    # STDOUT으로 로깅 설정 (Container Apps 환경에 최적화)
    logging_stream = sys.stdout if is_env_truthy("MCP_LOGGING_STDOUT") else sys.stderr
    setup_logging(current_logging_level, logging_stream)
    
    return current_logging_level


def get_server_config() -> dict[str, Any]:
    """환경변수에서 서버 설정을 읽어오는 공통 함수."""    
    return {
        "transport": os.getenv("TRANSPORT", "streamable-http").lower(),
        "port": int(os.getenv("PORT", "9000")),
        "host": os.getenv("HOST", "0.0.0.0"),  # noqa: S104
        "path": os.getenv("STREAMABLE_HTTP_PATH", "/mcp"),
        "stateless_http": True,  # FastMCP stateless 모드로 고정
    }


def add_user_token_middleware(mcp_instance: FastMCP, service_name: str) -> None:
    """MCP 인스턴스에 UserTokenMiddleware를 추가하는 공통 함수."""
    original_http_app = mcp_instance.http_app
    
    def patched_http_app(path=None, middleware=None, transport="streamable-http"):
        """UserTokenMiddleware가 포함된 HTTP 앱을 생성합니다."""
        try:
            user_token_mw = Middleware(UserTokenMiddleware, mcp_server_ref=mcp_instance)
            final_middleware = [user_token_mw]
            if middleware:
                final_middleware.extend(middleware)
            logger.info(f"Added UserTokenMiddleware to {service_name} server")
            return original_http_app(path=path, middleware=final_middleware, transport=transport)
        except Exception as e:
            logger.error(f"Failed to create HTTP app with middleware: {e}", exc_info=True)
            raise

    mcp_instance.http_app = patched_http_app


def run_mcp_server(
    mcp_instance: FastMCP,
    server_config: dict[str, Any],
    logging_level: int,
    service_name: str,
) -> None:
    """MCP 서버를 실행하는 공통 함수."""    
    # stateless_http 설정을 FastMCP 인스턴스에 적용 (run_async 호출 전에 설정 필요)
    if "stateless_http" in server_config:
        mcp_instance.settings.stateless_http = server_config["stateless_http"]
        logger.info(f"Set stateless_http to {server_config['stateless_http']} for {service_name} server")
    
    run_kwargs = {
        "transport": server_config["transport"],
        "host": server_config["host"],
        "port": server_config["port"],
        "log_level": logging.getLevelName(logging_level).lower(),
        "path": server_config["path"],
    }

    try:
        logger.debug(f"Starting {service_name} server asyncio event loop...")
        asyncio.run(mcp_instance.run_async(**run_kwargs))
    except (KeyboardInterrupt, SystemExit) as e:
        logger.info(f"{service_name} server shutdown initiated: {type(e).__name__}")
    except Exception as e:
        logger.error(f"{service_name} server encountered an error: {e}", exc_info=True)
        sys.exit(1) 