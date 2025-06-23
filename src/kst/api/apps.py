import logging
from enum import StrEnum
from io import BufferedReader
from pathlib import Path
from time import sleep

import requests

from kst.api.client import ApiClientError
from kst.console import OutputConsole

from .payload import CustomAppPayload, CustomAppUploadPayload, PayloadList
from .resource_base import ResourceBase

console = OutputConsole(logging.getLogger(__name__))

SHOW_IN_SELF_SERVICE_EXAMPLE = """Example:
  "show_in_self_service": true
  "self_service_category_id": "ae492437-c35f-46a3-bd0b-21188a69dfb1"
"""


class InstallType(StrEnum):
    """An enumeration of possible installation types for a custom app."""

    PACKAGE = "package"
    ZIP = "zip"
    IMAGE = "image"


class InstallEnforcement(StrEnum):
    """An enumeration of possible installation enforcement types for a custom app."""

    INSTALL_ONCE = "install_once"
    CONTINUOUSLY_ENFORCE = "continuously_enforce"
    NO_ENFORCEMENT = "no_enforcement"


class CustomAppsResource(ResourceBase):
    """An API client wrapper for interacting with the Custom Apps endpoint.

    Attributes:
        client (ApiClient): An ApiClient object with an open Session

    Methods:
        list: Retrieve a list of all custom apps
        get: Retrieve a single custom app by id
        create: Create a new custom app
        update: Update an existing custom app by id
        delete: Delete an existing custom app by id

    """

    _path = "/api/v1/library/custom-apps"

    def _upload_file(self, file: Path | BufferedReader) -> str:
        """Upload a file to S3 with exponential backoff retry logic.

        Args:
            file (Path | BufferedReader): File to upload (Path object or open BufferedReader)

        Returns:
            str: The S3 file key for the uploaded file

        Raises:
            FileNotFoundError: Raised when the file does not exist or is not readable
            ValueError: Raised when invalid file type is provided
            ApiClientError: Raised if a ApiClient has not been opened
            HTTPError: Raised when the HTTP request returns an unsuccessful status code
            ConnectionError: Raised when S3 upload fails after retries
            ValidationError: Raised when the response does not match the expected schema

        """
        if isinstance(file, Path):
            if not file.is_file():
                raise FileNotFoundError(f"The file {file} does not exist or is not readable")
            file_obj = file.open("rb")
        elif isinstance(file, BufferedReader):
            file_obj = file
        else:
            raise ValueError("Invalid file type provided. Must be a Path or BufferedReader object.")
        file_name = file.name

        # Get upload details from API
        payload = {"name": file_name}
        response = self.client.post(f"{self._path}/upload", data=payload)
        upload_response = CustomAppUploadPayload.model_validate_json(response.content)

        # Upload to S3
        files = [("file", (file_name, file_obj, "application/octet-stream"))]
        response = self.s3_client.post(upload_response.post_url, data=upload_response.post_data, files=files)
        if response.status_code != 204:
            raise ConnectionError(f"Failed to upload file to S3: {response.text}")

        return upload_response.file_key

    def list(self) -> PayloadList[CustomAppPayload]:
        """Retrieve a list of all custom apps.

        Returns:
            PayloadList: An object containing all combined results

        Raises:
            ApiClientError: Raised if a ApiClient has not been opened
            HTTPError: Raised when the HTTP request returns an unsuccessful status code
            ConnectionError: Raised when the API connection fails
            ValidationError: Raised when the response does not match the expected schema

        """

        all_results = PayloadList[CustomAppPayload]()
        next_page = self._path
        while next_page:
            response = self.client.get(next_page)

            # Parse bytes content to CustomAppPayloadList or raise ValidationError
            app_list = PayloadList[CustomAppPayload].model_validate_json(response.content)

            all_results.count = app_list.count
            all_results.results.extend(app_list.results)

            next_page = app_list.next

        return all_results

    def get(self, id: str) -> CustomAppPayload:
        """Retrieve details about a custom app.

        Args:
            id (str): The library item id of the app to retrieve

        Returns:
            CustomAppPayload: A parsed object from the response

        Raises:
            ApiClientError: Raised if a ApiClient has not been opened
            HTTPError: Raised when the HTTP request returns an unsuccessful status code
            ConnectionError: Raised when the API connection fails
            ValidationError: Raised when the response does not match the expected schema

        """
        response = self.client.get(f"{self._path}/{id}")
        return CustomAppPayload.model_validate_json(response.content)

    def create(
        self,
        name: str,
        file: Path | BufferedReader,
        install_type: InstallType,
        install_enforcement: InstallEnforcement,
        audit_script: str,
        preinstall_script: str,
        postinstall_script: str,
        restart: bool,
        active: bool,
        show_in_self_service: bool | None = False,
        self_service_category_id: str | None = None,
        self_service_recommended: bool | None = None,
        unzip_location: str | None = None,
    ) -> CustomAppPayload:
        """Create a new custom app in Kandji.

        Args:
            name (str): The name for the new app
            file (Path | BufferedReader): The app file to upload (Path object or open BufferedReader)
            install_type (InstallType): The installation type
            install_enforcement (InstallEnforcement): The enforcement type for installation
            audit_script (str): Script to audit app installation (only with 'continuously_enforce')
            preinstall_script (str): Script to run before installation
            postinstall_script (str): Script to run after installation
            restart (bool): Whether to restart after installation
            active (bool): Whether the app is active
            show_in_self_service (bool, optional): Whether to show in self service
            self_service_category_id (str, optional): Category ID for self service
            self_service_recommended (bool, optional): Whether recommended in self service
            unzip_location (str, optional): Location to unzip (required for 'zip' install_type)

        Returns:
            CustomAppPayload: A parsed object from the response

        Raises:
            ValueError: Raised when invalid parameters are passed
            ApiClientError: Raised if a ApiClient has not been opened
            HTTPError: Raised when the HTTP request returns an unsuccessful status code
            ConnectionError: Raised when the API connection fails
            ValidationError: Raised when the response does not match the expected schema

        """
        if audit_script and install_enforcement != InstallEnforcement.CONTINUOUSLY_ENFORCE:
            raise ValueError("audit_script can only be used with install_enforcement 'continuously_enforce'")
        if install_type == InstallType.ZIP and unzip_location is None:
            raise ValueError("unzip_location must be provided when install_type is 'zip'")

        if show_in_self_service:
            if self_service_category_id is None:
                raise ValueError(
                    f"self_service_category_id is required if show_in_self_service is True.\n\n{SHOW_IN_SELF_SERVICE_EXAMPLE}"
                )

        file_key = self._upload_file(file)

        payload = {
            "name": name,
            "file_key": file_key,
            "install_type": str(install_type),
            "install_enforcement": str(install_enforcement),
            "audit_script": audit_script,
            "preinstall_script": preinstall_script,
            "postinstall_script": postinstall_script,
            "restart": restart,
            "active": active,
            "show_in_self_service": show_in_self_service,
            "self_service_category_id": self_service_category_id,
            "self_service_recommended": self_service_recommended,
            "unzip_location": unzip_location,
        }

        payload = {
            k: v for k, v in payload.items() if v is not None
        }  # Retry logic for create API call when file is still being processed
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                response = self.client.post(self._path, data=payload)
                return CustomAppPayload.model_validate_json(response.content)
            except requests.HTTPError as e:
                if e.response.status_code == 503 and "The upload is still being processed." in e.response.text:
                    if attempt < max_attempts - 1:
                        console.warning(
                            f"Upload still being processed, retrying (attempt {attempt + 2}/{max_attempts})..."
                        )
                        sleep(2**attempt)
                        continue
                raise

        raise ApiClientError(f"Failed to create custom app after {max_attempts} attempts.")

    def update(
        self,
        id: str,
        name: str | None = None,
        file: Path | BufferedReader | None = None,
        install_type: InstallType | None = None,
        install_enforcement: InstallEnforcement | None = None,
        audit_script: str | None = None,
        preinstall_script: str | None = None,
        postinstall_script: str | None = None,
        restart: bool | None = None,
        active: bool | None = None,
        show_in_self_service: bool | None = False,
        self_service_category_id: str | None = None,
        self_service_recommended: bool | None = None,
        unzip_location: str | None = None,
    ) -> CustomAppPayload:
        """Update an existing custom app in Kandji.

        Args:
            id (str): The library item id of the app to update
            name (str, optional): The name for the app
            file_key (str, optional): The S3 file key for the uploaded app file
            install_type (InstallType, optional): The installation type
            install_enforcement (InstallEnforcement, optional): The enforcement type for installation
            audit_script (str, optional): Script to audit app installation (only with 'continuously_enforce')
            preinstall_script (str, optional): Script to run before installation
            postinstall_script (str, optional): Script to run after installation
            restart (bool, optional): Whether to restart after installation
            active (bool, optional): Whether the app is active
            show_in_self_service (bool, optional): Whether to show in self service
            self_service_category_id (str, optional): Category ID for self service
            self_service_recommended (bool, optional): Whether recommended in self service
            unzip_location (str, optional): Location to unzip (required for 'zip' install_type)

        Returns:
            CustomAppPayload: A parsed object from the response

        Raises:
            ValueError: Raised when invalid parameters are passed
            ApiClientError: Raised if a ApiClient has not been opened
            HTTPError: Raised when the HTTP request returns an unsuccessful status code
            ConnectionError: Raised when the API connection fails
            ValidationError: Raised when the response does not match the expected schema

        """

        if audit_script and install_enforcement != InstallEnforcement.CONTINUOUSLY_ENFORCE:
            raise ValueError("audit_script can only be used with install_enforcement 'continuously_enforce'")
        if install_type == InstallType.ZIP and unzip_location is None:
            raise ValueError("unzip_location must be provided when install_type is 'zip'")

        if show_in_self_service:
            if self_service_category_id is None:
                raise ValueError(
                    f"self_service_category_id is required if show_in_self_service is True.\n\n{SHOW_IN_SELF_SERVICE_EXAMPLE}"
                )

        file_key = None
        if file:
            file_key = self._upload_file(file)

        payload = {
            "name": name,
            "file_key": file_key,
            "install_type": None if install_type is None else str(install_type),
            "install_enforcement": None if install_enforcement is None else str(install_enforcement),
            "audit_script": audit_script,
            "preinstall_script": preinstall_script,
            "postinstall_script": postinstall_script,
            "restart": restart,
            "active": active,
            "show_in_self_service": show_in_self_service,
            "self_service_category_id": self_service_category_id,
            "self_service_recommended": self_service_recommended,
            "unzip_location": unzip_location,
        }

        payload = {k: v for k, v in payload.items() if v is not None}

        # Retry logic for update API call when file is still being processed
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                response = self.client.patch(f"{self._path}/{id}", data=payload)
                return CustomAppPayload.model_validate_json(response.content)
            except requests.HTTPError as e:
                if e.response.status_code == 503 and "The upload is still being processed." in e.response.text:
                    if attempt < max_attempts - 1:
                        console.warning(
                            f"Upload still being processed, retrying (attempt {attempt + 2}/{max_attempts})..."
                        )
                        sleep(2**attempt)
                        continue

        raise ApiClientError(f"Failed to update custom app after {max_attempts} attempts.")

    def delete(self, id: str) -> None:
        """Delete an existing custom app in Kandji.

        Args:
            id (str): The library item id of the app to delete

        Raises:
            ApiClientError: Raised if a ApiClient has not been opened
            HTTPError: Raised when the HTTP request returns an unsuccessful status code
            ConnectionError: Raised when the API connection fails

        """

        self.client.delete(f"{self._path}/{id}")
