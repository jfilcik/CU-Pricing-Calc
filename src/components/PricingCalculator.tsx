import { useState, type ReactNode } from 'react';
import { useLocalStorage as useKV } from '@/hooks/use-local-storage';
import { Calculator, ChevronDown, ExternalLink, Info } from 'lucide-react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import {
  pricingConfig, FileType, DeploymentType, DocumentMode, DocumentTier, ProcessingMode, ContextualizationType,
  TokenPricing, deploymentTypeLabels, fileTypeLabels, isSyncMode,
  invoiceBenchmark, publicPricingSnapshot
} from '@/lib/pricing-config';
import {
  calculatePricing, CalculationResults, fileTypeUnitKeys, formatCurrency, formatCurrencyPrecise,
  formatNumber, getDocumentExtractionRate
} from '@/lib/pricing-utils';
import './pricing-calculator.css';

const MAX_VOLUME = 10000000;
const billingUnitFormatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 12 });
const documentTiers = ['basic', 'standard'] as const;
const volumeScales: Record<FileType, number> = {
  document: 1, text: 3000, image: 1000, audio: 1, video: 1
};
const volumeUnits: Record<FileType, string> = {
  document: 'pages', text: 'pages', image: '1,000 images', audio: 'minute', video: 'minute'
};

function NumberField({ id, label, value, onChange, placeholder, max, readOnly, unit, error }: {
  id: string; label: string; value: number | undefined;
  onChange?: (value: number | undefined) => void; placeholder?: string;
  max?: number; readOnly?: boolean; unit?: string; error?: string;
}) {
  return (
    <div className="calc-field">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type="number" min="0" max={max} step="any" value={value ?? ''}
        readOnly={readOnly} placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        aria-describedby={[unit && `${id}-unit`, error && `${id}-error`].filter(Boolean).join(' ') || undefined}
        onChange={event => onChange?.(event.target.value === '' ? undefined : Number(event.target.value))} />
      {unit && <span id={`${id}-unit`} className="calc-unit">{unit}</span>}
      {error && <p id={`${id}-error`} role="alert" className="calc-field-error">{error}</p>}
    </div>
  );
}

const displayCost = (cost: number | null | undefined) => cost === undefined
  ? 'Invalid inputs' : cost === null ? 'Not priced' : formatCurrencyPrecise(cost);
type TokenEstimate = { input?: number; cached?: number; output?: number; embeddings?: number };
const rateFields: Array<{ key: keyof TokenPricing; label: string }> = [
  { key: 'input_per_mtok', label: 'Uncached input' },
  { key: 'cached_input_per_mtok', label: 'Cached input' },
  { key: 'output_per_mtok', label: 'Output' }
];

function PricingRow({ label, subtext, quantity, rate, cost }: {
  label: string; subtext?: string; quantity: ReactNode; rate: ReactNode; cost: number | null | undefined;
}) {
  return (
    <div className="calc-pricing-row">
      <div className="calc-row-label">{label}{subtext && <small>{subtext}</small>}</div>
      <div className="calc-row-quantity">{quantity}</div>
      <span className="calc-operator" aria-hidden="true">&times;</span>
      <div className="calc-row-rate">{rate}</div>
      <div className="calc-row-cost"><span aria-hidden="true">=</span> {displayCost(cost)}</div>
    </div>
  );
}

export default function PricingCalculator() {
  const [storedFileType, setFileType] = useKV<FileType>('calc-file-type', 'document');
  const [storedQuantity, setQuantity] = useKV<number>('calc-quantity', 1000);
  const [storedModelName, setModelName] = useKV<string>('calc-model', 'gpt-6.1-sol');
  const [storedDeployment, setDeploymentType] = useKV<DeploymentType>('calc-deployment', 'global');
  const [storedMode] = useKV<DocumentMode>('calc-document-mode', 'standard');
  const [storedProcessingMode, setProcessingMode] = useKV<ProcessingMode>(
    'calc-processing-mode', storedMode && isSyncMode(storedMode) ? 'sync' : 'async');
  const [storedTiers, setDocumentQuantities] = useKV<Record<DocumentTier, number> | null>('calc-document-volumes-v1', null);
  const [fieldQuantities, setFieldQuantities] = useKV<Partial<Record<FileType, number>>>('calc-field-volumes-v1', {});
  const [storedContext, setContextualizationType] = useKV<ContextualizationType>('calc-context', 'standard');
  const [storedFieldExtraction, setFieldExtractionEnabled] = useKV<boolean>('calc-field-extraction-enabled', true);
  const [storedExpanded, setFieldExtractionExpanded] = useKV<boolean>('calc-field-extraction-expanded', true);
  const [embeddingsModel, setEmbeddingsModel] = useState('text-embedding-3-small');
  const [tokenEstimates, setTokenEstimates] = useState<Record<string, TokenEstimate>>({});
  const [rateOverrides, setRateOverrides] = useKV<Record<string, Partial<TokenPricing>>>('calc-token-rates-v2', {});
  const fileType = storedFileType ?? 'document';
  const modelName = storedModelName === 'GPT-6 (custom deployment)' ? 'gpt-6-sol' : storedModelName ?? 'gpt-6.1-sol';
  const deploymentType = storedDeployment ?? 'global';
  const documentMode = storedMode === 'minimal' ? 'standard' : storedMode ?? 'standard';
  const contextualizationType = storedContext ?? 'standard';
  const supportsSync = fileType === 'document' || fileType === 'text';
  const processingMode = supportsSync ? storedProcessingMode ?? 'async' : 'async';
  const sync = processingMode === 'sync';
  const availableFileTypes: FileType[] = sync ? ['document', 'text'] : ['document', 'text', 'image', 'audio', 'video'];
  const basicDefault = documentMode === 'basic' || documentMode === 'basic_sync';
  const documentQuantities = {
    minimal: 0,
    basic: storedTiers?.basic ?? (basicDefault ? storedQuantity ?? 0 : 0),
    standard: storedTiers?.standard ?? (!basicDefault ? storedQuantity ?? 0 : 0)
  };
  const quantity = fileType === 'document'
    ? documentTiers.reduce((sum, tier) => sum + documentQuantities[tier], 0) : storedQuantity ?? 0;
  const fieldQuantity = fieldQuantities?.[fileType] ?? quantity;
  const fieldExtractionEnabled = !sync && (storedFieldExtraction ?? true);
  const fieldVolumeError = fieldExtractionEnabled && fieldQuantity > quantity
    ? 'Monthly field extraction volume cannot exceed content extraction volume. Reduce this value or increase content extraction volume.'
    : undefined;
  const expanded = Boolean(fieldVolumeError) || (storedExpanded ?? true);
  const model = pricingConfig.models.find(item => item.name === modelName);
  const defaultTokens = model?.tokens_per_unit[fileTypeUnitKeys[fileType]];
  const benchmark = fileType === 'document' ? invoiceBenchmark.models[modelName] : undefined;
  const estimateKey = `${modelName}:${fileType}`;
  const estimate = tokenEstimates[estimateKey] ?? {};
  const rateKey = `${modelName}:${deploymentType}`;
  const overrides = rateOverrides?.[rateKey] ?? {};
  const rates = deploymentType === 'ptu' ? undefined : model?.pricing[deploymentType];
  const embeddingRate = deploymentType === 'ptu' ? null : pricingConfig.embeddings[embeddingsModel].pricing[deploymentType];
  const scale = volumeScales[fileType];
  const perUnitLabel = fileType === 'audio' || fileType === 'video' ? 'minute'
    : fileType === 'image' ? 'image' : 'page';

  let results: CalculationResults | undefined;
  let error: string | undefined;
  try {
    if (quantity / scale > MAX_VOLUME || (fieldExtractionEnabled && fieldQuantity / scale > MAX_VOLUME)) {
      throw new Error('Processing volume must be between 0 and 10,000,000 billing units');
    }
    results = calculatePricing({
      fileType, quantity, modelName, deploymentType, documentMode, processingMode, contextualizationType,
      documentQuantities: fileType === 'document' ? documentQuantities : undefined,
      fieldQuantity, fieldExtractionEnabled, customInputTokens: estimate.input,
      customCachedInputTokens: estimate.cached ?? 0, customOutputTokens: estimate.output,
      tokenPricing: overrides, embeddingsEnabled: fileType === 'document', embeddingsModel,
      embeddingsTokensPerCall: estimate.embeddings
    });
  } catch (caught) {
    if (!(caught instanceof Error)) throw caught;
    error = caught.message;
  }

  const updateEstimate = (key: keyof TokenEstimate, value: number | undefined) => {
    setTokenEstimates(previous => ({
      ...previous, [estimateKey]: { ...previous[estimateKey], [key]: value }
    }));
  };
  const updateRate = (key: keyof TokenPricing, value: number | undefined) => {
    setRateOverrides(previous => {
      const updated = { ...previous?.[rateKey] };
      if (value === undefined) delete updated[key];
      else updated[key] = value;
      return { ...previous, [rateKey]: updated };
    });
  };
  const updateTier = (tier: DocumentTier, value: number | undefined) => {
    const updated = { ...documentQuantities, [tier]: value ?? 0 };
    setDocumentQuantities(updated);
    setQuantity(documentTiers.reduce((sum, key) => sum + updated[key], 0));
  };
  const monthlyCost = results?.total == null ? 'Incomplete estimate' : formatCurrency(results.total);
  const volumeUnit = `${fileType === 'image' ? 'x ' : ''}${volumeUnits[fileType]}`;
  const description = `${fileTypeLabels[fileType]} file type, ${formatNumber(quantity / scale)} ${volumeUnit} of input. ` +
    (fileType === 'document' ? `${sync ? 'Sync' : 'Async'} processing: ${formatNumber(documentQuantities.basic)} Basic (Read) pages and ${formatNumber(documentQuantities.standard)} Standard (Layout) pages. `
      : `${sync ? 'Sync' : 'Async'} processing. `) +
    (fieldExtractionEnabled
      ? `Field extraction enabled for ${formatNumber(fieldQuantity / scale)} ${volumeUnit} using ${deploymentTypeLabels[deploymentType]} ${modelName}, ` +
        `${formatNumber(estimate.input ?? defaultTokens?.in ?? 0)} input and ${formatNumber(estimate.output ?? defaultTokens?.out ?? 0)} output tokens per ${perUnitLabel}` +
        `${fileType === 'document' ? `, with ${embeddingsModel} embeddings` : ''}.`
      : `Field extraction disabled${sync ? ' (synchronous content extraction only)' : ''}.`);

  return (
    <div className="calc-page">
      <a href="#estimate" className="calc-skip-link">Skip to estimate</a>
      <header className="calc-site-header">
        <div className="calc-container calc-header-inner">
          <a className="calc-brand" href="https://azure.microsoft.com/" aria-label="Microsoft Azure">
            <span className="calc-microsoft-mark" aria-hidden="true"><i /><i /><i /><i /></span>
            <span>Microsoft</span><span className="calc-brand-divider" /><strong>Azure</strong>
          </a>
          <nav aria-label="Resources">
            <a href="https://azure.microsoft.com/en-us/pricing/details/content-understanding/" target="_blank" rel="noreferrer">Pricing details <ExternalLink size={13} /></a>
            <a href="https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/" target="_blank" rel="noreferrer">Documentation <ExternalLink size={13} /></a>
          </nav>
        </div>
      </header>

      <div className="calc-hero">
        <div className="calc-container">
          <p className="calc-eyebrow">AZURE CONTENT UNDERSTANDING</p>
          <h1>Pricing calculator</h1>
          <p>Estimate your monthly costs. Configure your content, choose your models, and see what goes into your estimate.</p>
          <a href="#estimate">Build your estimate <span aria-hidden="true">&darr;</span></a>
        </div>
      </div>

      <main id="estimate" className="calc-container calc-main">
        <div className="calc-estimate-heading">
          <div><span className="calc-section-kicker">YOUR ESTIMATE</span><h2>Make it your own</h2></div>
          <span className="calc-currency">Currency: <strong>USD ($)</strong></span>
        </div>
        <p className="calc-intro">Changes to your configuration automatically update your costs. Prices are estimates, not quotes.</p>

        <article className="calc-service" aria-label="Content Understanding estimate">
          <header className="calc-service-header">
            <div className="calc-service-title">
              <span className="calc-service-icon"><Calculator size={26} strokeWidth={1.5} /></span>
              <div><h2>Azure Content Understanding</h2><p>Multimodal content extraction and analysis</p></div>
            </div>
            <div className="calc-header-total"><span>Estimated monthly cost</span><strong>{error ? 'Invalid inputs' : monthlyCost}</strong></div>
          </header>

          <div className="calc-service-body">
            <div className="calc-select-grid">
              <div className="calc-field">
                <Label htmlFor="region">Region</Label>
                <Select value={publicPricingSnapshot.region} disabled>
                  <SelectTrigger id="region"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value={publicPricingSnapshot.region}>East US (reference rates)</SelectItem></SelectContent>
                </Select>
              </div>
              <div className="calc-field">
                <Label htmlFor="file-type">File type</Label>
                <Select value={fileType} onValueChange={(value: FileType) => {
                  setFileType(value);
                  setQuantity(value === 'text' ? 3000000 : value === 'audio' || value === 'video' ? 60 : 1000);
                }}>
                  <SelectTrigger id="file-type"><SelectValue /></SelectTrigger>
                  <SelectContent>{availableFileTypes.map(key =>
                    <SelectItem key={key} value={key}>{fileTypeLabels[key]}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="calc-field">
                <Label htmlFor="document-mode">Processing mode</Label>
                <Select value={processingMode} onValueChange={(value: ProcessingMode) => setProcessingMode(value)}>
                  <SelectTrigger id="document-mode"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="async">Async</SelectItem>
                    <SelectItem value="sync" disabled={!supportsSync}>Sync</SelectItem>
                  </SelectContent>
                </Select>
                <span className="calc-help">Sync supports Document and Text only.</span>
              </div>
            </div>
            <p className="calc-help">Reference pricing in USD, not a live regional quote. Pricing may differ in other regions.</p>

            <section className="calc-section" aria-labelledby="workload-heading">
              <h2 id="workload-heading">Content Understanding for {fileTypeLabels[fileType]}</h2>
              <div className="calc-volume">
                <NumberField id="quantity" label="Monthly content extraction volume"
                  value={quantity / scale} max={MAX_VOLUME} unit={volumeUnit}
                  readOnly={fileType === 'document'}
                  onChange={value => setQuantity((value ?? 0) * scale)} />
                <p className="calc-help">{fileType === 'document'
                  ? 'Total volume is the sum of the Basic and Standard tiers below.'
                  : `Enter the amount of content you expect to process each month (0 to ${formatNumber(MAX_VOLUME)}).`}
                  {fileType === 'text' && ' 1 page = 3,000 UTF-16 characters.'}</p>
              </div>
              <div className="calc-info">
                <Info size={18} aria-hidden="true" />
                <p>{sync ? 'Sync supports content extraction only. Field extraction, contextualization, model tokens, and embeddings are excluded.'
                  : fileType === 'document' ? 'Distribute your pages across extraction tiers. Basic (Read) and Standard (Layout) volumes are billed separately.'
                  : fileType === 'text' || fileType === 'image' ? `There is no charge for ${fileType} content extraction. Optional field extraction is priced separately.`
                  : `${fileTypeLabels[fileType]} is billed per minute. All volumes and estimates below use minutes, not hours.`}</p>
              </div>
              {fileType === 'document' && Boolean(storedTiers?.minimal || storedMode === 'minimal') &&
                <p role="status" className="calc-help">Minimal content extraction is no longer available. Reallocate any previously saved Minimal volume to Basic or Standard.</p>}

              <div className="calc-subsection-heading"><h3>Content Extraction</h3><span>Monthly cost</span></div>
              {fileType === 'document' ? documentTiers.map(tier =>
                <PricingRow key={tier} label={tier.charAt(0).toUpperCase() + tier.slice(1)}
                  subtext={tier === 'basic' ? 'Read' : 'Layout'}
                  quantity={<NumberField id={`volume-${tier}`} label={`${tier.charAt(0).toUpperCase() + tier.slice(1)} volume`}
                    value={documentQuantities[tier]} max={MAX_VOLUME}
                    unit="pages" onChange={value => updateTier(tier, value)} />}
                  rate={<>{formatCurrencyPrecise(getDocumentExtractionRate(tier, processingMode))}<small>per 1,000 pages</small></>}
                  cost={results ? documentQuantities[tier] / 1000 * getDocumentExtractionRate(tier, processingMode) : undefined} />
              ) : <PricingRow label={fileTypeLabels[fileType]}
                quantity={<>{formatNumber(quantity / scale)}<small>{volumeUnit}</small></>}
                rate={<>{formatCurrencyPrecise(fileType === 'audio' ? pricingConfig.ce.audio_per_minute
                  : fileType === 'video' ? pricingConfig.ce.video_per_minute : 0)}
                  <small>per {volumeUnits[fileType]}</small></>}
                cost={results?.ce.cost} />}
              <div className="calc-subtotal"><span>Content extraction subtotal</span><strong>{displayCost(results?.ce.cost)}</strong></div>
            </section>

            <section className="calc-section" aria-labelledby="field-heading">
              <div className="calc-field-heading">
                <h3 id="field-heading">Field Extraction</h3>
                <div className="calc-toggle"><Switch id="field-enabled" aria-label="Enable field extraction"
                  checked={fieldExtractionEnabled} disabled={sync} onCheckedChange={setFieldExtractionEnabled} />
                  <Label htmlFor="field-enabled">Enable field extraction</Label></div>
              </div>
              <p className="calc-help">{sync ? 'Unavailable for synchronous content extraction.'
                : 'Field extraction encompasses generative model usage, embeddings, and contextualization components.'}</p>

              {fieldExtractionEnabled && <>
                <Button variant="ghost" className="calc-disclosure" onClick={() => setFieldExtractionExpanded(!expanded)}
                  aria-expanded={expanded} aria-controls="field-details">
                  <ChevronDown size={16} className={expanded ? 'calc-chevron-open' : ''} />
                  {expanded ? 'Hide field extraction settings' : 'Show field extraction settings'}
                </Button>
                <div id="field-details" hidden={!expanded}>
                  <div className="calc-volume">
                    <NumberField id="field-quantity" label="Monthly field extraction volume" value={fieldQuantity / scale}
                      max={Math.min(MAX_VOLUME, quantity / scale)} unit={volumeUnit}
                      error={fieldVolumeError}
                      onChange={value => setFieldQuantities(previous => ({ ...previous, [fileType]: (value ?? 0) * scale }))} />
                    <p className="calc-help">Use a lower volume if only some of your content needs field extraction. This does not add another content extraction charge.</p>
                  </div>
                  <div className="calc-model-section">
                    <h4>Generative Model Usage</h4>
                    <div className="calc-select-grid">
                      <div className="calc-field">
                        <Label htmlFor="model">Model</Label>
                        <Select value={modelName} onValueChange={setModelName}>
                          <SelectTrigger id="model"><SelectValue /></SelectTrigger>
                          <SelectContent>{pricingConfig.models.map(item => <SelectItem key={item.name} value={item.name}>{item.name}</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                      <div className="calc-field">
                        <Label htmlFor="deployment">Deployment type</Label>
                        <Select value={deploymentType} onValueChange={(value: DeploymentType) => setDeploymentType(value)}>
                          <SelectTrigger id="deployment"><SelectValue /></SelectTrigger>
                          <SelectContent>{Object.entries(deploymentTypeLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div className="calc-token-grid">
                      <div><h5>Input</h5><NumberField id="input-tokens" label={`Total input tokens / ${perUnitLabel}`}
                        value={estimate.input ?? defaultTokens?.in} onChange={value => updateEstimate('input', value)} /></div>
                      <div><h5>Cached input</h5><NumberField id="cached-tokens" label={`Cached input tokens / ${perUnitLabel}`}
                        value={estimate.cached ?? 0} onChange={value => updateEstimate('cached', value)} /></div>
                      <div><h5>Output</h5><NumberField id="output-tokens" label={`Output tokens / ${perUnitLabel}`}
                        value={estimate.output ?? defaultTokens?.out} onChange={value => updateEstimate('output', value)} /></div>
                    </div>
                    <p className="calc-help">Cached input is a subset of total input, not additional tokens. Use your own per-unit averages for a different analyzer, schema, or content mix.</p>
                    <Button variant="outline" className="calc-reset" onClick={() => setTokenEstimates(previous => ({ ...previous, [estimateKey]: {} }))}>Reset token estimates</Button>
                    <div className="calc-provenance">
                      {benchmark?.status === 'measured' ? <p>
                        Document defaults measured using prebuilt-invoice, {invoiceBenchmark.runsPerModel} runs of a
                        {' '}<a href={invoiceBenchmark.sampleUrl} target="_blank" rel="noreferrer">public sample invoice</a>
                        {' '}on {(benchmark.measuredAt ?? invoiceBenchmark.measuredAt).slice(0, 10)}
                        {benchmark.region && ` in ${benchmark.region}`}{benchmark.apiVersion && ` using API ${benchmark.apiVersion}`}.
                        {' '}These are per-page averages, not a representative invoice corpus. Cached input defaults to zero; repeated invoice runs do not establish a guaranteed cache hit rate for new invoices.
                      </p> : <p>
                        Token defaults are heuristic estimates, not measured invoice usage.
                        {benchmark?.reason && ` Invoice benchmark unavailable: ${benchmark.reason}.`}
                        {fileType !== 'document' && ' Invoice PDF measurements do not calibrate this content type.'}
                        {' '}Mini/nano defaults use matching GPT-4.1 size estimates; other new models use GPT-4.1 estimates.
                      </p>}
                    </div>

                    <details className="calc-rate-settings">
                      <summary>Model pricing advanced settings - caching and pricing</summary>
                      <p className="calc-help">Defaults use <a href="https://azure.microsoft.com/en-us/pricing/details/azure-openai/" target="_blank" rel="noreferrer">public Azure OpenAI pricing</a>
                        {' '}in USD for {publicPricingSnapshot.region}, retrieved {publicPricingSnapshot.retrievedAt.slice(0, 10)}.
                        {' '}Standard short-context rates only; batch, priority, flex, long-context surcharges, and cache writes are excluded.
                        {' '}Unpublished rates remain unpriced. Adjust model pricing to override public defaults; model selection does not confirm regional availability.</p>
                      {deploymentType !== 'ptu' && <div className="calc-token-grid">
                        {rateFields.map(({ key, label }) => <NumberField key={key} id={key} label={`${label} ($ / million tokens)`}
                          value={overrides[key] ?? undefined}
                          placeholder={rates?.[key] == null ? 'Required when used' : `Public: ${rates[key]}`}
                          onChange={value => updateRate(key, value)} />)}
                      </div>}
                    </details>
                    {deploymentType === 'ptu' && <div role="status" className="calc-info"><Info size={18} /><p>PTU token charges are priced separately; the calculator shows a known subtotal, not a complete total.</p></div>}

                    {rateFields.map(({ key, label }, index) => {
                      const tokens = results ? [results.fe.uncachedInputTokens, results.fe.cachedInputTokens, results.fe.outputTokens][index] : undefined;
                      const cost = results ? [results.fe.inputCost, results.fe.cachedInputCost, results.fe.outputCost][index] : undefined;
                      return <PricingRow key={key} label={label}
                        quantity={<>{tokens === undefined ? '-' : billingUnitFormatter.format(tokens / 1000000)}<small>million tokens</small></>}
                        rate={<>{displayCost(deploymentType === 'ptu' ? null : overrides[key] ?? rates?.[key] ?? null)}<small>per million tokens</small></>}
                        cost={cost} />;
                    })}
                    <div className="calc-subtotal"><span>Generative model subtotal</span><strong>{displayCost(results?.fe.cost)}</strong></div>
                  </div>

                  {fileType === 'document' && <div className="calc-model-section">
                    <h4>Embeddings</h4>
                    <div className="calc-select-grid">
                      <div className="calc-field">
                        <Label htmlFor="embeddings">Embeddings model</Label>
                        <Select value={embeddingsModel} onValueChange={setEmbeddingsModel}>
                          <SelectTrigger id="embeddings"><SelectValue /></SelectTrigger>
                          <SelectContent>{Object.keys(pricingConfig.embeddings).map(name => <SelectItem key={name} value={name}>{name}</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                      <NumberField id="embedding-tokens" label={`Embedding tokens / ${perUnitLabel}`}
                        value={estimate.embeddings ?? defaultTokens?.embeddings ?? estimate.input ?? defaultTokens?.in}
                        onChange={value => updateEstimate('embeddings', value)} />
                    </div>
                    <p className="calc-help">{benchmark?.status === 'measured'
                      ? 'Uses embedding usage reported by the invoice benchmark; zero means no billed embedding tokens for this analyzer.'
                      : 'Unmeasured embedding usage is estimated from all input tokens, including cached input.'}
                      {' '}Model prompt caching does not discount embeddings.</p>
                    <PricingRow label="Embedding tokens"
                      quantity={<>{results ? billingUnitFormatter.format(results.embeddings.totalTokens / 1000) : '-'}<small>x 1,000 tokens</small></>}
                      rate={<>{displayCost(embeddingRate)}<small>per 1,000 tokens</small></>} cost={results?.embeddings.cost} />
                  </div>}

                  <div className="calc-model-section">
                    <h4>Contextualization</h4>
                    <div className="calc-field calc-context-select">
                      <Label htmlFor="context">Contextualization level</Label>
                      <Select value={contextualizationType} onValueChange={(value: ContextualizationType) => setContextualizationType(value)}>
                        <SelectTrigger id="context"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="standard">Standard - $1 / million tokens</SelectItem>
                          <SelectItem value="advanced">Advanced (Preview) - $3 / million tokens</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <p className="calc-help">Context processing is independent of model family. Measured invoice documents use reported context tokens; other estimates use 1,000 tokens per document page or image, 1,666.67 per audio minute, and 16,666.67 per video minute.
                      {fileType === 'text' && ' Text uses one context token per UTF-16 character (3,000 per page).'}</p>
                    <PricingRow label="Context tokens"
                      quantity={<>{results ? billingUnitFormatter.format(results.ctx.tokens / 1000000) : '-'}<small>million tokens</small></>}
                      rate={<>{formatCurrency(pricingConfig.ctx.per_mtok[contextualizationType])}<small>per million tokens</small></>}
                      cost={results?.ctx.cost} />
                  </div>
                </div>
              </>}
            </section>
            {error && !fieldVolumeError && <div role="alert" className="calc-error">{error}</div>}
            {results && <div className="calc-service-totals">
              <div><span>Upfront cost</span><strong>$0.00</strong></div>
              <div><span>{results.total == null ? 'Known subtotal (incomplete)' : 'Monthly cost'}</span>
                <strong>{formatCurrency(results.total ?? results.knownSubtotal)}</strong></div>
            </div>}
          </div>
          <footer className="calc-configuration"><span>CONFIGURATION SUMMARY</span><p>{description}</p></footer>
        </article>

        <section className="calc-estimate-summary" aria-labelledby="summary-heading">
          <div>
            <span className="calc-section-kicker">COST BREAKDOWN</span>
            <h2 id="summary-heading">Your monthly estimate</h2>
            <p className="calc-help">Pay as you go. No upfront commitment.</p>
          </div>
          {results ? <div className="calc-breakdown">
            <dl>
              <div><dt>Content Extraction</dt><dd>{displayCost(results.ce.cost)}</dd></div>
              {fieldExtractionEnabled && <>
                <div><dt>Model uncached input</dt><dd>{displayCost(results.fe.inputCost)}</dd></div>
                <div><dt>Model cached input</dt><dd>{displayCost(results.fe.cachedInputCost)}</dd></div>
                <div><dt>Model output</dt><dd>{displayCost(results.fe.outputCost)}</dd></div>
                {fileType === 'document' && <div><dt>Embeddings</dt><dd>{displayCost(results.embeddings.cost)}</dd></div>}
                <div><dt>Contextualization ({contextualizationType})</dt><dd>{displayCost(results.ctx.cost)}</dd></div>
              </>}
              <div className="calc-final-total"><dt>{results.total == null ? 'Known subtotal (incomplete)' : 'Estimated Total Cost'}</dt>
                <dd>{formatCurrency(results.total ?? results.knownSubtotal)}<small>/ month</small></dd></div>
            </dl>
            {results.missingRates.length > 0 && <p role="alert" className="calc-error">Not a complete estimate. Missing: {results.missingRates.join(', ')}.</p>}
          </div> : <p className="calc-error">Correct the invalid inputs above to see your estimate.</p>}
        </section>
        <p className="calc-disclaimer">USD estimates, excluding taxes. Model and embedding charges are billed through your configured Foundry deployments.
          {' '}Document Intelligence is not included. This standalone calculator is not connected to your Azure agreement.
          {' '}Refer to the <a href="https://azure.microsoft.com/en-us/pricing/details/content-understanding/" target="_blank" rel="noreferrer">Content Understanding pricing page <ExternalLink size={12} /></a>
          {' '}and <a href="https://azure.microsoft.com/en-us/pricing/details/azure-openai/" target="_blank" rel="noreferrer">Azure OpenAI pricing page <ExternalLink size={12} /></a> for current rates.</p>
      </main>
      <footer className="calc-page-footer"><div className="calc-container">Azure Content Understanding <span>Pricing estimates for planning purposes</span></div></footer>
    </div>
  );
}
