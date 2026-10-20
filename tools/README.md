# Content Understanding cost estimator

Estimates **Content Understanding only**, using actual API usage (recommended),
schema-based token estimates, or default planning heuristics. Document
Intelligence is outside this tool's scope.

## Service pricing

Rates are USD. Audio/video quantities remain **minutes** in the Python API and CLI.

| Content extraction | Price |
|---|---:|
| Document Basic (read) | $1 / 1,000 pages |
| Document Standard (layout; default) | $5 / 1,000 pages |
| Document Basic Sync (preview) | $1.50 / 1,000 pages |
| Document Standard Sync (preview) | $7.50 / 1,000 pages |
| Audio | $0.36 / hour |
| Video | $1 / hour |
| Image / text | No separate content-extraction charge |

**Sync supports content extraction only.** `basic_sync` and `standard_sync`
exclude model tokens, field extraction, contextualization, and embeddings,
even when usage or schema data contains those items or their flags are enabled.
The model need not have pricing for Sync. Sync usage counters also select CE-only
behavior; mixed Sync and asynchronous page counters must be estimated separately.

| Contextualization | USD / million contextualization tokens |
|---|---:|
| Standard (default) | $1 |
| Advanced (preview) | $3 |

Contextualization pricing is **independent of model class**. Quantities are
1,000 tokens per document page/image, exactly 100,000 per audio hour, and exactly
1,000,000 per video hour (no rounding of per-minute rates). The existing text
heuristic remains one contextualization token per character; model-token
estimates convert 3,000 characters to one page.

## Models and missing prices

The Python estimator and web calculator load the same
`src/lib/azure-openai-pricing.json` snapshot of [public Azure OpenAI pricing](https://azure.microsoft.com/en-us/pricing/details/azure-openai/?currency=USD).
Retrieved **2026-10-19**, it uses USD, East US/US Data Zone/Global Standard PAYG
short-context reference rates. It excludes batch, priority, flex, long-context
surcharges, and cache writes; other regions and negotiated rates can differ.

- GPT-4, GPT-5, and GPT-6 input/cached-input/output rates use published values
  where available. Unpublished cells remain unset, including Regional GPT-5/6
  and all GPT-6.1 Luna/Astra rates. No price is inferred from another model.
- The requested `gpt-5.6-tera` maps to the official `terra` pricing meter.
  The older unpriced `gpt-6` placeholder remains for Python API compatibility.
- Both explicit GPT-4o versions remain selectable.
- Embeddings include `text-embedding-3-small`, `text-embedding-3-large`,
  and `text-embedding-ada-002`. The old `text-embedding-ada-002 (Version 2)`
  spelling remains an alias.
- Each model has separate `global`, `regional`, and `data_zone` pricing entries.
  `datazone` is an accepted deployment alias. The previous `global_regional`
  key/deployment is retained; old configs with only this combined key still work.
- Measured document defaults come from `src/lib/invoice-token-defaults.json`.
  GPT-4.1, GPT-5.1, GPT-5.2, GPT-5.4, and GPT-5.5 have three successful runs
  each on one public invoice in East US 2 with GA API `2025-11-01`.
  South Central US preview API `2026-06-01-preview` adds three runs each for
  GPT-5.6 Terra/Luna/Sol and GPT-6 Luna/Sol/Astra. Model records retain their
  own API version, region, and measurement date across merged runs.
  GPT-6.1 Sol is supported by the preview base document analyzer, not the
  invoice analyzer, so GPT-6.1 invoice defaults remain heuristic.
  GPT-5 remains unmeasured after the original East US 2 quota limitation.
  Other models retain explicitly heuristic document estimates; all non-document
  modalities remain heuristic. Mini/nano use matching GPT-4.1 size estimates,
  regular new models use GPT-4.1 estimates, and versioned GPT-4o uses GPT-4o.
  See the [benchmark instructions](../README.md#measured-invoice-defaults) for
  coverage, provenance, reruns, quota limits, and service errors.
- Omitted `ProcessingRequest.cached_input_tokens` uses measured cache defaults
  in default planning mode; explicit zero disables them. Repeated-invoice cache
  averages are not guaranteed for new invoices. Schema mode assumes zero cache
  unless specified, and actual-usage mode uses only its supplied counters.
- Caller rates override only the selected request/deployment, without mutating
  the shared config. Missing rates are **not zero**: a nonzero token category
  without a price raises `ValueError`, and the CLI fails without printing a total.
  Rates for zero-token categories are not required; explicit zero prices are allowed.

Every breakdown includes `pricing_note`, also shown in human-readable reports.
Actual usage improves quantity accuracy, not the applicability of a regional or negotiated rate.
Existing PTU behavior remains: per-token model/embedding charges are excluded;
capacity charges are **not included**. Content extraction and contextualization
still apply.

## Python API

```python
from tools import CostEstimator, ProcessingRequest, SchemaConfig, UsageData

estimator = CostEstimator()

# Synthetic demonstration prices, NOT Azure quotes. Supply your verified rates.
rates = {
    "input_per_mtok": 2.0,
    "cached_input_per_mtok": 0.5,
    "output_per_mtok": 8.0,
}

usage = UsageData(
    input_tokens=1_000_000,       # TOTAL input, INCLUDING cached input
    cached_input_tokens=250_000, # Subset of input, never additional input
    output_tokens=100_000,
    contextualization_tokens=1_000_000,
    document_pages_basic=1000,
)
request = ProcessingRequest(
    file_type="document",
    quantity=1000,
    model_name="gpt-5",
    deployment_type="regional",
    document_tier="basic",
    contextualization_tier="advanced",
    model_rates=rates,
    usage_data=usage,
)
breakdown = estimator.estimate_cost(request)
print(breakdown.total_cost)  # 6.425 with these synthetic rates
print(breakdown.pricing_note)
print(estimator.explain_cost_drivers(request, breakdown))
```

Cached input is billed **once**:

```text
model cost = (total input - cached input) / 1M * input rate
           + cached input / 1M * cached-input rate
           + output / 1M * output rate
```

`cached_input_tokens <= input_tokens` is required. Cache does not discount
embedding tokens. Measured invoice defaults use reported billed embedding tokens
(zero for the measured analyzer); other defaults retain input-token heuristics.
API ledgers parsed by `from_api_response` do not invent embedding charges when
no embedding entries exist. Manually constructed legacy `UsageData` objects
without an explicit embedding ledger still fall back to full input when
`embeddings_enabled=True`; set `embedding_tokens_reported=True` to report zero.
Explicit positive embedding usage is billed even if the enable flag is omitted.

### Actual API usage and scaling

```python
usage = UsageData.from_api_response({
    "documentPagesBasic": 10,
    "contextualizationTokens": 10000,
    "tokens": {
        "gpt-5-input": 10000,
        "gpt-5-cached-input": 2500,
        "gpt-5-output": 1000,
    },
})
request = ProcessingRequest(
    "document", 1000, model_name="gpt-5", model_rates=rates, usage_data=usage,
)
scaled = estimator.estimate_from_usage(request, test_pages=10)
# All measured quantities, including cached tokens, are scaled 100 times.
```

Pass the response's top-level `usage` object, not extracted invoice content.
The parser also accepts the older singular `contextualizationToken` spelling
and converts `audioHours`/`videoHours` to minutes.
The token parser sums completion keys containing `input` and `output`; keys containing both
`cached` and `input` are counted only as cached subsets. Input counters must
already include cached input. Use `UsageData` directly for other API shapes.
Page counters supported: `documentPagesBasic`, `documentPagesStandard`,
`documentPagesBasicSync`, and `documentPagesStandardSync`. Asynchronous mixed
Basic/Standard counters are charged at their own rates; audio/video usage is
additive. If CE counters are absent, the selected `document_tier` and request
quantity determine CE cost.

The legacy `documentPagesMinimal` field is still parsed, but positive values
raise an error: the supplied Content Understanding structure gives it no rate.

### Schema/default planning

```python
request = ProcessingRequest(
    "document", 1000,
    model_name="gpt-5", model_rates=rates,
    document_tier="standard",
    schema_config=SchemaConfig(num_fields=10, field_complexity="moderate"),
    cached_input_tokens=100_000,  # Optional estimate for the entire target workload
)
rough = estimator.estimate_from_schema(request)

sync = estimator.estimate_cost(ProcessingRequest(
    "document", 1000, document_tier="basic_sync",
))
assert sync.total_cost == 1.5
```

`estimate_cost()` prefers usage, then schema, then default estimates.
`field_extraction_enabled=False` excludes FE in all modes; asynchronous
contextualization remains billable. Quantities, scale factors, schema sizes,
and supplied rates must be finite and nonnegative. `test_pages` must be positive.

### Custom configuration

`CostEstimator(config=...)` accepts the existing pricing configuration format.
Copy `PRICING_CONFIG`, then add an exact model ID or deployment-specific prices.
Model entries require `name`, `class`, `tokens_per_unit`, and `pricing`.
Pricing keys are `input_per_mtok`, `cached_input_per_mtok`, `output_per_mtok`
(USD/million tokens); `None` explicitly means missing. Supply measured usage
instead of inventing per-unit token estimates.

## CLI

Run from the repository root; the estimator itself uses the Python standard library.
Each command supports `--json` for structured output.

```powershell
# Basic read planning; retained GPT-4 model prices are labeled estimates
python tools\cost_estimator.py estimate --file-type document --quantity 1000 --document-tier basic

# Content-extraction-only Sync preview
python tools\cost_estimator.py estimate --file-type document --quantity 1000 --document-tier basic_sync

# Actual usage, advanced contextualization, cache and synthetic demonstration rates
python tools\cost_estimator.py estimate-usage --pages 1000 --model gpt-5 --deployment regional --document-tier basic --contextualization-tier advanced --input-tokens 1000000 --cached-input-tokens 250000 --output-tokens 100000 --ctx-tokens 1000000 --input-rate 2 --cached-input-rate .5 --output-rate 8 --json

# Schema planning
python tools\cost_estimator.py estimate --file-type document --quantity 1000 --schema-fields 10 --schema-complexity moderate

# Audio usage; quantities are minutes
python tools\cost_estimator.py estimate-usage --file-type audio --quantity 60 --input-tokens 0 --output-tokens 0

# Batch results, optionally with custom model configuration
python tools\cost_estimator.py analyze --results-file example_batch_results.json
```

Both `estimate` and `estimate-usage` accept `--document-tier`,
`--contextualization-tier`, `--cached-input-tokens`, `--input-rate`,
`--cached-input-rate`, `--output-rate`, `--no-field-extraction`, `--embeddings`,
and `--embeddings-model`. Usage also accepts `--embedding-tokens`.
`estimate-usage --quantity` replaces `--pages`; `--scale-to` scales measured
quantity to the target (requires positive measured quantity).
`--pricing-config path.json` is available on all three commands and loads a
complete configuration, including custom exact model IDs.

## Batch analysis

Existing result keys remain supported:

```json
[
  {
    "file_name": "invoice.pdf",
    "file_type": "document",
    "pages": 10,
    "actual_input_tokens": 26000,
    "actual_cached_input_tokens": 13000,
    "actual_output_tokens": 900,
    "model_name": "gpt-5",
    "deployment_type": "global",
    "document_tier": "basic",
    "contextualization_tier": "advanced",
    "contextualization_tokens": 10000,
    "model_rates": {
      "input_per_mtok": 2,
      "cached_input_per_mtok": 0.5,
      "output_per_mtok": 8
    }
  }
]
```

Rates above are synthetic examples only. Batch entries also accept `quantity`,
`embedding_tokens`, `embeddings_enabled`, `embeddings_model`, and
`field_extraction_enabled`. For backward compatibility, absent
`contextualization_tokens` means no measured contextualization in batch analysis.
Batch reports use the same pricing/cache/Sync checks as individual estimates.
Unknown models/rates raise rather than silently disappearing from totals.
Use `analyze_batch_results()` and `explain_batch_analysis()` from Python.

## Validation and references

```powershell
python -m pytest tools\tests -q
```

See [test coverage notes](tests/README.md). Service rates follow the supplied
Content Understanding pricing structure. The public
[pricing explainer](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/pricing-explainer)
provides background; verify applicable Azure model/deployment prices separately.
Schema/default heuristics and single-invoice measured baselines are planning aids only; public prices may differ from your deployment's effective rates.

License: see [LICENSE](../LICENSE).
