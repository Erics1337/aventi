import runpy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/refresh-runtime.py"


@pytest.mark.parametrize(
    "environment", [None, {}, {"Error": {"ErrorCode": "KMSAccessDenied"}}, {"Variables": None}]
)
def test_runtime_refresh_never_overwrites_unreadable_environment(monkeypatch, environment):
    client = MagicMock()
    client.get_function_configuration.return_value = {
        "Environment": environment,
        "RevisionId": "revision",
    }
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: client)
    with pytest.raises(RuntimeError, match="refresh aborted"):
        runpy.run_path(str(SCRIPT))
    client.update_function_configuration.assert_not_called()


def test_runtime_refresh_preserves_existing_variables(monkeypatch):
    client = MagicMock()
    existing = {"RUNTIME_SECRET_NAME": "staging-secret", "SQS_WORKER_QUEUE_URL": "queue"}
    client.get_function_configuration.return_value = {
        "Environment": {"Variables": existing},
        "RevisionId": "revision",
    }
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: client)
    runpy.run_path(str(SCRIPT))
    assert client.update_function_configuration.call_count == 3
    for call in client.update_function_configuration.call_args_list:
        variables = call.kwargs["Environment"]["Variables"]
        assert all(variables[key] == value for key, value in existing.items())
        assert variables["AVENTI_CONFIG_REVISION"]
        assert call.kwargs["RevisionId"] == "revision"
