"""Logging utilities for MCP Atlassian.

This module provides enhanced logging capabilities for MCP Atlassian,
including level-dependent stream handling to route logs to the appropriate
output stream based on their level.
"""

import logging
import sys
from typing import TextIO

from .env import is_env_truthy

def setup_logging(
    level: int = logging.WARNING, stream: TextIO = sys.stderr
) -> logging.Logger:
    """
    Configure MCP-Atlassian logging with level-based stream routing.

    Args:
        level: The minimum logging level to display (default: WARNING)
        stream: The stream to write logs to (default: sys.stderr)

    Returns:
        The configured logger instance
    """
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to prevent duplication
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add the level-dependent handler
    handler = logging.StreamHandler(stream)
    formatter = logging.Formatter("%(levelname)s - %(name)s - %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Configure specific loggers with unified naming
    loggers = [
        "mcp-atlassian",           # Main application logger
        "mcp-atlassian.jira",      # JIRA specific logger
        "mcp-atlassian.confluence", # Confluence specific logger
        "mcp-atlassian.server",    # Server related logger
        "mcp.server",              # MCP protocol logger
        "mcp.server.lowlevel.server"
    ]

    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)

    # HTTP 로깅 활성화 (환경 변수로 제어)
    if is_env_truthy("MCP_HTTP_DEBUG", "false"):
        # urllib3와 requests HTTP 로깅 활성화
        for logger_name in ["urllib3", "urllib3.connectionpool", "requests", "requests.packages.urllib3"]:
            logging.getLogger(logger_name).setLevel(logging.DEBUG)
        logging.getLogger("mcp-atlassian").info("HTTP request/response logging enabled")

    # Return the application logger
    return logging.getLogger("mcp-atlassian")


def get_logger(service: str = "main") -> logging.Logger:
    """
    Get a logger with consistent naming for Container Apps deployment.
    
    Args:
        service: Service name ('jira', 'confluence', 'main')
        
    Returns:
        Configured logger instance
    """
    if service == "jira":
        return logging.getLogger("mcp-atlassian.jira")
    elif service == "confluence":
        return logging.getLogger("mcp-atlassian.confluence")
    else:
        return logging.getLogger("mcp-atlassian")





def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """Mask sensitive values for safe logging.

    Args:
        value: The value to mask
        visible_chars: Number of characters to show at start and end

    Returns:
        Masked value
    """
    if not value:
        return "***"
    
    if len(value) <= visible_chars * 2:
        return "***"
    
    return f"{value[:visible_chars]}***{value[-visible_chars:]}"


def get_masked_session_headers(headers: dict[str, str]) -> dict[str, str]:
    """Get session headers with sensitive values masked for safe logging.

    Args:
        headers: Dictionary of HTTP headers

    Returns:
        Dictionary with sensitive headers masked
    """
    sensitive_headers = {"Authorization", "Cookie", "Set-Cookie", "Proxy-Authorization"}
    masked_headers = {}

    for key, value in headers.items():
        if key in sensitive_headers:
            if key == "Authorization":
                # Preserve auth type but mask the credentials
                if value.startswith("Basic "):
                    masked_headers[key] = f"Basic {mask_sensitive(value[6:])}"
                elif value.startswith("Bearer "):
                    masked_headers[key] = f"Bearer {mask_sensitive(value[7:])}"
                else:
                    masked_headers[key] = mask_sensitive(value)
            else:
                masked_headers[key] = mask_sensitive(value)
        else:
            masked_headers[key] = str(value)

    return masked_headers


def log_config_param(param_name: str, value: str | None, mask: bool = True) -> None:
    """Log configuration parameter with optional masking.

    Args:
        param_name: Parameter name
        value: Parameter value
        mask: Whether to mask the value
    """
    logger = logging.getLogger("mcp-atlassian")
    if value is None:
        logger.debug(f"Config {param_name}: None")
    elif mask:
        logger.debug(f"Config {param_name}: {mask_sensitive(value)}")
    else:
        logger.debug(f"Config {param_name}: {value}")
