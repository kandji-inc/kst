from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

ApiPayloadType = TypeVar("ApiPayloadType", "CustomProfilePayload", "CustomScriptPayload", "CustomAppPayload")


class CustomProfilePayload(BaseModel):
    """Payload model for custom profiles API endpoints."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("profile", mode="after")
    @classmethod
    def tabs_to_spaces(cls, v: str) -> str:
        return v.expandtabs(tabsize=4)

    id: Annotated[str, AfterValidator(lambda value: value.lower())]
    name: str
    active: bool
    profile: str
    mdm_identifier: str
    created_at: str
    updated_at: str
    runs_on_mac: bool = False
    runs_on_iphone: bool = False
    runs_on_ipad: bool = False
    runs_on_tv: bool = False
    runs_on_vision: bool = False
    runs_on_android: bool = False
    runs_on_windows: bool = False


class CustomScriptPayload(BaseModel):
    """Payload model for custom script API endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, AfterValidator(lambda value: value.lower())]
    name: str
    active: bool
    execution_frequency: str
    restart: bool
    script: str
    remediation_script: str
    created_at: str
    updated_at: str
    show_in_self_service: bool | None = False
    self_service_category_id: str | None = None
    self_service_recommended: bool | None = None


class CustomAppPayload(BaseModel):
    """Payload model for custom app library API endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, AfterValidator(lambda value: value.lower())]
    name: str
    sha256: str
    file_key: str
    file_url: str
    file_size: int
    file_updated: str
    install_type: str = Field(description="Installation type", pattern="^(package|zip|image)$")
    install_enforcement: str = Field(
        description="Install enforcement type", pattern="^(install_once|continuously_enforce|no_enforcement)$"
    )
    unzip_location: str | None = None
    restart: bool
    audit_script: str
    preinstall_script: str
    postinstall_script: str
    active: bool
    description: str | None = None
    version: str | None = None
    created_at: str
    updated_at: str
    show_in_self_service: bool | None = False
    self_service_category_id: str | None = None
    self_service_recommended: bool | None = None


class CustomAppUploadPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    expires: str
    post_url: str
    post_data: dict[str, str]
    file_key: str


class SelfServiceCategoryPayload(BaseModel):
    """Payload model for self-service categories API endpoints."""

    id: str
    name: str


class PayloadList(BaseModel, Generic[ApiPayloadType]):
    """Payload model for the syncable list endpoints."""

    count: int = 0
    next: str | None = None
    previous: str | None = None
    results: list[ApiPayloadType] = []
