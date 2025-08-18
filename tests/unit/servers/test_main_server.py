"""Tests for the main MCP server implementation."""

import json
import logging
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.testclient import TestClient

from mcp_atlassian.servers.main import main_mcp
from mcp_atlassian.utils.environment import MockEnvironment


@pytest.mark.anyio
async def test_run_server_invalid_transport():
    """Test that invalid transport raises ValueError."""
    with pytest.raises(ValueError) as excinfo:
        with MockEnvironment.basic_auth_env():
            main_mcp.run_async(transport="invalid")

    assert "invalid" in str(excinfo.value)


@pytest.mark.anyio
class TestUserTokenMiddleware:
    """Tests for the UserTokenMiddleware class."""

    @pytest.fixture
    def middleware(self):
        """Create a UserTokenMiddleware instance for testing."""
        mock_app = MagicMock()
        # Create a mock MCP server to avoid warnings
        mock_mcp_server = MagicMock()
        mock_mcp_server.settings.streamable_http_path = "/mcp"
        return UserTokenMiddleware(mock_app, mcp_server_ref=mock_mcp_server)

    @pytest.fixture
    def mock_request(self):
        """Create a mock request for testing."""
        request = MagicMock(spec=Request)
        request.url.path = "/mcp"
        request.method = "POST"
        request.headers = {}
        # Create a real state object that can be modified
        from types import SimpleNamespace

        request.state = SimpleNamespace()
        return request

    @pytest.fixture
    def mock_call_next(self):
        """Create a mock call_next function."""
        mock_response = JSONResponse({"test": "response"})
        call_next = AsyncMock(return_value=mock_response)
        return call_next

    @pytest.mark.anyio
    async def test_cloud_id_header_extraction_success(
        self, middleware, mock_request, mock_call_next
    ):
        """Test successful cloud ID header extraction."""
        # Setup request with cloud ID header
        mock_request.headers = {
            "Authorization": "Bearer test-token",
            "X-Atlassian-Cloud-Id": "test-cloud-id-123",
        }

        result = await middleware.dispatch(mock_request, mock_call_next)

        # Verify cloud ID was extracted and stored in request state
        assert hasattr(mock_request.state, "user_atlassian_cloud_id")
        assert mock_request.state.user_atlassian_cloud_id == "test-cloud-id-123"

        # Verify the request was processed normally
        mock_call_next.assert_called_once_with(mock_request)
        assert result is not None
