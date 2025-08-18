#!/usr/bin/env python3
"""
최종 개선된 로깅 시스템 테스트
"""

import asyncio
import json
import os
from unittest.mock import Mock

from fastmcp import Context
from src.mcp_atlassian.utils.decorators import (
    extract_mcp_context_info, 
    extract_mcp_debug_info,
    log_basic, 
    log_detailed,
    log_production
)


def safe_json_dumps(obj, indent=2):
    """JSON 직렬화 함수"""
    def default_handler(o):
        return str(o) if hasattr(o, '__class__') else str(o)
    
    try:
        return json.dumps(obj, indent=indent, ensure_ascii=False, default=default_handler)
    except Exception as e:
        return f"JSON 직렬화 실패: {e}"


def create_mock_context():
    """Mock Context 생성"""
    ctx = Mock(spec=Context)
    ctx.request_id = "mcp-request-12345"
    ctx.client_id = "test-client-67890"
    
    request_context = Mock()
    session = Mock()
    session.session_id = "session-abc123"
    request_context.session = session
    
    app_ctx = Mock()
    app_ctx.read_only = False
    app_ctx.enabled_tools = ['tool1', 'tool2', 'tool3']
    app_ctx.confluence_config = Mock()
    
    request_context.lifespan_context = {'app_lifespan_context': app_ctx}
    ctx.request_context = request_context
    
    return ctx


@log_basic()
async def test_basic_tool(ctx: Context, query: str = "test") -> str:
    """기본 로깅 테스트"""
    return f"Basic tool result: {query}"

@log_detailed()
async def test_detailed_tool(ctx: Context, query: str = "test") -> str:
    """상세 로깅 테스트 - 자동으로 디버그 정보 포함"""
    return f"Detailed tool result: {query}"

@log_production()
async def test_production_tool(ctx: Context, query: str = "test") -> str:
    """프로덕션 로깅 테스트 - MCP_VERBOSE에 따라 디버그 정보 포함"""
    return f"Production tool result: {query}"

# 모듈 경로 설정
test_basic_tool.__module__ = "src.mcp_atlassian.confluence.search"
test_detailed_tool.__module__ = "src.mcp_atlassian.jira.issues"
test_production_tool.__module__ = "src.mcp_atlassian.confluence.pages"


async def main():
    """테스트 실행"""
    print("=== 최종 개선된 로깅 시스템 테스트 ===\n")
    
    mock_ctx = create_mock_context()
    
    # 1. 기본 Context 정보 추출
    print("1. 기본 Context 정보 (항상 포함):")
    context_info = extract_mcp_context_info(mock_ctx)
    print(safe_json_dumps(context_info))
    print()
    
    # 2. 디버그 정보 추출
    print("2. 디버그 Context 정보 (별도 함수):")
    debug_info = extract_mcp_debug_info(mock_ctx)
    print(safe_json_dumps(debug_info))
    print()
    
    # 3. 기본 로깅 (디버그 정보 없음)
    print("3. 기본 로깅 테스트:")
    await test_basic_tool(mock_ctx, "basic test")
    print()
    
    # 4. 상세 로깅 (항상 디버그 정보 포함)
    print("4. 상세 로깅 테스트 (자동으로 디버그 정보 포함):")
    await test_detailed_tool(mock_ctx, "detailed test")
    print()
    
    # 5. 프로덕션 로깅 - MCP_VERBOSE=false
    print("5. 프로덕션 로깅 (MCP_VERBOSE=false):")
    os.environ.pop('MCP_VERBOSE', None)
    await test_production_tool(mock_ctx, "production test without debug")
    print()
    
    # 6. 프로덕션 로깅 - MCP_VERBOSE=true
    print("6. 프로덕션 로깅 (MCP_VERBOSE=true):")
    os.environ['MCP_VERBOSE'] = 'true'
    await test_production_tool(mock_ctx, "production test with debug")
    print()
    
    # 환경변수 정리
    os.environ.pop('MCP_VERBOSE', None)
    
    print("=== 테스트 완료 ===")
    print("\n💡 주요 개선사항:")
    print("   ✅ include_debug 매개변수 제거로 API 간소화")
    print("   ✅ log_detailed()는 항상 디버그 정보 포함")
    print("   ✅ log_production()은 MCP_VERBOSE 환경변수에 따라 디버그 정보 제어")
    print("   ✅ 기본 Context 정보와 디버그 정보의 명확한 분리")


if __name__ == "__main__":
    asyncio.run(main()) 