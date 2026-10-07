# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import logging
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import backoff
import pytest

from superset.utils.retries import retry_call


@pytest.fixture(autouse=True)
def mock_sleep() -> Iterator[MagicMock]:
    with patch("backoff._sync.time.sleep") as mocked:
        yield mocked


def _mock_func(**kwargs: Any) -> MagicMock:
    # backoff's log handlers read ``target.__name__``
    func = MagicMock(**kwargs)
    func.__name__ = "func"
    return func


def _failing(times: int, exc: Exception, result: Any = "ok") -> MagicMock:
    return _mock_func(side_effect=[exc] * times + [result])


def test_retry_call_succeeds_on_first_call(mock_sleep: MagicMock) -> None:
    func = _mock_func(return_value="ok")

    assert retry_call(func, max_tries=3) == "ok"
    assert func.call_count == 1
    mock_sleep.assert_not_called()


def test_retry_call_retries_until_success(mock_sleep: MagicMock) -> None:
    func = _failing(2, ValueError("boom"))

    assert retry_call(func, exception=ValueError, max_tries=5) == "ok"
    assert func.call_count == 3
    assert mock_sleep.call_count == 2


def test_retry_call_gives_up_after_max_tries(mock_sleep: MagicMock) -> None:
    func = _mock_func(side_effect=ValueError("boom"))

    with pytest.raises(ValueError, match="boom"):
        retry_call(func, exception=ValueError, max_tries=3)

    assert func.call_count == 3
    assert mock_sleep.call_count == 2


def test_retry_call_does_not_retry_other_exceptions(mock_sleep: MagicMock) -> None:
    func = _mock_func(side_effect=KeyError("nope"))

    with pytest.raises(KeyError):
        retry_call(func, exception=ValueError, max_tries=5)

    assert func.call_count == 1
    mock_sleep.assert_not_called()


def test_retry_call_retries_subclasses_of_configured_exception() -> None:
    class CustomError(ValueError):
        pass

    func = _failing(1, CustomError("boom"))

    assert retry_call(func, exception=ValueError, max_tries=3) == "ok"
    assert func.call_count == 2


def test_retry_call_passes_fargs_and_fkwargs() -> None:
    func = _failing(1, ValueError("boom"))

    retry_call(
        func,
        exception=ValueError,
        max_tries=3,
        fargs=[1, 2],
        fkwargs={"a": "b"},
    )

    assert func.call_count == 2
    for call in func.call_args_list:
        assert call.args == (1, 2)
        assert call.kwargs == {"a": "b"}


def test_retry_call_defaults_to_no_args() -> None:
    func = _mock_func(return_value="ok")

    retry_call(func)

    func.assert_called_once_with()


def test_retry_call_uses_strategy_and_its_kwargs(mock_sleep: MagicMock) -> None:
    func = _failing(2, ValueError("boom"))

    retry_call(
        func,
        strategy=backoff.constant,
        exception=ValueError,
        max_tries=5,
        interval=7,
        jitter=None,
    )

    assert [call.args[0] for call in mock_sleep.call_args_list] == [7, 7]


def test_retry_call_logs_giveup_at_configured_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    func = _mock_func(side_effect=ValueError("boom"))

    with caplog.at_level(logging.DEBUG, logger="backoff"):
        with pytest.raises(ValueError, match="boom"):
            retry_call(
                func,
                exception=ValueError,
                max_tries=2,
                giveup_log_level=logging.INFO,
            )

    giveup_records = [r for r in caplog.records if "Giving up" in r.getMessage()]
    assert len(giveup_records) == 1
    assert giveup_records[0].levelno == logging.INFO
