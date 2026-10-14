"""Provider adapters: demo behavior, live fail-closed, mocked SDK mapping."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.errors import NotFoundError, ProviderDisabledError, ValidationApiError
from app.providers.demo import DemoAdapter
from app.providers.registry import get_adapter


class TestDemoAdapter:
    def test_lists_all_resources(self):
        assert len(DemoAdapter().list_resources()) == 8

    def test_emulated_provider_filter(self):
        gcp = DemoAdapter(emulated_provider="gcp").list_resources()
        aws = DemoAdapter(emulated_provider="aws").list_resources()
        assert all(r.provider == "gcp" for r in gcp) and len(gcp) == 5
        assert all(r.provider == "aws" for r in aws) and len(aws) == 3

    def test_everything_labeled_simulated(self):
        assert all(r.simulated for r in DemoAdapter().list_resources())

    def test_resource_detail_includes_scenarios(self):
        detail = DemoAdapter().get_resource("web-frontend-1")
        assert "gcp-high-cpu" in detail.scenario_ids

    def test_unknown_resource_raises(self):
        with pytest.raises(NotFoundError):
            DemoAdapter().get_resource("ghost-vm")

    def test_cross_provider_resource_hidden(self):
        with pytest.raises(NotFoundError):
            DemoAdapter(emulated_provider="gcp").get_resource("i-0f1e2d3c4b5a69788")

    def test_unknown_metric_raises(self):
        end = datetime.now(UTC)
        with pytest.raises(ValidationApiError):
            DemoAdapter().get_metrics("web-frontend-1", "quantum_flux", end - timedelta(hours=1), end)


class TestRegistryFailClosed:
    def test_demo_disabled_blocks_demo_provider(self, monkeypatch):
        monkeypatch.setenv("CLOUDOPS_DEMO_MODE", "false")
        get_settings.cache_clear()
        with pytest.raises(ProviderDisabledError):
            get_adapter("demo")

    def test_gcp_disabled_and_no_demo_fails_closed(self, monkeypatch):
        monkeypatch.setenv("CLOUDOPS_DEMO_MODE", "false")
        monkeypatch.setenv("CLOUDOPS_GCP_ENABLED", "false")
        get_settings.cache_clear()
        with pytest.raises(ProviderDisabledError):
            get_adapter("gcp")

    def test_gcp_enabled_without_allowlist_fails_closed(self, monkeypatch):
        monkeypatch.setenv("CLOUDOPS_GCP_ENABLED", "true")
        monkeypatch.setenv("CLOUDOPS_GCP_ALLOWED_PROJECTS", "")
        get_settings.cache_clear()
        with pytest.raises(ProviderDisabledError):
            get_adapter("gcp")

    def test_gcp_project_not_in_allowlist_rejected(self, monkeypatch):
        monkeypatch.setenv("CLOUDOPS_GCP_ENABLED", "true")
        monkeypatch.setenv("CLOUDOPS_GCP_ALLOWED_PROJECTS", "allowed-project")
        get_settings.cache_clear()
        with pytest.raises(ProviderDisabledError):
            get_adapter("gcp", account="other-project")

    def test_demo_mode_emulates_gcp(self):
        adapter = get_adapter("gcp")
        assert isinstance(adapter, DemoAdapter) and adapter.simulated

    def test_unknown_provider_rejected(self):
        with pytest.raises(ValidationApiError):
            get_adapter("azure")


class TestGcpAdapterMocked:
    def _make_adapter(self, monkeypatch):
        monkeypatch.setenv("CLOUDOPS_GCP_ENABLED", "true")
        monkeypatch.setenv("CLOUDOPS_GCP_ALLOWED_PROJECTS", "proj-1")
        get_settings.cache_clear()
        from app.providers.gcp import GcpAdapter

        return GcpAdapter("proj-1")

    def test_instance_mapping_via_mocked_client(self, monkeypatch):
        adapter = self._make_adapter(monkeypatch)
        inst = SimpleNamespace(
            name="vm-1",
            status="RUNNING",
            machine_type="zones/us-central1-a/machineTypes/e2-small",
            creation_timestamp="2026-01-01T00:00:00+00:00",
            labels={"env": "prod"},
            network_interfaces=[
                SimpleNamespace(network_i_p="10.0.0.5", access_configs=[SimpleNamespace(nat_i_p="34.1.2.3")])
            ],
        )
        scoped = SimpleNamespace(instances=[inst])
        mock_client = MagicMock()
        mock_client.aggregated_list.return_value = [("zones/us-central1-a", scoped)]
        with patch.object(adapter, "_compute_client", return_value=mock_client):
            resources = adapter.list_resources()
        assert len(resources) == 1
        r = resources[0]
        assert r.id == "vm-1" and r.status == "running" and r.machine_type == "e2-small"
        assert r.internal_ip == "10.0.0.5" and r.external_ip == "34.1.2.3"
        assert r.zone == "us-central1-a" and r.simulated is False

    def test_unknown_metric_rejected(self, monkeypatch):
        adapter = self._make_adapter(monkeypatch)
        end = datetime.now(UTC)
        with pytest.raises(ValidationApiError):
            adapter.get_metrics("vm-1", "http_5xx_count", end - timedelta(hours=1), end)

    def test_get_resource_not_found(self, monkeypatch):
        adapter = self._make_adapter(monkeypatch)
        mock_client = MagicMock()
        mock_client.aggregated_list.return_value = []
        with patch.object(adapter, "_compute_client", return_value=mock_client):
            with pytest.raises(NotFoundError):
                adapter.get_resource("ghost")


class TestAwsAdapterMocked:
    def _make_adapter(self, monkeypatch, account="123456789012"):
        monkeypatch.setenv("CLOUDOPS_AWS_ENABLED", "true")
        monkeypatch.setenv("CLOUDOPS_AWS_ALLOWED_ACCOUNTS", "123456789012")
        get_settings.cache_clear()
        from app.providers.aws import AwsAdapter

        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": account}
        clients = {"sts": sts, "ec2": MagicMock(), "cloudwatch": MagicMock(), "logs": MagicMock()}
        with patch.object(AwsAdapter, "_build_session", return_value=MagicMock()):
            with patch.object(AwsAdapter, "_client", side_effect=lambda s: clients[s]):
                adapter = AwsAdapter()
        return adapter, clients

    def test_account_not_allowlisted_fails_closed(self, monkeypatch):
        with pytest.raises(ProviderDisabledError):
            self._make_adapter(monkeypatch, account="999999999999")

    def test_describe_instances_pagination_and_mapping(self, monkeypatch):
        adapter, clients = self._make_adapter(monkeypatch)
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-abc123",
                                "InstanceType": "t3.micro",
                                "State": {"Name": "running"},
                                "Placement": {"AvailabilityZone": "us-east-1a"},
                                "PrivateIpAddress": "172.31.0.5",
                                "LaunchTime": datetime(2026, 1, 1, tzinfo=UTC),
                                "Tags": [{"Key": "Name", "Value": "worker"}],
                            }
                        ]
                    }
                ]
            }
        ]
        clients["ec2"].get_paginator.return_value = paginator
        with patch.object(adapter, "_client", side_effect=lambda s: clients[s]):
            resources = adapter.list_resources()
        assert len(resources) == 1
        r = resources[0]
        assert r.id == "i-abc123" and r.name == "worker" and r.zone == "us-east-1a"

    def test_metric_statistics_sorted(self, monkeypatch):
        adapter, clients = self._make_adapter(monkeypatch)
        t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        clients["cloudwatch"].get_metric_statistics.return_value = {
            "Datapoints": [
                {"Timestamp": t0 + timedelta(minutes=5), "Average": 50.0},
                {"Timestamp": t0, "Average": 10.0},
            ]
        }
        with patch.object(adapter, "_client", side_effect=lambda s: clients[s]):
            points, unit = adapter.get_metrics("i-abc", "cpu_utilization", t0, t0 + timedelta(hours=1))
        assert unit == "percent"
        assert [p.value for p in points] == [10.0, 50.0], "points must be time-sorted"

    def test_unknown_metric_rejected(self, monkeypatch):
        adapter, _ = self._make_adapter(monkeypatch)
        end = datetime.now(UTC)
        with pytest.raises(ValidationApiError):
            adapter.get_metrics("i-abc", "http_request_count", end - timedelta(hours=1), end)
