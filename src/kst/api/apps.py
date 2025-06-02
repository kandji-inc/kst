from io import BufferedReader
from pathlib import Path

from .payload import CustomAppPayload, CustomAppUploadPayload, PayloadList
from .resource_base import ResourceBase


class CustomAppsResource(ResourceBase):
    """An API client wrapper for interacting with the Custom Apps endpoint.
    Attributes:
        client (ApiClient): An ApiClient object with an open Session

        Methods:
    """

    _path = "/api/v1/library/custom-apps"

    def list(self) -> PayloadList[CustomAppPayload]:
        """"""

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
        """"""
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
        """
        Create a new custom app in Kandji
        """

        if install_type == "zip" and unzip_location is None:
            raise ValueError("unzip_location must be provided when install_type is 'zip'")

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
        name: str,
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
        """
        Update a custom app in Kandji
        """

        if install_type == "zip" and unzip_location is None:
            raise ValueError("unzip_location must be provided when install_type is 'zip'")

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
        """
        Delete a custom app in Kandji
        """

        self.client.delete(f"{self._path}/{id}")

    def upload(self, file: Path | BufferedReader):
        """
        Upload a custom app to Kandji
        """
        payload = {"name": (file.name)}
        response = self.client.post(f"{self._path}/upload", data=payload)
        return CustomAppUploadPayload.model_validate_json(response.content)

    def upload_to_s3(
        self,
        file: Path | BufferedReader,
        post_url: str,
        post_data: dict[str, str],
    ) -> bool:
        """"""

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

        self.s3_client.post(post_url, data=post_data, files=files)
        return True
