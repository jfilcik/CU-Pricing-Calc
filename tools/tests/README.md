# Cost estimator tests

Run from the repository root:

```powershell
python -m pytest tools\tests -q
```

`test_cost_estimator.py` preserves coverage of usage/schema/default selection,
invoice arithmetic, schema multipliers, model comparisons, PTU behavior, batch
averages, and text conversion. Model-rate tests use the shared public-pricing snapshot;
synthetic overrides validate arithmetic separately. The documentation-rate invoice example uses
a custom configuration to validate arithmetic independently of live prices.

`test_pricing_structure.py` covers:

- Basic/read $1, Standard/layout $5, Basic Sync preview $1.50, and Standard
  Sync preview $7.50 per 1,000 pages, in all estimation modes.
- Standard $1/M and advanced preview $3/M contextualization independent of model.
- Mixed Basic/Standard usage, additive audio/video CE, and scaling.
- Sync suppression of FE, contextualization, embeddings, cache and schema
  features, including absent model prices; mixed Sync/async counters fail.
- GPT-5 family and configurable GPT-6 placeholder with caller-supplied prices
  for global, regional, and data-zone deployments.
- Explicit missing-rate failures (including cache), zero-token categories,
  legacy combined deployment configuration and independent regional prices.
- Cached input counted once as a subset of total input, scaled once; embeddings
  retain full-input heuristic billing for legacy manual usage and honor actual
  embedding ledgers, measured invoice defaults, and explicit overrides.
- Invalid negative/nonfinite quantities/rates and cache larger than input.
- Unsupported positive legacy Minimal counters rejected, not mispriced.
- Batch consistency and CLI JSON/text output, custom rates, Sync, advanced
  contextualization, and failure without a misleading total.

New-model test prices are **synthetic arithmetic fixtures**, not Azure quotes.
Exact-hour expectations avoid rounding drift: audio CE $0.36/hour, video CE
$1/hour; audio contextualization 100,000/hour and video 1,000,000/hour.

`test_invoice_benchmark.py` checks actual API counter shapes, missing versus zero
cache usage, page-weighted means, model identity checks, and polling URL safety.
It also checks Terra alias resolution, optional embedding mappings, mixed GA/preview
provenance, sample compatibility, and bounded retries for Windows snapshot file locks.
Tests do not make live Azure calls. The persisted measured snapshot supplies
document defaults; non-document token quantities remain heuristic.

Service rates come from the supplied Content Understanding structure; model and
embedding rates come from the public Azure OpenAI snapshot. Do not turn synthetic
test prices into product configuration.
