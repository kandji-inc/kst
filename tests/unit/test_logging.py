import logging
from logging.handlers import RotatingFileHandler

import platformdirs

from kst.__about__ import APP_NAME
from kst.cli import main


def test_logging_setup(monkeypatch, caplog):
    """Ensure that basicconfig is called with the correct parameters after main is executed."""

    def mock_basicconfig(**kwargs):
        assert kwargs["level"] == logging.INFO
        assert kwargs["format"] == "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        assert len(kwargs["handlers"]) == 1
        assert isinstance(kwargs["handlers"][0], RotatingFileHandler)
        assert kwargs["handlers"][0].baseFilename == str(
            platformdirs.user_log_path(appname=APP_NAME) / f"{APP_NAME}.log"
        )
        assert kwargs["handlers"][0].maxBytes == 1024 * 5000
        assert kwargs["handlers"][0].backupCount == 3

    monkeypatch.setattr(logging, "basicConfig", mock_basicconfig)
    with caplog.at_level(logging.DEBUG):
        main()
    assert "--- Starting Kandji Sync Toolkit ---" in caplog.text
