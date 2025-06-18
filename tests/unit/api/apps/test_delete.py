def test_delete_successful(monkeypatch, response_factory, custom_apps_resource):
    def mock_delete_request(self, url):
        assert url.endswith("existing-app-id")
        return response_factory(204, {})

    monkeypatch.setattr("kst.api.client.ApiClient.delete", mock_delete_request)
    custom_apps_resource.delete("existing-app-id")
