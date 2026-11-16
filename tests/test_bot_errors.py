"""The Telegram error handler: transient network errors log one WARNING line."""

import logging
from types import SimpleNamespace

from telegram.error import NetworkError

from nunzio.bot import NunzioBot


async def test_network_error_is_one_warning_without_traceback(caplog):
    with caplog.at_level(logging.WARNING, logger="nunzio.bot"):
        await NunzioBot._on_error(None, SimpleNamespace(error=NetworkError("Bad Gateway")))
    (record,) = caplog.records
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert "Bad Gateway" in record.getMessage()


async def test_other_errors_keep_their_traceback(caplog):
    with caplog.at_level(logging.WARNING, logger="nunzio.bot"):
        await NunzioBot._on_error(None, SimpleNamespace(error=ValueError("boom")))
    (record,) = caplog.records
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None
