import logging
import json
import time
import uuid
import psutil
import os
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar, Optional, Dict, Set

import requests
from fastmcp import Context
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def check_write_access(func: F) -> F:
    """
    Decorator for FastMCP tools to check if the application is in read-only mode.
    If in read-only mode, it raises a ValueError.
    Assumes the decorated function is async and has `ctx: Context` as its first argument.
    """

    @wraps(func)
    async def wrapper(ctx: Context, *args: Any, **kwargs: Any) -> Any:
        lifespan_ctx_dict = ctx.request_context.lifespan_context
        app_lifespan_ctx = (
            lifespan_ctx_dict.get("app_lifespan_context")
            if isinstance(lifespan_ctx_dict, dict)
            else None
        )  # type: ignore

        if app_lifespan_ctx is not None and app_lifespan_ctx.read_only:
            tool_name = func.__name__
            action_description = tool_name.replace(
                "_", " "
            )  # e.g., "create_issue" -> "create issue"
            logger.warning(f"Attempted to call tool '{tool_name}' in read-only mode.")
            raise ValueError(f"Cannot {action_description} in read-only mode.")

        return await func(ctx, *args, **kwargs)

    return wrapper  # type: ignore


def extract_mcp_context_info(ctx: Context) -> Dict[str, Any]:
    """
    MCP Context에서 stateless HTTP 모드에 최적화된 정보를 추출합니다.
    
    Args:
        ctx: FastMCP Context 객체
    """
    info = {}
    
    try:
        # Request ID (FastMCP에서 제공하는 기본 정보)
        if hasattr(ctx, 'request_id'):
            info['request_id'] = ctx.request_id
        
        # Stateless 모드에서는 최소한의 정보만 추출
        info['mode'] = 'stateless'
        
        # Request Context에서 기본적인 정보만 추출
        if hasattr(ctx, 'request_context') and ctx.request_context:
            req_ctx = ctx.request_context
            
            # Lifespan Context에서 기본 설정만 추출
            if hasattr(req_ctx, 'lifespan_context') and req_ctx.lifespan_context:
                lifespan_ctx = req_ctx.lifespan_context
                
                if isinstance(lifespan_ctx, dict):
                    app_ctx = lifespan_ctx.get("app_lifespan_context")
                    if app_ctx is not None:
                        # read_only 설정만 추출 (매 요청마다 확인 필요)
                        if hasattr(app_ctx, 'read_only'):
                            info['read_only'] = app_ctx.read_only
    
    except Exception as e:
        logger.warning(f"Failed to extract MCP context info: {e}")
    
    return info


def _get_memory_usage() -> float:
    """현재 프로세스의 메모리 사용량을 MB 단위로 반환합니다."""
    try:
        process = psutil.Process(os.getpid())
        return round(process.memory_info().rss / 1024 / 1024, 2)
    except Exception:
        return 0.0


def _determine_service_from_context(func: Any) -> str:
    """함수의 FastMCP 도구 등록 정보에서 서비스 타입을 추출합니다."""
    try:
        # FastMCP 도구의 태그에서 서비스 구분
        if hasattr(func, '__fastmcp_tool__'):
            tool_info = func.__fastmcp_tool__
            if hasattr(tool_info, 'tags') and tool_info.tags:
                if 'jira' in tool_info.tags:
                    return 'jira'
                elif 'confluence' in tool_info.tags:
                    return 'confluence'
        
        # 백업: 함수 모듈 경로에서 서비스 구분
        if hasattr(func, '__module__'):
            module_path = func.__module__
            if 'jira' in module_path:
                return 'jira'
            elif 'confluence' in module_path:
                return 'confluence'
                
    except Exception:
        pass
    
    return 'unknown'


def log_mcp_request_response(
    include_args: bool = False,
    include_result: bool = False,
    max_result_length: int = 1000,
    sensitive_keys: Optional[Set[str]] = None,
    include_performance_metrics: bool = False
) -> Callable[[F], F]:
    """
    Stateless HTTP 모드에 최적화된 MCP request/response 로깅 데코레이터.
    
    Args:
        include_args: Whether to log actual argument values (default: False for privacy)
        include_result: Whether to log actual result content (default: False for privacy)
        max_result_length: Maximum length of result to log if include_result=True
        sensitive_keys: Set of kwarg keys to exclude from logging
        include_performance_metrics: Whether to include memory usage and other metrics
    """
    if sensitive_keys is None:
        sensitive_keys = {
            'password', 'token', 'api_key', 'secret', 'auth', 'authorization',
            'bearer', 'key', 'credential', 'access_token', 'refresh_token'
        }
    
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(ctx: Context, *args: Any, **kwargs: Any) -> Any:
            tool_name = func.__name__
            start_time = time.time()
            
            # MCP Context에서 정보 추출 (stateless 모드 최적화)
            mcp_info = extract_mcp_context_info(ctx)
            
            # Request ID 사용 (FastMCP에서 제공하는 것 우선, 없으면 UUID 생성)
            request_id = mcp_info.get('request_id', str(uuid.uuid4())[:8])
            
            # 서비스 타입 결정 (함수 태그 기반)
            service_type = _determine_service_from_context(func)
            
            # 성능 메트릭 (시작)
            start_memory = _get_memory_usage() if include_performance_metrics else 0.0
            
            # 요청 로그 구성
            request_log = {
                "event": "MCP_REQUEST",
                "tool": tool_name,
                "service": service_type,
                "request_id": request_id,
                "timestamp": start_time,
                **mcp_info
            }
            
            # 성능 메트릭 추가
            if include_performance_metrics:
                request_log["performance"] = {
                    "start_memory_mb": start_memory,
                    "process_id": os.getpid()
                }
            
            # 인자 정보 처리
            if include_args:
                request_log["args"] = args
                # 민감한 키 제외하고 kwargs 로깅
                safe_kwargs = {
                    k: v for k, v in kwargs.items() 
                    if k.lower() not in sensitive_keys
                }
                sensitive_kwargs = {
                    k: "[REDACTED]" for k, v in kwargs.items() 
                    if k.lower() in sensitive_keys
                }
                request_log["kwargs"] = {**safe_kwargs, **sensitive_kwargs}
            else:
                request_log["args_count"] = len(args)
                request_log["kwargs_count"] = len(kwargs)
                # 민감하지 않은 키만 로깅
                safe_keys = [
                    k for k in kwargs.keys() 
                    if k.lower() not in sensitive_keys
                ]
                sensitive_keys_count = len(kwargs) - len(safe_keys)
                request_log["kwargs_keys"] = safe_keys
                if sensitive_keys_count > 0:
                    request_log["sensitive_kwargs_count"] = sensitive_keys_count
            
            logger.info(f"MCP_REQUEST: {json.dumps(request_log, default=str, ensure_ascii=False)}")
            
            try:
                # 도구 실행
                result = await func(ctx, *args, **kwargs)
                
                # 성공 응답 로그
                execution_time = time.time() - start_time
                end_memory = _get_memory_usage() if include_performance_metrics else 0.0
                
                response_log = {
                    "event": "MCP_RESPONSE",
                    "tool": tool_name,
                    "service": service_type,
                    "request_id": request_id,
                    "status": "success",
                    "execution_time_ms": round(execution_time * 1000, 2),
                    "timestamp": time.time(),
                    "business_operation": tool_name,  # 비즈니스 작업명 추가
                }
                
                # 도구별 메타데이터 추가 (비즈니스 컨텍스트)
                if include_args and args:
                    response_log["business_metadata"] = {
                        "input_count": len(args),
                        "input_types": [type(arg).__name__ for arg in args]
                    }
                
                if include_args and kwargs:
                    # 민감하지 않은 키만 포함
                    safe_kwargs = {
                        k: v for k, v in kwargs.items() 
                        if k.lower() not in sensitive_keys
                    }
                    if safe_kwargs:
                        response_log["business_metadata"] = response_log.get("business_metadata", {})
                        response_log["business_metadata"]["input_params"] = safe_kwargs
                
                # 결과 정보 추가
                if result is not None:
                    response_log["has_result"] = True
                    response_log["result_type"] = type(result).__name__
                    
                    # 선택적으로 실제 결과 내용 포함
                    if include_result:
                        result_str = str(result)
                        if len(result_str) > max_result_length:
                            response_log["result"] = result_str[:max_result_length] + "..."
                            response_log["result_truncated"] = True
                            response_log["result_full_length"] = len(result_str)
                        else:
                            response_log["result"] = result_str
                    else:
                        response_log["result_length"] = len(str(result))
                        
                    # JSON 응답인 경우 추가 분석
                    if isinstance(result, str):
                        try:
                            json_data = json.loads(result)
                            response_log["result_format"] = "json"
                            response_log["json_keys_count"] = len(json_data) if isinstance(json_data, dict) else None
                        except json.JSONDecodeError:
                            response_log["result_format"] = "string"
                else:
                    response_log["has_result"] = False
                
                # 성능 메트릭 추가
                if include_performance_metrics:
                    response_log["performance"] = {
                        "end_memory_mb": end_memory,
                        "memory_delta_mb": round(end_memory - start_memory, 2),
                    }
                
                logger.info(f"MCP_RESPONSE: {json.dumps(response_log, default=str, ensure_ascii=False)}")
                return result
                
            except Exception as e:
                # 에러 로그
                execution_time = time.time() - start_time
                end_memory = _get_memory_usage() if include_performance_metrics else 0.0
                
                error_log = {
                    "event": "MCP_ERROR",
                    "tool": tool_name,
                    "service": service_type,
                    "request_id": request_id,
                    "status": "error",
                    "error_type": type(e).__name__,
                    "error_message": str(e)[:500],
                    "execution_time_ms": round(execution_time * 1000, 2),
                    "timestamp": time.time(),
                }
                
                # 성능 메트릭 추가
                if include_performance_metrics:
                    error_log["performance"] = {
                        "end_memory_mb": end_memory,
                        "memory_delta_mb": round(end_memory - start_memory, 2),
                    }
                
                # Atlassian API 에러 특화 정보
                if isinstance(e, HTTPError) and hasattr(e, 'response'):
                    error_log["api_error"] = {
                        "status_code": e.response.status_code,
                        "reason": e.response.reason,
                    }
                elif isinstance(e, MCPAtlassianAuthenticationError):
                    error_log["error_category"] = "authentication"
                
                logger.error(f"MCP_ERROR: {json.dumps(error_log, default=str, ensure_ascii=False)}")
                raise

        return wrapper  # type: ignore
    
    return decorator


# Stateless HTTP 모드에 최적화된 로깅 데코레이터들
def log_basic() -> Callable[[F], F]:
    """기본 로깅: 민감한 정보 제외, 실행시간과 기본 정보만"""
    return log_mcp_request_response()


def log_detailed() -> Callable[[F], F]:
    """상세 로깅: 인자와 결과 포함 (개발/테스트용)"""
    return log_mcp_request_response(
        include_args=True, 
        include_result=True, 
        max_result_length=2000,
        include_performance_metrics=True
    )


def log_minimal() -> Callable[[F], F]:
    """최소 로깅: 실행시간과 성공/실패만"""
    return log_mcp_request_response(
        include_args=False, 
        include_result=False,
        include_performance_metrics=False
    )


def log_production() -> Callable[[F], F]:
    """프로덕션 로깅: 성능 최적화"""
    return log_mcp_request_response(
        include_args=False,
        include_result=False,
        include_performance_metrics=True,
        sensitive_keys={
            'password', 'token', 'api_key', 'secret', 'auth', 'authorization',
            'bearer', 'key', 'credential', 'access_token', 'refresh_token',
            'api_token', 'session_token', 'jwt', 'oauth'
        }
    )


# 기존 함수 (하위 호환성)
def log_mcp_request_response_legacy(func: F) -> F:
    """레거시 버전: 기존 코드와의 호환성을 위해 유지"""
    return log_basic()(func)


def handle_atlassian_api_errors(service_name: str = "Atlassian API") -> Callable:
    """
    Decorator to handle common Atlassian API exceptions (Jira, Confluence, etc.).

    Args:
        service_name: Name of the service for error logging (e.g., "Jira API").
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return func(self, *args, **kwargs)
            except HTTPError as http_err:
                if http_err.response is not None and http_err.response.status_code in [
                    401,
                    403,
                ]:
                    error_msg = (
                        f"Authentication failed for {service_name} "
                        f"({http_err.response.status_code}). "
                        "Token may be expired or invalid. Please verify credentials."
                    )
                    logger.error(error_msg)
                    raise MCPAtlassianAuthenticationError(error_msg) from http_err
                else:
                    operation_name = getattr(func, "__name__", "API operation")
                    logger.error(
                        f"HTTP error during {operation_name}: {http_err}",
                        exc_info=False,
                    )
                    raise http_err
            except KeyError as e:
                operation_name = getattr(func, "__name__", "API operation")
                logger.error(f"Missing key in {operation_name} results: {str(e)}")
                return []
            except requests.RequestException as e:
                operation_name = getattr(func, "__name__", "API operation")
                logger.error(f"Network error during {operation_name}: {str(e)}")
                return []
            except (ValueError, TypeError) as e:
                operation_name = getattr(func, "__name__", "API operation")
                logger.error(f"Error processing {operation_name} results: {str(e)}")
                return []
            except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
                operation_name = getattr(func, "__name__", "API operation")
                logger.error(f"Unexpected error during {operation_name}: {str(e)}")
                logger.debug(
                    f"Full exception details for {operation_name}:", exc_info=True
                )
                return []

        return wrapper

    return decorator


# 새로운 로깅 함수들 (시스템 이벤트, 인증 이벤트, 비즈니스 이벤트, 헬스체크)
def log_system_event(event_type: str, **kwargs) -> None:
    """
    시스템 이벤트 로깅 (시작/종료/설정 변경 등)
    
    Args:
        event_type: 이벤트 타입 (startup, shutdown, config_reload 등)
        **kwargs: 추가 정보
    """
    log_data = {
        "event": "MCP_SYSTEM_EVENT",
        "type": event_type,
        "timestamp": time.time(),
        **kwargs
    }
    logger.info(f"MCP_SYSTEM_EVENT: {json.dumps(log_data, default=str, ensure_ascii=False)}")


def log_auth_event(event_type: str, service: str, user: str = None, **kwargs) -> None:
    """
    인증 이벤트 로깅 (로그인/로그아웃/토큰 만료 등)
    
    Args:
        event_type: 이벤트 타입 (login, logout, token_expired, permission_denied 등)
        service: 서비스명 (jira, confluence)
        user: 사용자 식별자 (선택적)
        **kwargs: 추가 정보
    """
    log_data = {
        "event": "MCP_AUTH_EVENT",
        "type": event_type,
        "service": service,
        "timestamp": time.time(),
        **kwargs
    }
    if user:
        log_data["user"] = user
    logger.info(f"MCP_AUTH_EVENT: {json.dumps(log_data, default=str, ensure_ascii=False)}")


def log_business_event(operation: str, service: str, input_metadata: dict = None, output_metadata: dict = None, **kwargs) -> None:
    """
    비즈니스 로직 이벤트 로깅 (핵심 작업 추적)
    
    Args:
        operation: 작업명 (issue_creation, page_update, search_query 등)
        service: 서비스명 (jira, confluence)
        input_metadata: 입력 데이터 메타데이터 (선택적)
        output_metadata: 출력 데이터 메타데이터 (선택적)
        **kwargs: 추가 정보
    """
    log_data = {
        "event": "MCP_BUSINESS_EVENT",
        "operation": operation,
        "service": service,
        "timestamp": time.time(),
        **kwargs
    }
    if input_metadata:
        log_data["input_metadata"] = input_metadata
    if output_metadata:
        log_data["output_metadata"] = output_metadata
    logger.info(f"MCP_BUSINESS_EVENT: {json.dumps(log_data, default=str, ensure_ascii=False)}")