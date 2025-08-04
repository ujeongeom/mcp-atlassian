"""Dependency providers for JiraFetcher and ConfluenceFetcher with context awareness.

Provides get_jira_fetcher and get_confluence_fetcher for use in tool functions.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any

from fastmcp import Context
from fastmcp.server.dependencies import get_http_request
from starlette.requests import Request

from mcp_atlassian.confluence import ConfluenceConfig, ConfluenceFetcher
from mcp_atlassian.jira import JiraConfig, JiraFetcher
from mcp_atlassian.servers.context import MainAppContext

if TYPE_CHECKING:
    from mcp_atlassian.confluence.config import (
        ConfluenceConfig as UserConfluenceConfigType,
    )
    from mcp_atlassian.jira.config import JiraConfig as UserJiraConfigType

logger = logging.getLogger("mcp-atlassian.servers.dependencies")


def _create_user_config_for_fetcher(
    base_config: JiraConfig | ConfluenceConfig,
    auth_type: str,
    credentials: dict[str, Any],
    cloud_id: str | None = None,
) -> JiraConfig | ConfluenceConfig:
    """Create a user-specific configuration for Jira or Confluence fetchers.

    Args:
        base_config: The base JiraConfig or ConfluenceConfig to clone and modify.
        auth_type: The authentication type (only 'api_token' supported).
        credentials: Dictionary of credentials (token, email, etc).
        cloud_id: Optional cloud ID (not used for Bearer token auth).

    Returns:
        JiraConfig or ConfluenceConfig with user-specific credentials.

    Raises:
        ValueError: If required credentials are missing or auth_type is unsupported.
        TypeError: If base_config is not a supported type.
    """
    if auth_type != "api_token":
        raise ValueError(
            f"Unsupported auth_type '{auth_type}' for user-specific config creation. Only 'api_token' is supported."
        )

    username_for_config: str | None = credentials.get("user_email_context")

    logger.debug(
        f"Creating user config for fetcher. Auth type: {auth_type}, Credentials keys: {credentials.keys()}, Cloud ID: {cloud_id}"
    )

    common_args: dict[str, Any] = {
        "url": base_config.url,
        "auth_type": auth_type,  # 원래대로 그대로 전달
        "ssl_verify": base_config.ssl_verify,
        "http_proxy": base_config.http_proxy,
        "https_proxy": base_config.https_proxy,
        "no_proxy": base_config.no_proxy,
        "socks_proxy": base_config.socks_proxy,
    }

    # Bearer Token (API Token) 처리
        user_api_token = credentials.get("api_token")
        if not user_api_token:
            raise ValueError("API token missing in credentials for user auth_type 'api_token'")

        # Log warning if cloud_id is provided with API token auth (not typically needed)
        if cloud_id:
            logger.warning(
                f"Cloud ID '{cloud_id}' provided with API token authentication. "
                "API token authentication typically uses the base URL directly and doesn't require cloud_id override."
            )

    # API token을 basic auth로 사용 (Atlassian Cloud의 username/password 방식)
        common_args.update(
            {
            "auth_type": "basic",  # API 토큰은 basic auth로 처리
                "personal_token": None,  # Atlassian Cloud에서는 api_token 사용
                "oauth_config": None,
                "username": username_for_config,  # 사용자 이메일을 username으로 설정
                "api_token": user_api_token,  # API 토큰을 api_token 필드에 설정
            }
        )

    if isinstance(base_config, JiraConfig):
        user_jira_config: UserJiraConfigType = dataclasses.replace(
            base_config, **common_args
        )
        user_jira_config.projects_filter = base_config.projects_filter
        return user_jira_config
    elif isinstance(base_config, ConfluenceConfig):
        user_confluence_config: UserConfluenceConfigType = dataclasses.replace(
            base_config, **common_args
        )
        user_confluence_config.spaces_filter = base_config.spaces_filter
        return user_confluence_config
    else:
        raise TypeError(f"Unsupported base_config type: {type(base_config)}")


async def get_jira_fetcher(ctx: Context) -> JiraFetcher:
    """Returns a JiraFetcher instance appropriate for the current request context.

    Args:
        ctx: The FastMCP context.

    Returns:
        JiraFetcher instance for the current user or global config.

    Raises:
        ValueError: If configuration or credentials are invalid.
    """
    logger.debug(f"get_jira_fetcher: ENTERED. Context ID: {id(ctx)}")
    try:
        request: Request = get_http_request()
        logger.debug(
            f"get_jira_fetcher: In HTTP request context. Request URL: {request.url}. "
            f"State.jira_fetcher exists: {hasattr(request.state, 'jira_fetcher') and request.state.jira_fetcher is not None}. "
            f"State.user_auth_type: {getattr(request.state, 'user_atlassian_auth_type', 'N/A')}. "
            f"State.user_token_present: {hasattr(request.state, 'user_atlassian_token') and request.state.user_atlassian_token is not None}."
        )
        # Use fetcher from request.state if already present
        if hasattr(request.state, "jira_fetcher") and request.state.jira_fetcher:
            logger.debug("get_jira_fetcher: Returning JiraFetcher from request.state.")
            return request.state.jira_fetcher
        user_auth_type = getattr(request.state, "user_atlassian_auth_type", None)
        user_token = getattr(request.state, "user_atlassian_token", None)
        
        logger.debug(f"get_jira_fetcher: User auth type: {user_auth_type}")
        logger.debug(f"get_jira_fetcher: User token present: {user_token is not None}")
        
        # If OAuth or API Token is present, create user-specific fetcher
        if user_auth_type == "api_token" and user_token:
            user_email = getattr(
                request.state, "user_atlassian_email", None
            )  # May be None for PAT
            user_cloud_id = getattr(request.state, "user_atlassian_cloud_id", None)
            credentials = {"user_email_context": user_email}
            if user_auth_type == "api_token":
                credentials["api_token"] = user_token
            lifespan_ctx_dict = ctx.request_context.lifespan_context  # type: ignore
            app_lifespan_ctx: MainAppContext | None = (
                lifespan_ctx_dict.get("app_lifespan_context")
                if isinstance(lifespan_ctx_dict, dict)
                else None
            )
            # 전역 설정이 없으면 기본 설정으로 사용자별 설정 생성
            if not app_lifespan_ctx or not app_lifespan_ctx.full_jira_config:
                logger.warning(
                    "Jira global configuration not available. Creating minimal config for user-specific authentication."
                )
                # 기본 설정으로 사용자별 설정 생성
                from mcp_atlassian.jira.config import JiraConfig
                import os
                
                # 헤더에서 Jira URL 확인 (우선순위: 헤더 > 환경변수)
                jira_url_header = request.headers.get("X-Jira-URL")
                if jira_url_header and jira_url_header.strip():
                    jira_url = jira_url_header.strip()
                    logger.debug(f"Using Jira URL from header: {jira_url}")
                else:
                    jira_url = os.getenv("JIRA_URL")
                    if not jira_url:
                        raise ValueError("Jira URL is required. Please provide it via X-Jira-URL header or JIRA_URL environment variable.")
                    logger.debug(f"Using Jira URL from environment: {jira_url}")
                
                base_config = JiraConfig(
                    url=jira_url,  # 헤더 또는 환경변수에서 가져오거나 기본값 사용
                    auth_type="basic",  # 기본 auth_type (인증 정보는 사용자별로 처리)
                    ssl_verify=False,  # SSL 검증 무시
                )
            else:
                base_config = app_lifespan_ctx.full_jira_config

            cloud_id_info = f" with cloudId {user_cloud_id}" if user_cloud_id else ""
            logger.info(
                f"Creating user-specific JiraFetcher (type: {user_auth_type}) for user {user_email or 'unknown'} (token ...{str(user_token)[-8:]}){cloud_id_info}"
            )
            user_specific_config = _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type=user_auth_type,
                credentials=credentials,
                cloud_id=user_cloud_id,
            )
            try:
                user_jira_fetcher = JiraFetcher(config=user_specific_config)
                current_user_id = user_jira_fetcher.get_current_user_account_id()
                logger.debug(
                    f"get_jira_fetcher: Validated Jira token for user ID: {current_user_id}"
                )
                request.state.jira_fetcher = user_jira_fetcher
                return user_jira_fetcher
            except Exception as e:
                logger.error(
                    f"get_jira_fetcher: Failed to create/validate user-specific JiraFetcher: {e}",
                    exc_info=True,
                )
                raise ValueError(f"Invalid user Jira token or configuration: {e}")
        else:
            logger.debug(
                f"get_jira_fetcher: No user-specific JiraFetcher. Auth type: {user_auth_type}. Token present: {hasattr(request.state, 'user_atlassian_token')}. Will use global fallback."
            )
    except RuntimeError:
        logger.debug(
            "Not in an HTTP request context. Attempting global JiraFetcher for non-HTTP."
        )
    # Fallback to global fetcher if not in HTTP context or no user info
    lifespan_ctx_dict_global = ctx.request_context.lifespan_context  # type: ignore
    app_lifespan_ctx_global = (
        lifespan_ctx_dict_global.get("app_lifespan_context")
        if isinstance(lifespan_ctx_dict_global, dict)
        else None
    )
    
    # MainAppContext 또는 JiraAppContext 둘 다 지원
    if app_lifespan_ctx_global:
        # full_jira_config 속성이 있는지 확인 (호환성)
        if hasattr(app_lifespan_ctx_global, 'full_jira_config'):
            global_config = app_lifespan_ctx_global.full_jira_config
        elif hasattr(app_lifespan_ctx_global, 'jira_config'):
            global_config = app_lifespan_ctx_global.jira_config
        else:
            global_config = None
            
        if global_config and hasattr(global_config, 'is_auth_configured') and global_config.is_auth_configured():
            logger.info("Using global Jira configuration as fallback")
            return JiraFetcher(global_config)
    
    # 여전히 설정이 없으면 에러 발생
    logger.error("No Jira configuration available (neither user-specific nor global)")
    raise ValueError(
        "Jira authentication required. Please provide user token via Authorization header "
        "or configure global Jira credentials."
    )


async def get_confluence_fetcher(ctx: Context) -> ConfluenceFetcher:
    """Returns a ConfluenceFetcher instance appropriate for the current request context.

    Args:
        ctx: The FastMCP context.

    Returns:
        ConfluenceFetcher instance for the current user or global config.

    Raises:
        ValueError: If configuration or credentials are invalid.
    """
    logger.debug(f"get_confluence_fetcher: ENTERED. Context ID: {id(ctx)}")
    try:
        request: Request = get_http_request()
        logger.debug(
            f"get_confluence_fetcher: In HTTP request context. Request URL: {request.url}. "
            f"State.confluence_fetcher exists: {hasattr(request.state, 'confluence_fetcher') and request.state.confluence_fetcher is not None}. "
            f"State.user_auth_type: {getattr(request.state, 'user_atlassian_auth_type', 'N/A')}. "
            f"State.user_token_present: {hasattr(request.state, 'user_atlassian_token') and request.state.user_atlassian_token is not None}."
        )
        if (
            hasattr(request.state, "confluence_fetcher")
            and request.state.confluence_fetcher
        ):
            logger.debug(
                "get_confluence_fetcher: Returning ConfluenceFetcher from request.state."
            )
            return request.state.confluence_fetcher
        user_auth_type = getattr(request.state, "user_atlassian_auth_type", None)
        user_token = getattr(request.state, "user_atlassian_token", None)
        
        logger.debug(f"get_confluence_fetcher: User auth type: {user_auth_type}")
        logger.debug(f"get_confluence_fetcher: User token present: {user_token is not None}")
        
        if user_auth_type == "api_token" and user_token:
            user_email = getattr(request.state, "user_atlassian_email", None)
            user_cloud_id = getattr(request.state, "user_atlassian_cloud_id", None)
            credentials = {"user_email_context": user_email}
            if user_auth_type == "api_token":
                credentials["api_token"] = user_token
            lifespan_ctx_dict = ctx.request_context.lifespan_context  # type: ignore
            app_lifespan_ctx: MainAppContext | None = (
                lifespan_ctx_dict.get("app_lifespan_context")
                if isinstance(lifespan_ctx_dict, dict)
                else None
            )
            # 전역 설정이 없으면 기본 설정으로 사용자별 설정 생성
            if not app_lifespan_ctx or not app_lifespan_ctx.full_confluence_config:
                logger.warning(
                    "Confluence global configuration not available. Creating minimal config for user-specific authentication."
                )
                # 기본 설정으로 사용자별 설정 생성
                from mcp_atlassian.confluence.config import ConfluenceConfig
                import os
                
                # 헤더에서 Confluence URL 확인 (우선순위: 헤더 > 환경변수)
                confluence_url_header = request.headers.get("X-Confluence-URL")
                if confluence_url_header and confluence_url_header.strip():
                    confluence_url = confluence_url_header.strip()
                    logger.debug(f"Using Confluence URL from header: {confluence_url}")
                else:
                    confluence_url = os.getenv("CONFLUENCE_URL")
                    if not confluence_url:
                        raise ValueError("Confluence URL is required. Please provide it via X-Confluence-URL header or CONFLUENCE_URL environment variable.")
                    logger.debug(f"Using Confluence URL from environment: {confluence_url}")
                
                base_config = ConfluenceConfig(
                    url=confluence_url,  # 헤더 또는 환경변수에서 가져오거나 기본값 사용
                    auth_type="basic",  # 기본 auth_type (인증 정보는 사용자별로 처리)
                    ssl_verify=False,  # SSL 검증 무시
                )
            else:
                base_config = app_lifespan_ctx.full_confluence_config

            cloud_id_info = f" with cloudId {user_cloud_id}" if user_cloud_id else ""
            logger.info(
                f"Creating user-specific ConfluenceFetcher (type: {user_auth_type}) for user {user_email or 'unknown'} (token ...{str(user_token)[-8:]}){cloud_id_info}"
            )
            user_specific_config = _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type=user_auth_type,
                credentials=credentials,
                cloud_id=user_cloud_id,
            )
            try:
                user_confluence_fetcher = ConfluenceFetcher(config=user_specific_config)
                current_user_data = user_confluence_fetcher.get_current_user_info()
                # Try to get email from Confluence if not provided (can happen with PAT)
                derived_email = (
                    current_user_data.get("email")
                    if isinstance(current_user_data, dict)
                    else None
                )
                display_name = (
                    current_user_data.get("displayName")
                    if isinstance(current_user_data, dict)
                    else None
                )
                logger.debug(
                    f"get_confluence_fetcher: Validated Confluence token. User context: Email='{user_email or derived_email}', DisplayName='{display_name}'"
                )
                request.state.confluence_fetcher = user_confluence_fetcher
                if (
                    not user_email
                    and derived_email
                    and current_user_data
                    and isinstance(current_user_data, dict)
                    and current_user_data.get("email")
                ):
                    request.state.user_atlassian_email = current_user_data["email"]
                return user_confluence_fetcher
            except Exception as e:
                logger.error(
                    f"get_confluence_fetcher: Failed to create/validate user-specific ConfluenceFetcher: {e}"
                )
                raise ValueError(f"Invalid user Confluence token or configuration: {e}")
        else:
            logger.debug(
                f"get_confluence_fetcher: No user-specific ConfluenceFetcher. Auth type: {user_auth_type}. Token present: {hasattr(request.state, 'user_atlassian_token')}. Will use global fallback."
            )
    except RuntimeError:
        logger.debug(
            "Not in an HTTP request context. Attempting global ConfluenceFetcher for non-HTTP."
        )
    lifespan_ctx_dict_global = ctx.request_context.lifespan_context  # type: ignore
    app_lifespan_ctx_global = (
        lifespan_ctx_dict_global.get("app_lifespan_context")
        if isinstance(lifespan_ctx_dict_global, dict)
        else None
    )
    
    # MainAppContext 또는 ConfluenceAppContext 둘 다 지원
    if app_lifespan_ctx_global:
        # full_confluence_config 속성이 있는지 확인 (호환성)
        if hasattr(app_lifespan_ctx_global, 'full_confluence_config'):
            global_config = app_lifespan_ctx_global.full_confluence_config
        elif hasattr(app_lifespan_ctx_global, 'confluence_config'):
            global_config = app_lifespan_ctx_global.confluence_config
        else:
            global_config = None
            
        if global_config and hasattr(global_config, 'is_auth_configured') and global_config.is_auth_configured():
            logger.info("Using global Confluence configuration as fallback")
            return ConfluenceFetcher(global_config)
    
    # 여전히 설정이 없으면 에러 발생
    logger.error("No Confluence configuration available (neither user-specific nor global)")
    raise ValueError(
        "Confluence authentication required. Please provide user token via Authorization header "
        "or configure global Confluence credentials."
    )
