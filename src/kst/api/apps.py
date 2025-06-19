from io import BufferedReader
from pathlib import Path

from .payload import CustomAppPayload, CustomAppUploadPayload, PayloadList
from .resource_base import ResourceBase


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
        upload: Get S3 upload details for a custom app
        upload_to_s3: Upload a file to S3 using presigned URL

    """

    _path = "/api/v1/library/custom-apps"

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
        file_key: str,
        install_type: str,
        install_enforcement: str,
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
            file_key (str): The S3 file key for the uploaded app file
            install_type (str): The installation type ('package', 'zip', or 'image')
            install_enforcement (str): The enforcement type for installation
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
        if audit_script and not install_enforcement == "continuously_enforce":
            raise ValueError("audit_script can only be used with install_enforcement 'continuously_enforce'")
        if install_type == "zip" and unzip_location is None:
            raise ValueError("unzip_location must be provided when install_type is 'zip'")
        if install_type not in ["package", "zip", "image"]:
            raise ValueError("install_type must be one of 'package', 'zip', or 'image'")

        payload = {
            "name": name,
            "file_key": file_key,
            "install_type": install_type,
            "install_enforcement": install_enforcement,
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
        response = self.client.post(self._path, data=payload)
        return CustomAppPayload.model_validate_json(response.content)

    def update(
        self,
        id: str,
        name: str | None = None,
        install_type: str | None = None,
        install_enforcement: str | None = None,
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
            install_type (str, optional): The installation type ('package', 'zip', or 'image')
            install_enforcement (str, optional): The enforcement type for installation
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

        if audit_script and not install_enforcement == "continuously_enforce":
            raise ValueError("audit_script can only be used with install_enforcement 'continuously_enforce'")
        if install_type == "zip" and unzip_location is None:
            raise ValueError("unzip_location must be provided when install_type is 'zip'")
        if install_type not in ["package", "zip", "image", None]:
            raise ValueError("install_type must be one of 'package', 'zip', or 'image'")

        payload = {
            "name": name,
            "install_type": install_type,
            "install_enforcement": install_enforcement,
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
        response = self.client.patch(f"{self._path}/{id}", data=payload)
        return CustomAppPayload.model_validate_json(response.content)

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

    def upload(self, name: str) -> CustomAppUploadPayload:
        """Retrieve the S3 upload details needed for uploading the app using upload_to_s3.

        Args:
            name (str): The filename for the app to upload

        Returns:
            CustomAppUploadPayload: A parsed object containing S3 upload details

        Raises:
            ApiClientError: Raised if a ApiClient has not been opened
            HTTPError: Raised when the HTTP request returns an unsuccessful status code
            ConnectionError: Raised when the API connection fails
            ValidationError: Raised when the response does not match the expected schema

        """
        payload = {"name": name}
        response = self.client.post(f"{self._path}/upload", data=payload)
        return CustomAppUploadPayload.model_validate_json(response.content)

    def upload_to_s3(
        self,
        file: Path | BufferedReader,
        post_url: str,
        post_data: dict[str, str],
    ) -> bool:
        """Upload a file to S3 using presigned URL and post data provided by the upload method.

        Args:
            file (Path | BufferedReader): File to upload (Path object or open BufferedReader)
            post_url (str): The S3 presigned POST URL
            post_data (dict[str, str]): The POST data for S3 upload

        Returns:
            bool: True if upload was successful

        Raises:
            FileNotFoundError: Raised when the file does not exist or is not readable
            ValueError: Raised when invalid file type is provided
            ConnectionError: Raised when S3 upload fails

        """

        if isinstance(file, Path):
            if not file.is_file():
                raise FileNotFoundError(f"The file {file} does not exist or is not readable")
            file_obj = file.open("rb")
            file_name = file.name
        elif isinstance(file, BufferedReader):
            file_obj = file
            file_name = file.name
        else:
            raise ValueError("Invalid file type provided. Must be a Path or BufferedReader object.")
        files = [("file", (file_name, file_obj, "application/octet-stream"))]

        response = self.s3_client.post(post_url, data=post_data, files=files)
        if response.status_code != 204:
            raise ConnectionError(f"Failed to upload file to S3: {response.text}")
        return True
