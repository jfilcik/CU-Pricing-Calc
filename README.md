# Content Understanding pricing calculator

A web calculator and Python estimator for Azure Content Understanding. Document Intelligence pricing is out of scope.

For current rates, rely directly on the [Azure Content Understanding pricing page](https://azure.microsoft.com/en-us/pricing/details/content-understanding/) and [Azure OpenAI pricing page](https://azure.microsoft.com/en-us/pricing/details/azure-openai/), rather than this calculator's saved pricing snapshot. For how charges are calculated, see [Pricing for Azure Content Understanding in Foundry Tools](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/pricing-explainer).

## Content Understanding rates

Service pricing information is available on the [Azure Content Understanding pricing page](https://azure.microsoft.com/en-us/pricing/details/content-understanding/).

| Content extraction | USD rate |
| --- | --- |
| Document Basic (Read) | $1 / 1,000 pages |
| Document Standard (Layout) | $5 / 1,000 pages |
| Document Basic Sync (Preview) | $1.50 / 1,000 pages |
| Document Standard Sync (Preview) | $7.50 / 1,000 pages |
| Audio | $0.36 / hour |
| Video | $1 / hour |

**Sync is content extraction only.** The processing-mode selector offers **Sync** and **Async**. Both modes have separate Basic (Read) and Standard (Layout) volumes, with mode-specific rates. Sync disables field extraction and excludes model tokens, embeddings, and contextualization from the estimate. Switching back to Async restores the previous field extraction preference.

Sync supports **Document and Text only**; its file-type selector excludes Image, Audio, and Video. Async supports all five file types. Image, Audio, and Video cannot select Sync; any previously saved incompatible media/Sync combination is shown in Async mode.

Async field extraction adds model usage, document embeddings, and contextualization:

| Context processing | USD / million tokens |
| --- | --- |
| Standard | $1 |
| Advanced (Preview) | $3 |

Contextualization is independent of model family. Defaults use 1,000 context tokens per document page or image, 100,000 per audio hour, and 1,000,000 per video hour. The invoice benchmark confirms the document rate for measured models; other modalities remain planning assumptions. Text retains the heuristic of one context token per character; model tokens use pages rounded up at 3,000 characters per page.

## Models, deployments, and caching

The web calculator uses one full model selector, with separate Global, Regional, and Data Zone rate settings. The supplied supported-model list includes:

- GPT-6.1: Luna, Sol, Astra.
- GPT-6: Luna, Sol, Astra.
- GPT-5.6: Tera, Luna, Sol.
- GPT-5.5, GPT-5.4, GPT-5.4-mini, GPT-5.2, GPT-5.1, GPT-5, GPT-5-mini, GPT-5-nano.
- GPT-4.1, GPT-4.1-mini, GPT-4.1-nano, GPT-4o (including `2024-11-20` and `2024-08-06` versions), GPT-4o-mini.

The embedding selector includes `text-embedding-3-small`, `text-embedding-3-large`, and `text-embedding-ada-002`. Selecting a model does not confirm regional availability.

Model input, cached-input, output, and embedding rates come from [public Azure OpenAI pricing](https://azure.microsoft.com/en-us/pricing/details/azure-openai/?currency=USD), with Azure Retail Prices API verification for embedding/nano meters. The shared snapshot in `src/lib/azure-openai-pricing.json` was retrieved on **2026-10-19**, in USD, using **East US**, US Data Zone, and Global reference rates. It covers Standard PAYG short-context pricing, not batch, flex, priority, long-context surcharges, or cache writes. Prices in other regions can differ.

Unpublished model/deployment rates remain unpriced, including Regional GPT-5/6 rates and all GPT-6.1 Luna/Astra rates in this snapshot. The requested `gpt-5.6-tera` name maps to the official `terra` pricing meter. Adjust model pricing in USD per million tokens; overrides are saved separately for each model/deployment pair. Embedding prices also vary by deployment.

Total input tokens **include** cached input. Model cost is:

```text
((total input - cached input) * input rate
 + cached input * cached input rate
 + output * output rate) / 1,000,000
```

Cached input must not exceed total input. Caching does not discount embedding tokens or context processing. Zero tokens and zero rates are valid; missing required rates are not treated as zero. When a required rate is absent, the calculator shows **Known subtotal (incomplete)** and identifies the missing rates. PTU model/embedding charges remain separately priced and are excluded from a complete total.

## Measured invoice defaults

`src/lib/invoice-token-defaults.json` stores actual `prebuilt-invoice` usage from three runs per measured model on one [public Microsoft sample invoice](https://github.com/Azure-Samples/azure-ai-content-understanding-python/raw/refs/heads/main/data/invoice.pdf). Document defaults use page-weighted means for input, output, contextualization, and billed embedding tokens. **The web calculator defaults cached input to zero for every model, including after resetting estimates.** Enter your own cached-token estimate to model caching. The snapshot retains measured cached input as historical evidence, not as the web default, along with raw usage counters, sample SHA-256, and per-model API version, region, measurement date, and coverage; it contains no extracted invoice content or credentials.

Support depends on the region and API version. Five models were measured in East US 2 using GA API `2025-11-01`: GPT-4.1, GPT-5.1, GPT-5.2, GPT-5.4, and GPT-5.5. **South Central US with `2026-06-01-preview` adds measured GPT-5.6 Terra/Luna/Sol and GPT-6 Luna/Sol/Astra defaults**, using existing deployments without changing their configuration. The calculator retains the requested `gpt-5.6-tera` spelling as an alias for Terra.

GPT-6.1 Sol is advertised by the South Central US preview's `prebuilt-document` analyzer, but **not** `prebuilt-invoice`; GPT-6.1 Luna/Astra are not advertised by either analyzer there. No GPT-6.1 invoice measurements are claimed. GPT-5 remains unmeasured because the original East US 2 resource's PAYG quota was exhausted. Unsupported models, missing quota, and service errors are recorded rather than replaced with invented measurements. The UI distinguishes measured defaults from heuristics.

| Measured model | Input / page | Output / page | Cached input / page |
| --- | ---: | ---: | ---: |
| GPT-4.1 | 10,592.67 | 1,427 | 6,912 |
| GPT-5.1 | 10,540 | 1,185 | Not consistently reported |
| GPT-5.2 | 10,635 | 1,204 | Not consistently reported |
| GPT-5.4 | 10,664 | 913.33 | Not consistently reported |
| GPT-5.5 | 10,659 | 921 | Not consistently reported |
| GPT-5.6 Terra | 11,595 | 1,102.33 | 11,592 |
| GPT-5.6 Luna | 11,595 | 1,099 | Not consistently reported |
| GPT-5.6 Sol | 11,595 | 1,091.67 | 11,592 |
| GPT-6 Luna | 11,595 | 1,080 | Not consistently reported |
| GPT-6 Sol | 11,595 | 1,106 | Not consistently reported |
| GPT-6 Astra | 11,595 | 1,104 | Not consistently reported |

All eleven measured models reported 1,000 contextualization tokens and zero billed embedding tokens per page. The snapshot retains unrounded averages.

Repeated runs of the same invoice can create warm-cache hits; these averages are **not a guaranteed cache hit rate for new invoices**. Missing cache counters remain unknown in the snapshot and use an explicit zero-cache planning assumption. No embedding ledger entries means zero billed embeddings for this analyzer, not for every CU workload.

Unmeasured document models and all audio/video/text/image defaults retain size-matched heuristics: mini/nano use matching GPT-4.1 estimates, regular models use GPT-4.1 estimates, and versioned GPT-4o uses GPT-4o estimates. Invoice PDF measurements cannot calibrate other modalities. Override counts or reset them to the model defaults in the UI; representative production usage is preferable.

To refresh measurements using an authorized CU resource with an existing model deployment:

```powershell
python -m tools.benchmark_invoice --account YOUR_ACCOUNT --resource-group YOUR_RESOURCE_GROUP --runs 3
```

For the South Central US preview, select the API version and the subscription explicitly:

```powershell
python -m tools.benchmark_invoice --account YOUR_ACCOUNT --resource-group YOUR_RESOURCE_GROUP --subscription YOUR_SUBSCRIPTION --api-version 2026-06-01-preview --models gpt-5.6-tera --runs 3 --resume
```

The runner uses Azure CLI authentication and an in-memory account key. It uses request-level model mappings, never changes resource defaults, and exits with code 2 for partial coverage. An existing `text-embedding-3-large` deployment is mapped if present; otherwise its mapping is omitted (the invoice baseline needs no embeddings). If an analyzer actually requires an unavailable embedding deployment, the service error is reported, not hidden. The `gpt-5.6-tera` calculator key resolves to the service's `gpt-5.6-terra` model and usage counters.

`--deploy-missing` permits temporary PAYG deployments when existing quota allows, with cleanup after each attempt; it can incur inference charges. `--models ... --resume` refreshes selected records while retaining other results from a matching sample/run-count snapshot. GA and preview measurements can coexist: each model retains its own API version, region, measurement date, and embedding configuration. Top-level API/region metadata describes the latest invocation, not every record.

## Web calculator

The web experience provides a single-page estimate with inline quantities, rates, and cost breakdowns.

- A single scrolling estimate shows content extraction, optional field extraction, model usage, document-only embeddings, contextualization, and a generated configuration summary.
- Documents have independent **Basic (Read)** and **Standard (Layout)** quantities in both Sync and Async processing modes. Their sum drives the total content volume; switching modes preserves the volumes and changes their rates. Minimal is no longer offered in the UI; saved Minimal allocations are excluded with a notice to reallocate them. The Python estimator retains its imported Basic/Standard modes.
- New visitors start with **gpt-6.1-sol** using **Global** deployment. Previously saved model and deployment selections are retained.
- Document and text volumes use **actual page counts**, defaulting to **1,000 pages**. Basic and Standard inputs and field extraction volumes also use actual pages; extraction rates remain displayed per 1,000 pages. Existing saved quantities retain their actual page counts. Images use thousands of images, and audio/video use minutes. Text uses 3,000 UTF-16 characters per page and retains the imported one-context-token-per-character assumption.
- Field extraction defaults to the content extraction volume but can be lowered independently. It scales model, embedding, and context usage without charging for content extraction twice. Its volume cannot exceed the content volume; exceeding it highlights the input with an inline error and suppresses totals until corrected.
- Volume controls accept 0 through 10,000,000 displayed units (actual pages for documents/text); combined document tiers must also stay within that range. Invalid quantities suppress totals instead of silently clamping inputs.
- Region displays the snapshot's **East US reference rates** and is intentionally read-only: no live regional pricing or currency conversion is implied. Global, Regional, Data Zone, and PTU deployment behavior, measured invoice defaults, caching, and custom rate overrides are preserved.

Upfront cost is zero. Monthly totals include all configured components; missing rates show an incomplete known subtotal, not a complete quote. Model-rate overrides live under **Model pricing advanced settings - caching and pricing**. Collapsing field extraction settings does not turn off its charges.

```powershell
npm install
npm run dev
```

```powershell
npm test
npm run typecheck
npm run build
```

The pricing configuration is in `src/lib/pricing-config.ts`; the UI and regression tests use the shared calculations in `src/lib/pricing-utils.ts`.

### GitHub Pages

The app builds as a static site with relative asset paths, so it works at `https://jfilcik.github.io/CU-Pricing-Calc/` or at a custom domain. The source repository is [jfilcik/CU-Pricing-Calc](https://github.com/jfilcik/CU-Pricing-Calc). No Spark runtime, server, API key, or sign-in is required. The template's Spark package remains in the dependency lockfile but is not imported by the app or build configuration.

Calculator settings and custom rate overrides are saved in this browser's `localStorage`, under `cu-pricing:` keys. They are not uploaded or shared with other visitors. Existing Spark-backed settings are not automatically migrated; re-enter them on the new site. Clearing site data resets saved settings. Storage failures are surfaced as errors rather than silently discarding changes.

To publish:

1. Review the bundled pricing and benchmark JSON for public distribution. All data included in a static build is downloadable, including model names, usage defaults, and benchmark metadata.
2. In the repository's **Settings > Pages**, set **Source** to **GitHub Actions**.
3. Merge these changes into `main`. The **Deploy calculator to GitHub Pages** workflow runs tests, type-checks, builds, and deploys `dist`. Pull requests only validate the build and do not deploy. You can also run the workflow manually on `main`.
4. Open the URL reported by the workflow's `github-pages` deployment environment. A custom domain or existing Pages configuration can change the final URL.

For a local production preview, run `npm run build` followed by `npm run preview`. Nothing has been published merely by adding the workflow; deployment requires pushing/merging and enabling Pages.

## Python estimator

See [tools/README.md](tools/README.md) for usage-based and schema-based estimation, CLI options, and examples.

```powershell
python -m tools.cost_estimator --help
python -m pytest -q tools\tests
python examples.py
```

## License

Spark template resources are licensed under the MIT license. See [LICENSE](LICENSE).
