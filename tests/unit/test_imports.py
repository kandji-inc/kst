from itertools import chain


def test_api_imports():
    import kst.api

    expected_imports = {
        "ApiClient",
        "ApiConfig",
        "ApiPayloadType",
        "CustomProfilePayload",
        "CustomProfilesResource",
        "CustomScriptPayload",
        "CustomScriptsResource",
        "ExecutionFrequency",
        "PayloadList",
        "SelfServiceCategoriesResource",
        "SelfServiceCategoryPayload",
    }

    for import_name in expected_imports:
        assert hasattr(kst.api, import_name)

    assert set(kst.api.__all__) == expected_imports


def test_model_imports():
    import kst.repository

    common_imports = {
        "ACCEPTED_INFO_EXTENSIONS",
        "File",
        "InfoFile",
        "InfoFormat",
        "MemberBase",
        "Repository",
        "RepositoryDirectory",
        "SUFFIX_MAP",
    }

    profile_imports = {
        "CustomProfile",
        "Mobileconfig",
        "PROFILE_INFO_HASH_KEYS",
        "PROFILE_RUNS_ON_PARAMS",
        "ProfileInfoFile",
    }

    script_imports = {
        "CustomScript",
        "DEFAULT_SCRIPT_SUFFIX",
        "DEFAULT_SCRIPT_CATEGORY",
        "DEFAULT_SCRIPT_CONTENT",
        "ExecutionFrequency",
        "SCRIPT_INFO_HASH_KEYS",
        "Script",
        "ScriptInfoFile",
    }

    for import_name in chain(common_imports, profile_imports, script_imports):
        assert hasattr(kst.repository, import_name)

    assert set(kst.repository.__all__) == common_imports | profile_imports | script_imports
