"""Usage normalization tests with synthetic counters, not measured defaults."""

import io
import json
from pathlib import Path
import urllib.error
from unittest.mock import Mock

import pytest

from tools.benchmark_invoice import (
    aggregate_runs, ContentUnderstanding, MODEL_ALIASES, resume_records, summarize_usage, write_snapshot,
)


def response(**overrides):
    usage = {
        "documentPagesStandard": 2, "contextualizationTokens": 2000,
        "tokens": {"gpt-4.1-input": 1000, "gpt-4.1-output": 200},
    }
    usage.update(overrides)
    return {"status": "Succeeded", "usage": usage}


def test_absent_cache_is_unknown_and_embedding_ledger_is_zero():
    run = summarize_usage(response(), "gpt-4.1")
    assert run["cached_input"] is None
    assert run["embeddings"] == 0
    assert aggregate_runs([run]) == {
        "input": 500, "cached_input": None, "output": 100,
        "contextualization": 1000, "embeddings": 0,
    }


def test_normalizes_all_token_categories_by_pages_without_double_counting_cache():
    run = summarize_usage(response(tokens={
        "gpt-4.1-input": 1000, "gpt-4.1-cached-input": 400,
        "gpt-4.1-output": 200, "text-embedding-3-large": 300,
    }), "gpt-4.1")
    assert aggregate_runs([run]) == {
        "input": 500, "cached_input": 200, "output": 100,
        "contextualization": 1000, "embeddings": 150,
    }


def test_aggregates_weighted_per_page_means_not_mean_of_run_means():
    first = summarize_usage(response(), "gpt-4.1")
    second = summarize_usage(response(
        documentPagesStandard=1, contextualizationTokens=1000,
        tokens={"gpt-4.1-input": 100, "gpt-4.1-output": 100},
    ), "gpt-4.1")
    assert aggregate_runs([first, second])["input"] == pytest.approx(1100 / 3)


@pytest.mark.parametrize("usage", [
    {"tokens": {}},
    {"documentPagesStandard": 0},
    {"contextualizationTokens": None},
    {"tokens": {"gpt-5-input": 100, "gpt-5-output": 10}},
    {"tokens": {"gpt-4.1-input": -1, "gpt-4.1-output": 10}},
    {"tokens": {"gpt-4.1-input": 100, "gpt-4.1-cached-input": 101, "gpt-4.1-output": 10}},
])
def test_rejects_missing_or_invalid_evidence(usage):
    with pytest.raises(ValueError):
        summarize_usage(response(**usage), "gpt-4.1")


def test_rejects_empty_aggregation():
    with pytest.raises(ValueError, match="At least one"):
        aggregate_runs([])


def test_never_sends_credentials_to_untrusted_polling_locations():
    client = ContentUnderstanding("https://example.cognitiveservices.azure.com", "synthetic-test-key")
    with pytest.raises(ValueError, match="Polling URL"):
        client.request("https://unrelated.example/analyzerResults/123")


def deployment_error(code="DeploymentIdNotFound"):
    return urllib.error.HTTPError(
        "https://example.cognitiveservices.azure.com", 400, "Bad Request", {},
        io.BytesIO(json.dumps({"error": {"innererror": {"code": code}}}).encode()),
    )


def test_retries_only_new_deployment_discovery_errors(monkeypatch):
    client = ContentUnderstanding("https://example.cognitiveservices.azure.com", "synthetic-test-key")
    client.request = Mock(side_effect=[
        deployment_error(), ({}, {"Operation-Location": client.endpoint + "/result"}),
        ({"status": "Succeeded"}, {}),
    ])
    sleep = Mock()
    monkeypatch.setattr("tools.benchmark_invoice.time.sleep", sleep)
    assert client.analyze("https://example.com/invoice.pdf", "completion", "embedding",
                          deployment_retry_seconds=180)["status"] == "Succeeded"
    sleep.assert_called_once_with(10)
    assert client.request.call_args_list[0].args[1]["modelDeployments"] == {
        "prebuilt-analyzer-completion": "completion",
        "prebuilt-analyzer-embedding": "embedding",
    }


@pytest.mark.parametrize("code,retry", [("DeploymentIdNotFound", 0), ("InvalidModel", 180)])
def test_propagation_retry_is_bounded_and_does_not_hide_other_errors(code, retry):
    client = ContentUnderstanding("https://example.cognitiveservices.azure.com", "synthetic-test-key")
    client.request = Mock(side_effect=deployment_error(code))
    with pytest.raises(RuntimeError, match=code):
        client.analyze("https://example.com/invoice.pdf", "completion", "embedding",
                       deployment_retry_seconds=retry)
    client.request.assert_called_once()


def test_persisted_defaults_match_complete_raw_usage_evidence():
    path = Path(__file__).resolve().parents[2] / "src" / "lib" / "invoice-token-defaults.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    assert len(snapshot["sampleSha256"]) == 64
    for name, record in snapshot["models"].items():
        if record["status"] != "measured":
            assert "perPage" not in record
            continue
        assert len(record["runs"]) == snapshot["runsPerModel"]
        assert record["apiVersion"] in ("2025-11-01", "2026-06-01-preview")
        assert record["region"] in ("eastus2", "southcentralus")
        normalized = [summarize_usage({"usage": run["usage"]}, record.get("modelName", name))
                      for run in record["runs"]]
        assert record["perPage"] == aggregate_runs(normalized)
        assert "reason" not in record


def test_omits_embedding_mapping_when_no_embedding_deployment_is_needed():
    client = ContentUnderstanding("https://example.cognitiveservices.azure.com", "synthetic-test-key",
                                  "2026-06-01-preview")
    client.request = Mock(side_effect=[
        ({}, {"Operation-Location": client.endpoint + "/result"}),
        ({"status": "Succeeded"}, {}),
    ])
    client.analyze("https://example.com/invoice.pdf", "gpt-5.6-terra", None)
    assert client.request.call_args_list[0].args[1]["modelDeployments"] == {
        "prebuilt-analyzer-completion": "gpt-5.6-terra",
    }


def test_tera_alias_uses_actual_terra_usage_counters():
    model_name = MODEL_ALIASES["gpt-5.6-tera"]
    run = summarize_usage(response(tokens={
        f"{model_name}-input": 1000, f"{model_name}-output": 100,
    }), model_name)
    assert (run["input"], run["output"]) == (1000, 100)
    with pytest.raises(ValueError, match="requested completion model"):
        summarize_usage(response(), model_name)


def test_resuming_preview_preserves_ga_provenance_and_existing_per_model_metadata():
    previous = {
        "sampleSha256": "sample", "runsPerModel": 3, "apiVersion": "2025-11-01",
        "region": "eastus2", "measuredAt": "original-time", "embeddingModel": "text-embedding-3-large",
        "models": {
            "gpt-4.1": {"status": "measured", "perPage": {"input": 100}},
            "gpt-6-sol": {"status": "measured", "apiVersion": "2026-06-01-preview",
                          "region": "southcentralus", "measuredAt": "preview-time", "embeddingModel": None},
        },
    }
    current = {"sampleSha256": "sample", "runsPerModel": 3,
               "apiVersion": "2026-06-01-preview", "region": "southcentralus"}
    records = resume_records(previous, current)
    assert records["gpt-4.1"]["apiVersion"] == "2025-11-01"
    assert records["gpt-4.1"]["region"] == "eastus2"
    assert records["gpt-4.1"]["measuredAt"] == "original-time"
    assert records["gpt-6-sol"]["region"] == "southcentralus"
    assert records["gpt-6-sol"]["measuredAt"] == "preview-time"
    assert records["gpt-6-sol"]["embeddingModel"] is None


@pytest.mark.parametrize("key,value", [("sampleSha256", "different"), ("runsPerModel", 1)])
def test_resume_rejects_incomparable_samples_and_run_counts(key, value):
    previous = {"sampleSha256": "sample", "runsPerModel": 3, "models": {}}
    current = {**previous, key: value}
    with pytest.raises(ValueError, match=key):
        resume_records(previous, current)


def test_atomic_snapshot_write_retries_transient_windows_file_locks(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.json"
    original = Path.replace
    calls = []

    def replace(source, target):
        calls.append(target)
        if len(calls) == 1:
            raise PermissionError("Synthetic sharing violation")
        return original(source, target)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr("tools.benchmark_invoice.time.sleep", Mock())
    write_snapshot(path, {"status": "measured"})
    assert json.loads(path.read_text()) == {"status": "measured"}
    assert len(calls) == 2
    assert not path.with_suffix(".json.tmp").exists()


def test_snapshot_write_surfaces_persistent_permission_errors(tmp_path, monkeypatch):
    replace = Mock(side_effect=PermissionError("Synthetic permanent permission failure"))
    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr("tools.benchmark_invoice.time.sleep", Mock())
    with pytest.raises(PermissionError):
        write_snapshot(tmp_path / "snapshot.json", {"status": "measured"})
    assert replace.call_count == 10
