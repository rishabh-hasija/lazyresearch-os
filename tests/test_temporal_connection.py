"""Connection configuration, SDK forwarding and sanitized deployment probes."""

import asyncio
import traceback
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.health import check_temporal
from lazyresearch.infrastructure.workflows import connection, health
from scripts import smoke_temporal

BASE = {"DATABASE_URL": "postgresql://unused/tests"}
SECRET = "fake-temporal-secret"
CLOUD = {
    **BASE,
    "TEMPORAL_ADDRESS": "namespace.account.tmprl.cloud:7233",
    "TEMPORAL_NAMESPACE": "namespace.account",
    "TEMPORAL_API_KEY": SECRET,
}


def test_local_unauthenticated_and_web_without_temporal():
    local = Settings.from_env({**BASE, "TEMPORAL_ADDRESS": "127.0.0.1:7233"})
    assert local.temporal_namespace == "default"
    assert not local.temporal_api_key and not local.temporal_tls_enabled
    web = Settings.from_env(BASE)
    assert not web.temporal_address
    with pytest.raises(ValueError, match="TEMPORAL_ADDRESS"):
        asyncio.run(connection.connect_temporal(web))


@pytest.mark.parametrize("tls", [None, "true"])
def test_cloud_config_and_redaction(tls):
    values = dict(CLOUD)
    if tls:
        values["TEMPORAL_TLS"] = tls
    settings = Settings.from_env(values)
    assert settings.temporal_cloud and settings.temporal_tls_enabled
    assert settings.temporal_api_key == SECRET
    assert SECRET not in repr(settings)


@pytest.mark.parametrize(
    "address",
    [
        "namespace.account.tmprl.cloud:7233",
        "eu-west-1.aws.api.temporal.io:7233",
        "NAMESPACE.ACCOUNT.TMPRL.CLOUD.:7233",
    ],
)
def test_cloud_endpoints_require_api_key(address):
    with pytest.raises(ValueError, match="TEMPORAL_API_KEY"):
        Settings.from_env({**BASE, "TEMPORAL_ADDRESS": address})


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"TEMPORAL_API_KEY": SECRET}, "TEMPORAL_ADDRESS"),
        ({"TEMPORAL_TLS": "true"}, "TEMPORAL_ADDRESS"),
        ({"TEMPORAL_TLS": SECRET}, "TEMPORAL_TLS"),
        ({"TEMPORAL_ADDRESS": "https://host:7233"}, "TEMPORAL_ADDRESS"),
        ({"TEMPORAL_ADDRESS": "host"}, "TEMPORAL_ADDRESS"),
        ({"TEMPORAL_ADDRESS": "host:0"}, "TEMPORAL_ADDRESS"),
        ({"TEMPORAL_ADDRESS": "host:99999"}, "TEMPORAL_ADDRESS"),
        ({"TEMPORAL_ADDRESS": "host:7233/path"}, "TEMPORAL_ADDRESS"),
        ({"TEMPORAL_ADDRESS": "host:7233?key=" + SECRET}, "TEMPORAL_ADDRESS"),
        ({"TEMPORAL_ADDRESS": SECRET + "@host:7233"}, "TEMPORAL_ADDRESS"),
        ({"TEMPORAL_ADDRESS": "[invalid"}, "TEMPORAL_ADDRESS"),
        ({"TEMPORAL_ADDRESS": "host:7233", "TEMPORAL_NAMESPACE": ""}, "TEMPORAL_NAMESPACE"),
        ({"TEMPORAL_ADDRESS": "host:7233", "TEMPORAL_TASK_QUEUE": ""}, "TEMPORAL_TASK_QUEUE"),
        (
            {"TEMPORAL_ADDRESS": "host:7233", "TEMPORAL_API_KEY": SECRET, "TEMPORAL_TLS": "false"},
            "TEMPORAL_TLS",
        ),
    ],
)
def test_invalid_config_is_sanitized(overrides, message):
    with pytest.raises(ValueError, match=message) as caught:
        Settings.from_env({**BASE, **overrides})
    assert SECRET not in str(caught.value)


def test_cloud_requires_namespace_and_tls():
    with pytest.raises(ValueError, match="TEMPORAL_NAMESPACE"):
        Settings.from_env({**CLOUD, "TEMPORAL_NAMESPACE": "default"})
    with pytest.raises(ValueError, match="TEMPORAL_TLS"):
        Settings.from_env({**CLOUD, "TEMPORAL_TLS": "false"})


@pytest.mark.parametrize("cloud", [False, True])
def test_sdk_connection_receives_settings(monkeypatch, cloud):
    values = CLOUD if cloud else {**BASE, "TEMPORAL_ADDRESS": "localhost:7233"}
    settings = Settings.from_env(values)
    connect = AsyncMock()
    monkeypatch.setattr(connection.Client, "connect", connect)
    assert asyncio.run(connection.connect_temporal(settings)) is connect.return_value
    connect.assert_awaited_once_with(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        api_key=SECRET if cloud else None,
        tls=cloud,
    )


def test_tls_self_hosted_without_key():
    settings = Settings.from_env(
        {
            **BASE,
            "TEMPORAL_ADDRESS": "private.example:7233",
            "TEMPORAL_TLS": "true",
        }
    )
    assert settings.temporal_tls_enabled and not settings.temporal_api_key


@pytest.mark.parametrize("stage", ["connect", "namespace"])
def test_sdk_errors_never_escape_in_messages_logs_or_tracebacks(monkeypatch, capsys, caplog, stage):
    settings = Settings.from_env(CLOUD)
    connect = AsyncMock()
    if stage == "connect":
        connect.side_effect = RuntimeError(SECRET)
    else:
        connect.return_value.workflow_service.describe_namespace.side_effect = RuntimeError(SECRET)
    monkeypatch.setattr(connection.Client, "connect", connect)
    with pytest.raises(connection.TemporalConnectionError) as caught:
        asyncio.run(connection.verify_temporal(settings))
    assert SECRET not in "".join(traceback.format_exception(caught.value))
    assert SECRET not in repr(caught.value)
    assert SECRET not in capsys.readouterr().out + caplog.text


def test_probe_checks_configured_namespace(monkeypatch):
    connect = AsyncMock()
    monkeypatch.setattr(connection.Client, "connect", connect)
    settings = Settings.from_env(CLOUD)
    assert health.research_service_available(settings)
    request = connect.return_value.workflow_service.describe_namespace.call_args.args[0]
    assert request.namespace == settings.temporal_namespace
    status = check_temporal(settings)
    assert status.ok and "worker activity not verified" in status.detail


def test_unconfigured_probe_never_connects(monkeypatch):
    connect = AsyncMock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(connection.Client, "connect", connect)
    status = check_temporal(Settings.from_env(BASE))
    assert not status.ok and "Not checked" in status.detail
    connect.assert_not_called()


def test_probe_failure_sanitized_and_bounded(monkeypatch):
    settings = Settings.from_env(CLOUD)
    probe = AsyncMock(side_effect=TimeoutError(SECRET))
    monkeypatch.setattr(health, "verify_temporal", probe)
    status = check_temporal(settings)
    assert not status.ok and SECRET not in status.detail
    assert "PostgreSQL" in status.detail


def test_direct_settings_cannot_disable_tls_with_key():
    with pytest.raises(ValueError, match="TEMPORAL_TLS"):
        replace(Settings.from_env(CLOUD), temporal_tls=False)


def test_smoke_explicit_env_file_and_environment_precedence(monkeypatch, tmp_path, capsys):
    for key in CLOUD:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("TEMPORAL_TLS", raising=False)
    env_file = tmp_path / "cloud.env"
    env_file.write_text(
        "TEMPORAL_ADDRESS=namespace.account.tmprl.cloud:7233\n"
        "TEMPORAL_NAMESPACE=namespace.account\n"
        "TEMPORAL_API_KEY='" + SECRET + "'\n"
        "TEMPORAL_TLS=true\n"
    )
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "override.account")
    monkeypatch.setattr("sys.argv", ["smoke_temporal", "--env-file", str(env_file)])
    verify = AsyncMock()
    monkeypatch.setattr(smoke_temporal, "verify_temporal", verify)
    assert smoke_temporal.main() == 0
    settings = verify.call_args.args[0]
    assert settings.temporal_api_key == SECRET and settings.temporal_tls_enabled
    assert settings.temporal_namespace == "override.account"
    assert SECRET not in capsys.readouterr().out


def test_smoke_does_not_implicitly_load_env(monkeypatch, capsys):
    for key in CLOUD:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("TEMPORAL_TLS", raising=False)
    monkeypatch.setattr("sys.argv", ["smoke_temporal"])
    load = AsyncMock(side_effect=AssertionError("must not load"))
    monkeypatch.setattr(smoke_temporal, "load_dotenv", load)
    assert smoke_temporal.main() == 1
    load.assert_not_called()
    assert SECRET not in capsys.readouterr().out
