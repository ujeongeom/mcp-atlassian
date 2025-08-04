"""Confluence-only MCP server entry point for Container Apps deployment."""

import asyncio
import logging
import os
import sys

from mcp_atlassian.utils.logging import setup_logging
from mcp_atlassian.utils.env import is_env_truthy

# Confluence MCP 인스턴스 import
from .confluence import confluence_mcp

logger = logging.getLogger("mcp-atlassian.confluence-server")


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