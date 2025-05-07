import pytest

from kst.api import CustomProfilesResource
from kst.exceptions import ApiClientError


def test_client_exists_in_context_manager(config):
    custom_profiles_resource = CustomProfilesResource(config)

    assert custom_profiles_resource._client is None
    with pytest.raises(ApiClientError) as exc_info:
        custom_profiles_resource.client
    assert str(exc_info.value) == "No open client available."

    with custom_profiles_resource as profiles:
        assert profiles.client is not None

    assert custom_profiles_resource._client is None
    with pytest.raises(ApiClientError) as exc_info:
        custom_profiles_resource.client
    assert str(exc_info.value) == "No open client available."
