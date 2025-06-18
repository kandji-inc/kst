from collections.abc import Iterator

import pytest

from kst.api import ApiConfig, CustomAppsResource


@pytest.fixture
def custom_apps_resource(config: ApiConfig) -> Iterator[CustomAppsResource]:
    """Return an open CustomProfilesResource object."""
    with CustomAppsResource(config) as apps:
        yield apps
