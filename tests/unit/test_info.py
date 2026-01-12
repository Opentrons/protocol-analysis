"""Unit tests for the /info endpoint."""

import pytest
from api.main import get_info, InfoResponse, VERSION
from api.version_mapping import PROTOCOL_API_TO_ROBOT_STACK


@pytest.mark.asyncio
async def test_get_info_returns_correct_structure():
    """Test that get_info returns an InfoResponse with the correct structure."""
    response = await get_info()

    assert isinstance(response, InfoResponse)
    assert hasattr(response, "version")
    assert hasattr(response, "protocol_api_versions")
    assert hasattr(response, "supported_robot_versions")


@pytest.mark.asyncio
async def test_get_info_returns_current_version():
    """Test that get_info returns the current application version."""
    response = await get_info()

    assert response.version == VERSION
    assert response.version == "0.1.0"


@pytest.mark.asyncio
async def test_get_info_returns_protocol_api_mappings():
    """Test that get_info returns the protocol API to robot stack mappings."""
    response = await get_info()

    assert response.protocol_api_versions == PROTOCOL_API_TO_ROBOT_STACK
    assert isinstance(response.protocol_api_versions, dict)


@pytest.mark.asyncio
async def test_get_info_protocol_api_versions_not_empty():
    """Test that the protocol API versions mapping is not empty."""
    response = await get_info()

    assert len(response.protocol_api_versions) > 0


@pytest.mark.asyncio
async def test_get_info_protocol_api_versions_contain_expected_keys():
    """Test that the protocol API versions mapping contains expected version keys."""
    response = await get_info()

    # Check for some known protocol API versions (only 2.20 and up)
    expected_versions = [
        "2.20",
        "2.21",
        "2.22",
        "2.23",
        "2.24",
        "2.25",
        "2.26",
        "2.27",
        "2.28",
    ]
    for version in expected_versions:
        assert version in response.protocol_api_versions


@pytest.mark.asyncio
async def test_get_info_protocol_api_versions_values_are_strings():
    """Test that all values in the protocol API versions mapping are strings."""
    response = await get_info()

    for api_version, stack_version in response.protocol_api_versions.items():
        assert isinstance(api_version, str)
        assert isinstance(stack_version, str)
