from __future__ import annotations

from unittest.mock import Mock

import pytest
from milpbooklm_workers.loop import WorkerLoop


def _loop(close: Mock) -> WorkerLoop:
    return WorkerLoop(
        repo=Mock(),
        handlers={},
        policy=Mock(),
        worker_id="lifecycle-test",
        capacity_classes=(),
        lease_seconds=10,
        poll_seconds=0,
        complete=Mock(),
        recover=Mock(return_value=()),
        cancel=Mock(),
        teardown=(close,),
    )


def test_worker_closes_execution_stack_after_stop() -> None:
    close = Mock()
    loop = _loop(close)
    loop.request_stop()

    loop.run_forever()

    close.assert_called_once_with()


def test_worker_closes_execution_stack_after_poll_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    close = Mock()
    loop = _loop(close)
    failure = RuntimeError("poll failed")
    monkeypatch.setattr(loop, "_poll_once", Mock(side_effect=failure))

    with pytest.raises(RuntimeError, match="poll failed"):
        loop.run_forever()

    close.assert_called_once_with()
