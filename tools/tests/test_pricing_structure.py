"""Content Understanding rate structure; model test rates are synthetic, not quotes."""

from copy import deepcopy
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import mock_open

import pytest

from tools.cost_estimator import (
    CostEstimator, ProcessingRequest, PRICING_CONFIG, PUBLIC_PRICING, INVOICE_BENCHMARK,
    SchemaConfig, UsageData, main,
)


RATES = {"input_per_mtok": 2.0, "cached_input_per_mtok": 0.5, "output_per_mtok": 8.0}
ROOT = Path(__file__).resolve().parents[2]

SUPPORTED_MODELS = [
    "gpt-6.1-luna", "gpt-6.1-sol", "gpt-6.1-astra",
    "gpt-6-luna", "gpt-6-sol", "gpt-6-astra",
    "gpt-5.6-tera", "gpt-5.6-luna", "gpt-5.6-sol",
    "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.2", "gpt-5.1",
    "gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4.1-mini",
    "gpt-4.1-nano", "gpt-4o", "gpt-4o-mini", "gpt-4o-2024-11-20", "gpt-4o-2024-08-06",
]


@pytest.mark.parametrize("name", SUPPORTED_MODELS)
def test_supported_models_inherit_matching_token_defaults(name):
    models = {model["name"]: model for model in PRICING_CONFIG["models"]}
    reference = (
        "gpt-4o-mini" if name.startswith("gpt-4o") and name.endswith("-mini")
        else "gpt-4o" if name.startswith("gpt-4o")
        else "gpt-4.1-nano" if name.endswith("-nano")
        else "gpt-4.1-mini" if name.endswith("-mini") else "gpt-4.1"
    )
    for file_type in ("text", "image", "audio", "video"):
        result = CostEstimator().estimate_cost(ProcessingRequest(
            file_type, 1000, model_name=name, model_rates=RATES,
        ))
        baseline = CostEstimator().estimate_cost(ProcessingRequest(
            file_type, 1000, model_name=reference, model_rates=RATES,
        ))
        assert (result.input_tokens, result.output_tokens) == (baseline.input_tokens, baseline.output_tokens)
    measured = INVOICE_BENCHMARK["models"][name]
    defaults = models[name]["tokens_per_unit"]["doc_page"]
    if measured["status"] == "measured":
        expected = measured["perPage"]
        assert defaults == {
            "in": expected["input"], "out": expected["output"],
            "cached_input": expected["cached_input"],
            "contextualization": expected["contextualization"], "embeddings": expected["embeddings"],
        }
    else:
        assert defaults == {"in": 2600, "out": 90}
    for deployment, rates in PUBLIC_PRICING["models"][name].items():
        assert models[name]["pricing"][deployment] == rates


def test_supported_embedding_names_include_canonical_ada():
    assert PRICING_CONFIG["embeddings"]["text-embedding-ada-002"] == PRICING_CONFIG["embeddings"][
        "text-embedding-ada-002 (Version 2)"
    ]


def cli(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "cost_estimator.py"), *args],
        cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
    )


@pytest.mark.parametrize("tier,expected", [
    ("basic", 1), ("standard", 5), ("basic_sync", 1.5), ("standard_sync", 7.5),
])
@pytest.mark.parametrize("mode", ["default", "schema", "usage"])
def test_document_tiers(tier, expected, mode):
    kwargs = {}
    if mode == "schema":
        kwargs["schema_config"] = SchemaConfig()
    elif mode == "usage":
        kwargs["usage_data"] = UsageData(0, 0, **{f"document_pages_{tier}": 1000})
    request = ProcessingRequest("document", 1000, document_tier=tier, **kwargs)
    breakdown = CostEstimator().estimate_cost(request)
    assert breakdown.ce_cost == expected
    if tier.endswith("_sync"):
        assert breakdown.total_cost == expected
        assert breakdown.total_tokens == 0


@pytest.mark.parametrize("model", ["gpt-4o", "gpt-4o-mini", "gpt-5-mini", "gpt-6"])
@pytest.mark.parametrize("mode", ["default", "schema", "usage"])
def test_advanced_context_is_independent_of_model(model, mode):
    kwargs = {"schema_config": SchemaConfig()} if mode == "schema" else {}
    if mode == "usage":
        kwargs["usage_data"] = UsageData(0, 0, contextualization_tokens=1_000_000)
    result = CostEstimator().estimate_cost(ProcessingRequest(
        "document", 1000, model_name=model, contextualization_tier="advanced",
        field_extraction_enabled=False, **kwargs,
    ))
    assert result.ctx_cost == 3.0


def test_usage_mixed_content_tiers_and_modalities_scale():
    result = CostEstimator().estimate_from_usage(ProcessingRequest(
        "document", 2000, usage_data=UsageData(
            0, 0, document_pages_basic=1000, document_pages_standard=1000,
            audio_minutes=60, video_minutes=60,
        ),
    ), scale_factor=2)
    assert result.ce_cost == pytest.approx((1 + 5 + .36 + 1) * 2)


@pytest.mark.parametrize("tier", ["basic_sync", "standard_sync"])
@pytest.mark.parametrize("mode", ["default", "schema", "usage"])
def test_sync_excludes_every_non_ce_component(tier, mode):
    kwargs = {}
    if mode == "schema":
        kwargs["schema_config"] = SchemaConfig(training_examples_count=10)
    elif mode == "usage":
        kwargs["usage_data"] = UsageData(
            1_000_000, 1_000_000, 1_000_000, embedding_tokens=1_000_000,
            cached_input_tokens=500_000,
        )
    request = ProcessingRequest(
        "document", 1000, model_name="unconfigured-model", document_tier=tier,
        embeddings_enabled=True, embeddings_model="not-needed",
        contextualization_tier="advanced", cached_input_tokens=10, **kwargs,
    )
    estimator = CostEstimator()
    result = estimator.estimate_cost(request)
    assert (result.fe_cost, result.ctx_cost, result.embeddings_cost) == (0, 0, 0)
    assert (result.input_tokens, result.output_tokens, result.cached_input_tokens) == (0, 0, 0)
    assert result.total_cost == result.ce_cost
    assert "excluded" in estimator.explain_cost_drivers(request, result)


def test_sync_usage_counters_without_explicit_tier_are_ce_only():
    request = ProcessingRequest("document", 1000, model_name="unconfigured-model", usage_data=UsageData(
        10, 20, 30, document_pages_basic_sync=500, document_pages_standard_sync=500,
    ))
    estimator = CostEstimator()
    result = estimator.estimate_cost(request)
    assert result.total_cost == 4.5
    assert result.total_tokens == 0
    assert "excluded" in estimator.explain_cost_drivers(request, result)


def test_mixed_sync_async_usage_rejected():
    request = ProcessingRequest("document", 2, usage_data=UsageData(
        0, 0, document_pages_basic=1, document_pages_basic_sync=1,
    ))
    with pytest.raises(ValueError, match="separate requests"):
        CostEstimator().estimate_cost(request)


@pytest.mark.parametrize("model", ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-6"])
@pytest.mark.parametrize("deployment", ["global", "regional", "data_zone", "datazone"])
def test_configurable_model_rates_and_cached_subset(model, deployment):
    result = CostEstimator().estimate_cost(ProcessingRequest(
        "document", 1000, model_name=model, deployment_type=deployment,
        model_rates=RATES, usage_data=UsageData(
            1_000_000, 100_000, cached_input_tokens=250_000,
        ),
    ))
    assert result.fe_cost == pytest.approx(.75 * 2 + .25 * .5 + .1 * 8)
    assert result.input_tokens == 1_000_000
    assert result.cached_input_tokens == 250_000
    assert "Caller-provided" in result.pricing_note


@pytest.mark.parametrize("model", ["gpt-6.1-astra", "gpt-6"])
@pytest.mark.parametrize("mode", ["default", "schema", "usage"])
def test_unknown_required_rates_never_return_a_total(model, mode):
    kwargs = {"schema_config": SchemaConfig()} if mode == "schema" else {}
    if mode == "usage":
        kwargs["usage_data"] = UsageData(100, 10)
    with pytest.raises(ValueError, match="Missing required input_per_mtok"):
        CostEstimator().estimate_cost(ProcessingRequest(
            "document", 1, model_name=model, **kwargs,
        ))


def test_missing_cached_rate_is_not_free_or_full_price():
    with pytest.raises(ValueError, match="cached_input_per_mtok"):
        CostEstimator().estimate_cost(ProcessingRequest(
            "document", 1, model_name="gpt-6.1-astra",
            model_rates={"input_per_mtok": 2, "output_per_mtok": 8},
            usage_data=UsageData(100, 10, cached_input_tokens=20),
        ))


def test_only_rates_for_nonzero_quantities_are_required():
    result = CostEstimator().estimate_cost(ProcessingRequest(
        "document", 1, model_name="gpt-6",
        model_rates={"cached_input_per_mtok": 2},
        usage_data=UsageData(100, 0, cached_input_tokens=100),
    ))
    assert result.fe_cost == pytest.approx(.0002)
    assert CostEstimator().estimate_cost(ProcessingRequest("document", 0, model_name="gpt-6")).total_cost == 0


def test_input_and_output_missing_rates_are_separate():
    with pytest.raises(ValueError, match="output_per_mtok"):
        CostEstimator().estimate_cost(ProcessingRequest(
            "document", 1, model_name="gpt-6.1-astra", model_rates={"input_per_mtok": 1},
            usage_data=UsageData(10, 20),
        ))


@pytest.mark.parametrize("mode", ["default", "schema", "usage"])
def test_cache_does_not_discount_embedding_input(mode):
    kwargs = {}
    if mode == "schema":
        kwargs["schema_config"] = SchemaConfig()
    if mode == "usage":
        kwargs["usage_data"] = UsageData(2600, 100, cached_input_tokens=1300)
    else:
        kwargs["cached_input_tokens"] = 1300
    result = CostEstimator().estimate_cost(ProcessingRequest(
        "document", 1, embeddings_enabled=True, model_rates=RATES, **kwargs,
    ))
    assert result.embeddings_cost == pytest.approx(2600 / 1000 * .00002)
    assert result.cached_input_tokens == 1300


def test_usage_explicit_embedding_tokens_override_input():
    result = CostEstimator().estimate_cost(ProcessingRequest(
        "document", 1, model_rates=RATES, usage_data=UsageData(
            2600, 100, cached_input_tokens=1300, embedding_tokens=400,
        ),
    ))
    assert result.embeddings_cost == pytest.approx(400 / 1000 * .00002)


def test_parse_cached_tokens_does_not_add_them_to_total_input():
    usage = UsageData.from_api_response({
        "documentPagesBasicSync": 2,
        "tokens": {"gpt-5-input": 100, "gpt-5-cached-input": 25, "gpt-5-output": 10},
    })
    assert (usage.input_tokens, usage.cached_input_tokens, usage.output_tokens) == (100, 25, 10)
    assert usage.document_pages_basic_sync == 2


def test_cached_tokens_scale_once():
    request = ProcessingRequest(
        "document", 1000, model_rates=RATES, usage_data=UsageData(
            10_000, 1000, cached_input_tokens=2500, document_pages_basic=10,
        ),
    )
    result = CostEstimator().estimate_from_usage(request, test_pages=10)
    assert (result.input_tokens, result.cached_input_tokens) == (1_000_000, 250_000)
    assert result.fe_cost == pytest.approx(2.425)
    assert result.ce_cost == 1


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), -float("inf")])
def test_invalid_quantities_and_rates_rejected(bad):
    with pytest.raises(ValueError):
        ProcessingRequest("document", bad)
    with pytest.raises(ValueError):
        UsageData(1, 1, cached_input_tokens=bad)
    with pytest.raises(ValueError):
        UsageData(bad, 1)
    with pytest.raises(ValueError):
        SchemaConfig(num_fields=bad)
    with pytest.raises(ValueError):
        ProcessingRequest("document", 1, model_rates={"input_per_mtok": bad})
    with pytest.raises(ValueError):
        CostEstimator().estimate_from_usage(ProcessingRequest(
            "document", 1, usage_data=UsageData(1, 1),
        ), scale_factor=bad)


def test_cached_tokens_cannot_exceed_input():
    with pytest.raises(ValueError, match="cannot exceed"):
        UsageData(1, 0, cached_input_tokens=2)
    with pytest.raises(ValueError, match="cannot exceed"):
        CostEstimator().estimate_cost(ProcessingRequest(
            "document", 1, cached_input_tokens=2601, model_rates=RATES,
        ))


@pytest.mark.parametrize("test_pages", [0, -1, float("inf"), float("nan")])
def test_invalid_scaling_denominator_rejected(test_pages):
    with pytest.raises(ValueError):
        CostEstimator().estimate_from_usage(ProcessingRequest(
            "document", 1, usage_data=UsageData(1, 1),
        ), test_pages=test_pages)


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf")])
def test_invalid_configured_model_rates_rejected(bad):
    config = deepcopy(PRICING_CONFIG)
    config["models"][0]["pricing"]["global"]["input_per_mtok"] = bad
    with pytest.raises(ValueError):
        CostEstimator(config).estimate_cost(ProcessingRequest("document", 1))


def test_unsupported_minimal_counter_is_not_billed_as_standard():
    with pytest.raises(ValueError, match="documentPagesMinimal"):
        CostEstimator().estimate_cost(ProcessingRequest(
            "document", 1, usage_data=UsageData(0, 0, document_pages_minimal=1),
        ))


def test_legacy_config_and_distinct_global_regional_prices():
    config = deepcopy(PRICING_CONFIG)
    model = config["models"][0]
    model["pricing"]["regional"]["input_per_mtok"] = 7
    estimator = CostEstimator(config)
    for deployment, expected in (("global", 2.5), ("regional", 7)):
        result = estimator.estimate_cost(ProcessingRequest(
            "document", 1, deployment_type=deployment, usage_data=UsageData(1_000_000, 0),
        ))
        assert result.fe_cost == expected
    del model["pricing"]["global"]
    del model["pricing"]["regional"]
    assert estimator.estimate_cost(ProcessingRequest(
        "document", 1, usage_data=UsageData(1_000_000, 0),
    )).fe_cost == 2.5


def test_context_rates_work_without_legacy_model_class_keys():
    config = deepcopy(PRICING_CONFIG)
    del config["ctx"]["regular_per_mtok"]
    del config["ctx"]["mini_per_mtok"]
    estimator = CostEstimator(config)
    for tier, expected in (("standard", 1), ("advanced", 3)):
        result = estimator.estimate_cost(ProcessingRequest(
            "document", 1000, contextualization_tier=tier,
            field_extraction_enabled=False,
        ))
        assert result.ctx_cost == expected


def test_public_prices_are_labeled_in_json_and_text():
    estimator = CostEstimator()
    request = ProcessingRequest("document", 1)
    result = estimator.estimate_cost(request)
    assert "Public Azure OpenAI USD Standard short-context prices" in result.pricing_note
    assert PUBLIC_PRICING["retrievedAt"] in estimator.explain_cost_drivers(request, result)


def test_batch_uses_same_rates_and_sync_rules():
    results = [
        {"pages": 1000, "model_name": "gpt-5", "model_rates": RATES,
         "document_tier": "basic", "actual_input_tokens": 1_000_000,
         "actual_cached_input_tokens": 250_000, "actual_output_tokens": 100_000},
        {"pages": 1000, "model_name": "gpt-6", "document_tier": "basic_sync",
         "actual_input_tokens": 1000},
    ]
    analysis = CostEstimator().analyze_batch_results(results)
    assert analysis["summary"]["total_cost"] == pytest.approx(1 + 2.425 + 1.5)
    assert analysis["summary"]["total_cached_input_tokens"] == 250_000
    assert analysis["per_document_breakdown"][1]["input_tokens"] == 0
    with pytest.raises(ValueError, match="Missing required"):
        CostEstimator().analyze_batch_results([
            {"pages": 1, "model_name": "gpt-6", "actual_input_tokens": 10},
        ])
    with pytest.raises(ValueError, match="not found"):
        CostEstimator().analyze_batch_results([{"pages": 1, "model_name": "unknown"}])


@pytest.mark.parametrize("command", ["estimate", "estimate-usage"])
def test_cli_custom_prices_cached_tokens_and_advanced(command):
    args = ["--quantity", "1000", "--file-type", "document"] if command == "estimate" else [
        "--pages", "1000", "--input-tokens", "1000000", "--output-tokens", "100000",
        "--ctx-tokens", "1000000",
    ]
    completed = cli(command, *args, "--model", "gpt-6", "--deployment", "regional",
                    "--document-tier", "basic", "--contextualization-tier", "advanced",
                    "--cached-input-tokens", "250000", "--input-rate", "2",
                    "--cached-input-rate", ".5", "--output-rate", "8", "--json")
    assert completed.returncode == 0, completed.stderr
    breakdown = json.loads(completed.stdout)["breakdown"]
    assert breakdown["cached_input_tokens"] == 250_000
    assert breakdown["ce_cost"] == 1
    assert breakdown["ctx_cost"] == 3
    if command == "estimate-usage":
        assert breakdown["fe_cost"] == pytest.approx(2.425)


def test_cli_missing_rates_fails_without_printing_total():
    result = cli("estimate", "--file-type", "document", "--quantity", "1", "--model", "gpt-6.1-astra")
    assert result.returncode != 0
    assert "Missing required" in result.stderr
    assert "Total Estimated Cost" not in result.stdout


def test_cli_loads_exact_custom_model_config(monkeypatch, capsys):
    config = deepcopy(PRICING_CONFIG)
    model = config["models"][-1]
    model["name"] = "configured-model-id"
    model["pricing"]["regional"] = RATES
    monkeypatch.setattr("builtins.open", mock_open(read_data=json.dumps(config)))
    monkeypatch.setattr(sys, "argv", [
        "cost_estimator.py", "estimate-usage", "--pages", "1",
        "--input-tokens", "1000000", "--output-tokens", "0",
        "--model", "configured-model-id", "--deployment", "regional",
        "--pricing-config", "caller-pricing.json", "--json",
    ])
    main()
    assert json.loads(capsys.readouterr().out)["breakdown"]["fe_cost"] == 2


@pytest.mark.parametrize("flag,value", [
    ("--quantity", "-1"), ("--input-rate", "nan"), ("--cached-input-tokens", "-1"),
])
def test_cli_invalid_inputs_fail(flag, value):
    result = cli("estimate", "--file-type", "document", "--quantity", "1", flag, value)
    assert result.returncode != 0
    assert "finite and nonnegative" in result.stderr


def test_cli_zero_base_cannot_scale_to_positive_quantity():
    result = cli("estimate-usage", "--pages", "0", "--scale-to", "10",
                 "--input-tokens", "10", "--output-tokens", "1", "--json")
    assert result.returncode != 0
    assert "positive measured quantity" in result.stderr


def test_cli_sync_and_exact_hourly_rates():
    sync = cli("estimate", "--file-type", "document", "--quantity", "1000",
               "--model", "gpt-6", "--document-tier", "standard_sync", "--embeddings")
    assert sync.returncode == 0, sync.stderr
    assert "$7.5000" in sync.stdout
    assert "excluded (Sync)" in sync.stdout
    audio = cli("estimate-usage", "--file-type", "audio", "--quantity", "60",
                "--input-tokens", "0", "--output-tokens", "0", "--json")
    assert audio.returncode == 0, audio.stderr
    assert json.loads(audio.stdout)["breakdown"]["ce_cost"] == pytest.approx(.36)


@pytest.mark.parametrize("deployment,expected", [
    ("global", .00002), ("regional", .000022), ("data_zone", .000022),
])
def test_embedding_prices_match_deployment(deployment, expected):
    result = CostEstimator().estimate_cost(ProcessingRequest(
        "document", 1, deployment_type=deployment,
        usage_data=UsageData(1000, 0, embedding_tokens=1000),
    ))
    assert result.embeddings_cost == expected


@pytest.mark.parametrize("model", [
    name for name, record in INVOICE_BENCHMARK["models"].items() if record["status"] == "measured"
])
def test_measured_invoice_defaults_use_reported_categories_and_cache(model):
    per_page = INVOICE_BENCHMARK["models"][model]["perPage"]
    result = CostEstimator().estimate_cost(ProcessingRequest(
        "document", 3, model_name=model, embeddings_enabled=True,
    ))
    assert result.input_tokens == int(3 * per_page["input"])
    assert result.cached_input_tokens == int(3 * (per_page["cached_input"] or 0))
    assert result.output_tokens == int(3 * per_page["output"])
    assert result.ctx_cost == pytest.approx(3 * per_page["contextualization"] / 1_000_000)
    assert result.embeddings_cost == 0
    assert "Measured prebuilt-invoice" in result.confidence_note
    if per_page["cached_input"] is None:
        assert "zero cache is a planning assumption" in result.confidence_note
    override = CostEstimator().estimate_cost(ProcessingRequest(
        "document", 3, model_name=model, cached_input_tokens=0,
    ))
    assert override.cached_input_tokens == 0


def test_api_ledger_does_not_infer_embedding_charge_from_completion_input():
    usage = UsageData.from_api_response({
        "documentPagesStandard": 1, "contextualizationTokens": 1000,
        "tokens": {"gpt-4.1-input": 1000, "gpt-4.1-output": 100},
    })
    assert usage.contextualization_tokens == 1000
    assert usage.embedding_tokens_reported
    result = CostEstimator().estimate_cost(ProcessingRequest(
        "document", 1, model_name="gpt-4.1", usage_data=usage, embeddings_enabled=True,
    ))
    assert result.embeddings_cost == 0


@pytest.mark.parametrize("command", ["estimate", "estimate-usage"])
def test_cli_omitted_cache_uses_planning_defaults_only_for_estimate(command):
    args = ["--file-type", "document", "--quantity", "3"] if command == "estimate" else [
        "--pages", "3", "--input-tokens", "1000", "--output-tokens", "100",
    ]
    result = cli(command, *args, "--model", "gpt-4.1", "--json")
    assert result.returncode == 0, result.stderr
    expected = 3 * INVOICE_BENCHMARK["models"]["gpt-4.1"]["perPage"]["cached_input"] if command == "estimate" else 0
    assert json.loads(result.stdout)["breakdown"]["cached_input_tokens"] == expected


def test_cli_publicly_priced_model_can_print_full_report_on_windows():
    result = cli("estimate", "--file-type", "document", "--quantity", "1", "--model", "gpt-5")
    assert result.returncode == 0, result.stderr
    assert "Public Azure OpenAI" in result.stdout


def test_embedding_ledger_is_not_counted_as_completion_input():
    usage = UsageData.from_api_response({
        "tokens": {"gpt-4.1-input": 100, "gpt-4.1-output": 10,
                   "text-embedding-3-large-input": 50},
    })
    assert (usage.input_tokens, usage.output_tokens, usage.embedding_tokens) == (100, 10, 50)
