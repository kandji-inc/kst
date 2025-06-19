from collections.abc import Callable, Iterator
from pathlib import Path
from time import sleep
from urllib.parse import urljoin

import pytest
import requests

from kst.api import ApiConfig, CustomAppsResource


def upload_app(config: ApiConfig, app_name: str) -> tuple[str, dict[str, str], str]:
    """Get upload information for a dummy app in a Kandji tenant."""
    headers = {"Authorization": f"Bearer {config.api_token}"}
    resource_url = urljoin(config.url, "api/v1/library/custom-apps/upload")
    response = requests.post(
        resource_url,
        headers=headers,
        data={"name": app_name},
    )
    response.raise_for_status()
    file_key = response.json()["file_key"]
    post_data = response.json()["post_data"]
    post_url = response.json()["post_url"]
    return file_key, post_data, post_url


def upload_app_to_s3(post_url: str, post_data: dict[str, str], app_name: str, tmp_path: Path) -> bool:
    """Upload a dummy app to S3."""
    app_file = tmp_path / app_name
    app_file.write_text("dummy app data")
    response = requests.post(
        url=post_url,
        data=post_data,
        files=[("file", (app_name, app_file.open("rb")))],
    )
    response.raise_for_status()
    return True


def create_app(config: ApiConfig, file_key: str) -> str:
    """Create a single app in a Kandji tenant and return the app ID."""
    resource_url = urljoin(config.url, "api/v1/library/custom-apps")
    headers = {"Authorization": f"Bearer {config.api_token}"}
    payload = {
        "name": "Test App",
        "file_key": file_key,
        "install_type": "zip",
        "install_enforcement": "continuously_enforce",
        "audit_script": "#!/bin/bash\necho 'Audit script'",
        "preinstall_script": "#!/bin/bash\necho 'Pre-install script'",
        "postinstall_script": "#!/bin/bash\necho 'Post-install script'",
        "restart": False,
        "active": True,
        "show_in_self_service": False,
        "unzip_location": "/var/tmp",
    }
    max_attempts = 5
    for attempt in range(max_attempts):
        sleep(5)  # need to wait for the s3 upload to process
        response = requests.post(resource_url, headers=headers, json=payload)
        if response.status_code == 201:
            response.raise_for_status()
            return response.json()["id"]

        print(f"Attempt {attempt + 1}/{max_attempts}: Status code {response.status_code}")
        if attempt == max_attempts - 1:  # Last attempt
            response.raise_for_status()

    # This should never be reached due to raise_for_status(), but satisfies type checker
    raise RuntimeError("Failed to create app after all attempts")


def delete_app_factory(config: ApiConfig, app_id: str) -> Callable:
    """Return a function which deletes a specific app in a Kandji tenant.

    The function can be used directly or passed to addfinallizer() in order to setup
    cleanup steps after the test.
    """

    def delete_app():
        resource_url = urljoin(config.url, f"api/v1/library/custom-apps/{app_id}")
        headers = {"Authorization": f"Bearer {config.api_token}"}
        response = requests.delete(resource_url, headers=headers)
        if not response.ok and response.status_code != 404:
            response.raise_for_status()

    return delete_app


@pytest.fixture
def setup_live_apps_upload(config: ApiConfig) -> tuple[str, dict[str, str], str]:
    """Get post_data object, url and file_key from the Kandji API for uploading an app to S3."""
    app_name = "test_app.pkg"
    file_key, post_data, post_url = upload_app(config, app_name)
    return file_key, post_data, post_url


@pytest.fixture
def setup_live_apps_upload_to_s3(config: ApiConfig, tmp_path) -> str:
    """Upload a dummy app to S3."""
    app_name = "test_app.pkg"
    file_key, post_data, post_url = upload_app(config, app_name)
    upload_app_to_s3(post_url, post_data, app_name, tmp_path)
    return file_key


@pytest.fixture
def setup_live_apps_create_only(config: ApiConfig, tmp_path: Path) -> str:
    """Create an app in a Kandji tenant and return the app ID."""
    file_key, post_data, post_url = upload_app(config, "test_app.pkg")
    upload_app_to_s3(post_url, post_data, "test_app.pkg", tmp_path)
    app_id = create_app(config, file_key)
    return app_id


@pytest.fixture
def setup_live_apps_create_and_delete(config: ApiConfig, tmp_path: Path) -> Iterator[str]:
    """Create an app in a Kandji tenant and delete it after the test."""
    file_key, post_data, post_url = upload_app(config, "test_app.pkg")
    upload_app_to_s3(post_url, post_data, "test_app.pkg", tmp_path)
    app_id = create_app(config, file_key)
    yield app_id
    delete_app_factory(config, app_id)()


@pytest.fixture
def custom_apps_resource(config: ApiConfig) -> Iterator[CustomAppsResource]:
    """Return an open CustomAppsResource object."""
    with CustomAppsResource(config) as apps:
        yield apps
