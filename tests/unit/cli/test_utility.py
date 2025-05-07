import logging
import re
from contextlib import chdir, nullcontext

import pytest
import typer

from kst.cli.utility import api_config_prompt, validate_output_path, validate_repo_path
from kst.repository import RepositoryDirectory

repo_dir_name = "repo"


@pytest.mark.parametrize(
    ("tenant_url", "api_token", "interactive", "input_url", "input_token", "expectation", "log_out"),
    [
        pytest.param(
            "https://test.api.kandji.io",
            "00000000-0000-0000-0000-000000000000",
            True,
            None,
            None,
            nullcontext(("https://test.api.kandji.io", "00000000-0000-0000-0000-000000000000")),
            "",
            id="https_with_token",
        ),
        pytest.param(
            "http://test.api.kandji.io",
            "00000000-0000-0000-0000-000000000000",
            True,
            None,
            None,
            nullcontext(("https://test.api.kandji.io", "00000000-0000-0000-0000-000000000000")),
            "",
            id="http_with_token",
        ),
        pytest.param(
            "test.api.kandji.io",
            "00000000-0000-0000-0000-000000000000",
            True,
            None,
            None,
            nullcontext(("https://test.api.kandji.io", "00000000-0000-0000-0000-000000000000")),
            "",
            id="no_scheme_with_token",
        ),
        pytest.param(
            "a" * 3000,  # greater than max length of HttpUrl
            "00000000-0000-0000-0000-000000000000",
            True,
            None,
            None,
            pytest.raises(typer.BadParameter),
            "The Tenant URL must be a valid Kandji API URL.",
            id="invalid_url_with_token",
        ),
        pytest.param(
            "https://test.api.kandji.io",
            "",
            True,
            None,
            None,
            pytest.raises(typer.BadParameter),
            "The API token must be a valid UUID4 string.",
            id="https_without_token",
        ),
        pytest.param(
            None,
            None,
            True,
            "https://test.api.kandji.io",
            "00000000-0000-0000-0000-000000000000",
            nullcontext(("https://test.api.kandji.io", "00000000-0000-0000-0000-000000000000")),
            "",
            id="prompt for both",
        ),
        pytest.param(
            "https://test.api.kandji.io",
            "00000000-0000-0000-0000-000000000000",
            False,
            None,
            None,
            nullcontext(("https://test.api.kandji.io", "00000000-0000-0000-0000-000000000000")),
            "",
            id="https_with_token_non_interactive",
        ),
        pytest.param(
            None,
            None,
            False,
            "https://test.api.kandji.io",
            "00000000-0000-0000-0000-000000000000",
            pytest.raises(typer.BadParameter),
            "You must provide a valid Kandji Tenant API URL.",
            id="no_url_non_interactive",
        ),
        pytest.param(
            "https://test.api.kandji.io",
            None,
            False,
            "https://test.api.kandji.io",
            None,
            pytest.raises(typer.BadParameter),
            "You must provide a valid Kandji API Token",
            id="no_token_non_interactive",
        ),
    ],
)
def test_api_config_prompt(
    monkeypatch,
    response_factory,
    caplog,
    tenant_url,
    api_token,
    interactive,
    input_url,
    input_token,
    expectation,
    log_out,
):
    user_prompted = False

    def fake_prompt(text, *args, **kwargs):
        nonlocal user_prompted
        user_prompted = True
        if "URL" in text:
            return input_url
        elif "Token" in text:
            return input_token
        else:
            pytest.fail("Unexpected prompt")

    def fake_requests_get(url, *args, **kwargs):
        if url == "https://test.api.kandji.io/app/v1/ping":
            return response_factory(200, b'"ping"')
        return response_factory(404, {"error": "tenantNotFound"})

    monkeypatch.setattr("typer.prompt", fake_prompt)
    monkeypatch.setattr("requests.get", fake_requests_get)
    with expectation as values:
        config = api_config_prompt(tenant_url, api_token, interactive=interactive)
        assert config.url == values[0]
        assert config.api_token == values[1]

    if not interactive:
        assert user_prompted is False
    assert log_out in caplog.text


def test_validate_repo_path(tmp_path_repo):
    # Test with no path and outside of repo
    with pytest.raises(typer.BadParameter):
        validate_repo_path()

    # Test with repo path passed from outside repo
    assert tmp_path_repo == validate_repo_path(tmp_path_repo)

    # Test validating subdirectory
    profiles_path = tmp_path_repo / "profiles/subdir/Test Profile"
    assert tmp_path_repo == validate_repo_path(profiles_path)
    assert tmp_path_repo / RepositoryDirectory.PROFILES == validate_repo_path(
        profiles_path, RepositoryDirectory.PROFILES
    )
    assert tmp_path_repo / RepositoryDirectory.SCRIPTS == validate_repo_path(profiles_path, RepositoryDirectory.SCRIPTS)

    # Test validating wrong subdirectory
    with pytest.raises(typer.BadParameter):
        validate_repo_path(profiles_path, RepositoryDirectory.SCRIPTS, validate_subdir=True)


@pytest.mark.parametrize(
    ("cd_path", "override_path", "expectation", "log_msg"),
    [
        pytest.param(
            ".",
            None,
            pytest.raises(typer.BadParameter),
            "An output path was not specified and the current directory has not been initialized as a Kandji Sync Toolkit",
            id="external without override exits",
        ),
        pytest.param(
            ".",
            "profile.mobileconfig",
            pytest.raises(typer.BadParameter),
            "The output path must be located inside a profiles directory of a valid kst repository.",
            id="external with invalid override exits",
        ),
        pytest.param(
            ".",
            f"{repo_dir_name}/profile.mobileconfig",
            pytest.raises(typer.BadParameter),
            "The output path must be located inside a profiles directory of a valid kst repository.",
            id="external with invalid internal override exits",
        ),
        pytest.param(
            ".",
            f"{repo_dir_name}/{RepositoryDirectory.PROFILES}/subdirectory",
            nullcontext(f"{repo_dir_name}/{RepositoryDirectory.PROFILES}/subdirectory"),
            "",
            id="external with valid override returns override",
        ),
        pytest.param(
            repo_dir_name,
            None,
            nullcontext(f"{repo_dir_name}/{RepositoryDirectory.PROFILES}"),
            "",
            id="internal without override returns profile root",
        ),
        pytest.param(
            repo_dir_name,
            "profile.mobileconfig",
            pytest.raises(typer.BadParameter),
            "",
            id="internal with invalid override exits",
        ),
    ],
)
@pytest.mark.usefixtures("tmp_path_repo")
def test_validate_output_path(caplog, tmp_path, cd_path, override_path, expectation, log_msg):
    "Test the resolved output path when the command is run within a repository."
    caplog.set_level(logging.DEBUG)
    with chdir(tmp_path / cd_path):
        with expectation as expected_path:
            output_path = validate_output_path(
                directory=RepositoryDirectory.PROFILES,
                override=str(tmp_path / override_path) if override_path else None,
            )
            assert output_path == tmp_path / expected_path
    assert re.search(log_msg, caplog.text)
