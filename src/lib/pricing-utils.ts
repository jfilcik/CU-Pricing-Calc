import {
  pricingConfig, FileType, DeploymentType, DocumentMode, DocumentTier, ProcessingMode, ContextualizationType,
  TokenPricing, isSyncMode
} from './pricing-config';

export interface CalculationInputs {
  fileType: FileType;
  quantity: number;
  modelName: string;
  deploymentType: DeploymentType;
  customInputTokens?: number;
  customOutputTokens?: number;
  customCachedInputTokens?: number;
  documentMode?: DocumentMode;
  processingMode?: ProcessingMode;
  documentQuantities?: Record<DocumentTier, number>;
  fieldQuantity?: number;
  contextualizationType?: ContextualizationType;
  fieldExtractionEnabled?: boolean;
  tokenPricing?: Partial<TokenPricing>;
  embeddingsEnabled: boolean;
  embeddingsModel?: string;
  embeddingsTokensPerCall?: number;
}

export interface CalculationResults {
  ce: {
    units: number;
    cost: number;
  };
  fe: {
    inputTokens: number;
    cachedInputTokens: number;
    uncachedInputTokens: number;
    outputTokens: number;
    totalTokens: number;
    inputCost: number | null;
    cachedInputCost: number | null;
    outputCost: number | null;
    cost: number | null;
  };
  embeddings: {
    totalTokens: number;
    cost: number | null;
  };
  ctx: {
    tokens: number;
    cost: number;
  };
  total: number | null;
  knownSubtotal: number;
  missingRates: string[];
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(amount);
}

export function formatCurrencyPrecise(amount: number): string {
  // Format to 6 significant digits
  const formatted = amount.toPrecision(6);
  const num = parseFloat(formatted);
  
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 8 // Allow up to 8 decimal places to show tiny amounts
  }).format(num);
}

export function formatNumber(num: number): string {
  return new Intl.NumberFormat('en-US').format(num);
}

export function formatTokens(tokens: number): string {
  if (tokens >= 1000000) {
    return `${(tokens / 1000000).toFixed(1)}M`;
  } else if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}K`;
  }
  return formatNumber(tokens);
}

export function convertTextToPages(characters: number): number {
  return Math.ceil(characters / pricingConfig.page_from_chars);
}

export function getUnitsForCalculation(fileType: FileType, quantity: number): number {
  if (fileType === 'text') {
    return convertTextToPages(quantity);
  }
  return quantity;
}

export function getDocumentExtractionRate(tier: DocumentTier, mode: ProcessingMode): number {
  if (mode === 'async') return pricingConfig.ce.document_per_1000_pages[tier];
  if (tier === 'minimal') throw new Error('Minimal extraction is not available in sync mode');
  return pricingConfig.ce.document_per_1000_pages[`${tier}_sync`];
}

export function calculatePricing(inputs: CalculationInputs): CalculationResults {
  const { fileType, quantity, modelName, deploymentType } = inputs;
  const documentMode = inputs.documentMode ?? 'standard';
  const documentTier = documentMode === 'basic_sync' ? 'basic'
    : documentMode === 'standard_sync' ? 'standard' : documentMode;
  const contextualizationType = inputs.contextualizationType ?? 'standard';
  const processingMode = inputs.processingMode ?? (isSyncMode(documentMode) ? 'sync' : 'async');
  if (processingMode !== 'sync' && processingMode !== 'async') throw new Error('Unknown processing mode');
  if (processingMode === 'sync' && fileType !== 'document' && fileType !== 'text') {
    throw new Error('Sync processing supports Document and Text only');
  }
  const enabled = inputs.fieldExtractionEnabled !== false && processingMode !== 'sync';
  const fieldValues = enabled ? {
    fieldQuantity: inputs.fieldQuantity,
    inputTokens: inputs.customInputTokens, outputTokens: inputs.customOutputTokens,
    cachedInputTokens: inputs.customCachedInputTokens, embeddingTokens: inputs.embeddingsTokensPerCall,
    ...inputs.tokenPricing
  } : {};
  for (const [label, value] of Object.entries({
    quantity, ...fieldValues,
    ...(fileType === 'document' && inputs.documentQuantities ? inputs.documentQuantities : {})
  })) {
    if (value != null && (!Number.isFinite(value) || value < 0)) {
      throw new Error(`${label} must be a finite, non-negative number`);
    }
  }
  if (!(fileType in fileTypeUnitKeys)) throw new Error(`Unknown file type: ${fileType}`);
  if (!(documentMode in pricingConfig.ce.document_per_1000_pages)) throw new Error('Unknown document mode');
  if (!(contextualizationType in pricingConfig.ctx.per_mtok)) throw new Error('Unknown contextualization type');
  const units = getUnitsForCalculation(fileType, quantity);
  const fieldQuantity = inputs.fieldQuantity ?? quantity;
  if (enabled && fieldQuantity > quantity) {
    throw new Error('Field extraction volume cannot exceed content extraction volume');
  }
  const fieldUnits = getUnitsForCalculation(fileType, fieldQuantity);
  if (fileType === 'document' && inputs.documentQuantities) {
    const tierTotal = Object.values(inputs.documentQuantities).reduce((sum, value) => sum + value, 0);
    if (Math.abs(tierTotal - quantity) > Number.EPSILON * Math.max(1, quantity) * 4) {
      throw new Error('Document tier volumes must add up to the content extraction volume');
    }
  }
  const ceCost = fileType === 'document'
    ? inputs.documentQuantities
      ? (Object.entries(inputs.documentQuantities) as [DocumentTier, number][]).reduce(
        (sum, [tier, pages]) => pages === 0 ? sum : sum + pages / 1000 * getDocumentExtractionRate(tier, processingMode), 0)
      : units / 1000 * getDocumentExtractionRate(documentTier, processingMode)
    : fileType === 'audio' ? units * pricingConfig.ce.audio_per_minute
    : fileType === 'video' ? units * pricingConfig.ce.video_per_minute : 0;
  const missingRates: string[] = [];
  const fe: CalculationResults['fe'] = {
    inputTokens: 0, cachedInputTokens: 0, uncachedInputTokens: 0, outputTokens: 0,
    totalTokens: 0, inputCost: 0, cachedInputCost: 0, outputCost: 0, cost: 0
  };
  const embeddings: CalculationResults['embeddings'] = { totalTokens: 0, cost: 0 };
  const ctx = { tokens: 0, cost: 0 };
  if (enabled) {
    const model = pricingConfig.models.find(m => m.name === modelName);
    if (!model) throw new Error(`Model ${modelName} not found`);
    const tokensPerUnit = model.tokens_per_unit[fileTypeUnitKeys[fileType]];
    if (!tokensPerUnit) throw new Error(`No token estimate for ${fileType}`);
    const input = inputs.customInputTokens ?? tokensPerUnit.in;
    const cached = inputs.customCachedInputTokens ?? tokensPerUnit.cached_input ?? 0;
    if (cached > input) throw new Error('Cached input tokens cannot exceed total input tokens');
    fe.inputTokens = fieldUnits * input;
    fe.cachedInputTokens = fieldUnits * cached;
    fe.uncachedInputTokens = fe.inputTokens - fe.cachedInputTokens;
    fe.outputTokens = fieldUnits * (inputs.customOutputTokens ?? tokensPerUnit.out);
    fe.totalTokens = fe.inputTokens + fe.outputTokens;
    const rates = deploymentType === 'ptu' ? null : model.pricing[deploymentType];
    if (deploymentType !== 'ptu' && !rates) throw new Error('Unknown deployment type');
    const cost = (tokens: number, key: keyof TokenPricing, label: string): number | null => {
      if (tokens === 0) return 0;
      if (deploymentType === 'ptu') return null;
      const rate = inputs.tokenPricing?.[key] ?? rates?.[key];
      if (rate == null) {
        missingRates.push(label);
        return null;
      }
      return tokens / 1000000 * rate;
    };
    fe.inputCost = cost(fe.uncachedInputTokens, 'input_per_mtok', 'Input token rate');
    fe.cachedInputCost = cost(fe.cachedInputTokens, 'cached_input_per_mtok', 'Cached input token rate');
    fe.outputCost = cost(fe.outputTokens, 'output_per_mtok', 'Output token rate');
    fe.cost = fe.inputCost == null || fe.cachedInputCost == null || fe.outputCost == null
      ? null : fe.inputCost + fe.cachedInputCost + fe.outputCost;
    if (inputs.embeddingsEnabled) {
      const embedding = pricingConfig.embeddings[inputs.embeddingsModel ?? 'text-embedding-3-small'];
      if (!embedding) throw new Error(`Unknown embeddings model: ${inputs.embeddingsModel}`);
      embeddings.totalTokens = fieldUnits * (inputs.embeddingsTokensPerCall ?? tokensPerUnit.embeddings ?? input);
      const rate = deploymentType === 'ptu' ? null : embedding.pricing[deploymentType];
      if (embeddings.totalTokens === 0) embeddings.cost = 0;
      else if (rate == null) {
        embeddings.cost = null;
        if (deploymentType !== 'ptu') missingRates.push('Embedding token rate');
      } else embeddings.cost = embeddings.totalTokens / 1000 * rate;
    }
    const contextUnits = fileType === 'text' ? fieldQuantity : fieldUnits;
    const contextKey = fileType === 'text' ? 'text_chars' : fileTypeUnitKeys[fileType];
    ctx.tokens = contextUnits * (tokensPerUnit.contextualization ?? pricingConfig.ctx.units[contextKey]);
    ctx.cost = ctx.tokens / 1000000 * pricingConfig.ctx.per_mtok[contextualizationType];
  }
  const knownSubtotal = ceCost + ctx.cost + (fe.inputCost ?? 0) + (fe.cachedInputCost ?? 0)
    + (fe.outputCost ?? 0) + (embeddings.cost ?? 0);
  if (enabled && deploymentType === 'ptu' && (fe.cost == null || embeddings.cost == null)) {
    missingRates.push('PTU model/embedding charges (priced separately)');
  }
  const total = fe.cost == null || embeddings.cost == null ? null : knownSubtotal;
  if (!Number.isFinite(knownSubtotal) || !Number.isFinite(fe.totalTokens) || !Number.isFinite(ctx.tokens)) {
    throw new Error('Inputs exceed the supported calculation range');
  }
  return { ce: { units, cost: ceCost }, fe, embeddings, ctx, total, knownSubtotal, missingRates };
}

export const fileTypeUnitKeys = {
  document: 'doc_page', text: 'text_page', image: 'image',
  audio: 'audio_minute', video: 'video_minute'
} as const;