import { describe, expect, it } from 'vitest';
import { calculatePricing, CalculationInputs } from './pricing-utils';
import { DocumentMode, invoiceBenchmark, pricingConfig, publicPricingSnapshot, TokenDeploymentType } from './pricing-config';

const inputs: CalculationInputs = {
  fileType: 'document', quantity: 1000, modelName: 'gpt-4o', deploymentType: 'global',
  embeddingsEnabled: false
};

describe('Content Understanding pricing', () => {
  it('includes every supplied model, including both GPT-4o versions', () => {
    expect(pricingConfig.models.map(model => model.name)).toEqual(expect.arrayContaining([
      'gpt-6.1-luna', 'gpt-6.1-sol', 'gpt-6.1-astra',
      'gpt-6-luna', 'gpt-6-sol', 'gpt-6-astra',
      'gpt-5.6-tera', 'gpt-5.6-luna', 'gpt-5.6-sol',
      'gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.2', 'gpt-5.1',
      'gpt-5', 'gpt-5-mini', 'gpt-5-nano', 'gpt-4.1', 'gpt-4.1-mini',
      'gpt-4.1-nano', 'gpt-4o', 'gpt-4o-mini', 'gpt-4o-2024-11-20', 'gpt-4o-2024-08-06'
    ]));
    expect(new Set(pricingConfig.models.map(model => model.name)).size).toBe(24);
    expect(Object.keys(pricingConfig.embeddings)).toEqual([
      'text-embedding-3-small', 'text-embedding-3-large', 'text-embedding-ada-002'
    ]);
  });

  it.each(pricingConfig.models.map(model => model.name))('%s uses measured document defaults or size-matched heuristics', name => {
    const model = pricingConfig.models.find(item => item.name === name)!;
    const referenceName = name.startsWith('gpt-4o') ? name.includes('mini') ? 'gpt-4o-mini' : 'gpt-4o'
      : name.endsWith('-nano') ? 'gpt-4.1-nano' : name.endsWith('-mini') ? 'gpt-4.1-mini' : 'gpt-4.1';
    const reference = pricingConfig.models.find(item => item.name === referenceName)!;
    for (const fileType of ['text', 'image', 'audio', 'video'] as const) {
      const result = calculatePricing({ ...inputs, fileType, modelName: name });
      const baseline = calculatePricing({ ...inputs, fileType, modelName: referenceName });
      expect(result.fe.inputTokens).toBe(baseline.fe.inputTokens);
      expect(result.fe.outputTokens).toBe(baseline.fe.outputTokens);
    }
    const measured = invoiceBenchmark.models[name];
    expect(model.tokens_per_unit.doc_page).toMatchObject(measured.status === 'measured'
      ? { in: measured.perPage!.input, out: measured.perPage!.output,
          cached_input: measured.perPage!.cached_input ?? 0, contextualization: measured.perPage!.contextualization,
          embeddings: measured.perPage!.embeddings }
      : { in: 2600, out: 90 });
    expect(model.pricing).toEqual(publicPricingSnapshot.models[name as keyof typeof publicPricingSnapshot.models]);
  });

  it.each<[DocumentMode, number]>([
    ['minimal', 0.01], ['basic', 1], ['standard', 5], ['basic_sync', 1.5], ['standard_sync', 7.5]
  ])('charges %s at the documented page rate', (documentMode, expected) => {
    const result = calculatePricing({ ...inputs, documentMode, fieldExtractionEnabled: false });
    expect(result.ce.cost).toBe(expected);
    expect(result.total).toBe(expected);
  });

  it.each<DocumentMode>(['basic_sync', 'standard_sync'])('excludes every field extraction component in %s', documentMode => {
    const result = calculatePricing({
      ...inputs, documentMode, contextualizationType: 'advanced', fieldExtractionEnabled: true,
      embeddingsEnabled: true, modelName: 'gpt-6-sol', customCachedInputTokens: 10
    });
    expect(result.ctx).toEqual({ tokens: 0, cost: 0 });
    expect(result.fe.totalTokens).toBe(0);
    expect(result.fe.cost).toBe(0);
    expect(result.embeddings.totalTokens).toBe(0);
    expect(result.total).toBe(result.ce.cost);
    expect(result.missingRates).toEqual([]);
  });

  it.each(['gpt-4o', 'gpt-4o-mini', 'gpt-5', 'gpt-6-sol'])('context rate does not depend on %s', modelName => {
    expect(calculatePricing({ ...inputs, modelName }).ctx.cost).toBe(1);
    expect(calculatePricing({ ...inputs, modelName, contextualizationType: 'advanced' }).ctx.cost).toBe(3);
  });

  it('ignores stale field extraction settings for extraction-only estimates', () => {
    const result = calculatePricing({
      ...inputs, documentMode: 'basic_sync', modelName: 'unknown', customInputTokens: -1,
      customCachedInputTokens: Infinity, tokenPricing: { input_per_mtok: -10 }
    });
    expect(result.total).toBe(1.5);
  });

  it.each<TokenDeploymentType>(['global', 'regional', 'data_zone'])('supports all families with explicit %s rates and cached tokens', deploymentType => {
    for (const model of pricingConfig.models) {
      const result = calculatePricing({
        ...inputs, deploymentType, modelName: model.name, customInputTokens: 1000,
        customCachedInputTokens: 400, customOutputTokens: 100,
        tokenPricing: { input_per_mtok: 2, cached_input_per_mtok: 0.5, output_per_mtok: 8 }
      });
      expect(result.fe.inputTokens).toBe(1000000);
      expect(result.fe.uncachedInputTokens).toBe(600000);
      expect(result.fe.cachedInputTokens).toBe(400000);
      expect(result.fe.inputCost).toBeCloseTo(1.2);
      expect(result.fe.cachedInputCost).toBeCloseTo(0.2);
      expect(result.fe.outputCost).toBeCloseTo(0.8);
      expect(result.fe.cost).toBeCloseTo(2.2);
      expect(result.fe.totalTokens).toBe(1100000);
      expect(result.total).toBeCloseTo(8.2);
    }
  });

  it('requires missing cached rates only when cached tokens are used', () => {
    expect(calculatePricing(inputs).total).not.toBeNull();
    const result = calculatePricing({
      ...inputs, modelName: 'gpt-6.1-astra', customCachedInputTokens: 100,
      tokenPricing: { input_per_mtok: 2, output_per_mtok: 8 }
    });
    expect(result.total).toBeNull();
    expect(result.missingRates).toEqual(['Cached input token rate']);
    expect(result.fe.cachedInputCost).toBeNull();
  });

  it('does not silently price unknown models or missing family rates', () => {
    const result = calculatePricing({ ...inputs, modelName: 'gpt-6.1-astra' });
    expect(result.total).toBeNull();
    expect(result.fe.cost).toBeNull();
    expect(result.knownSubtotal).toBe(6);
    expect(result.missingRates).toEqual(['Input token rate', 'Output token rate']);
    expect(() => calculatePricing({ ...inputs, modelName: 'unknown' })).toThrow('not found');
  });

  it('accepts genuinely free rates and zero tokens', () => {
    const result = calculatePricing({
      ...inputs, modelName: 'gpt-5', customInputTokens: 0, customOutputTokens: 0
    });
    expect(result.fe.cost).toBe(0);
    expect(result.total).toBe(6);
    expect(calculatePricing({
      ...inputs, modelName: 'gpt-5', tokenPricing: {
        input_per_mtok: 0, output_per_mtok: 0, cached_input_per_mtok: 0
      }
    }).total).toBe(6);
  });

  it('does not discount embeddings when input tokens are cached', () => {
    const result = calculatePricing({
      ...inputs, embeddingsEnabled: true, customInputTokens: 1000, customCachedInputTokens: 1000,
      tokenPricing: { cached_input_per_mtok: 0.1 }
    });
    expect(result.fe.uncachedInputTokens).toBe(0);
    expect(result.embeddings.totalTokens).toBe(1000000);
    expect(result.embeddings.cost).toBeCloseTo(0.02);
  });

  it.each(['audio', 'video'] as const)('uses exact hourly %s rates and context quantities', fileType => {
    const result = calculatePricing({ ...inputs, fileType, quantity: 60 });
    expect(result.ce.cost).toBeCloseTo(fileType === 'audio' ? 0.36 : 1);
    expect(result.ctx.tokens).toBeCloseTo(fileType === 'audio' ? 100000 : 1000000);
  });

  it.each<TokenDeploymentType>(['global', 'regional', 'data_zone'])('uses published %s model and embedding prices', deploymentType => {
    const result = calculatePricing({
      ...inputs, deploymentType, embeddingsEnabled: true,
      customInputTokens: 1000, customCachedInputTokens: 400, customOutputTokens: 100
    });
    const regional = deploymentType !== 'global';
    expect(result.fe.cost).toBeCloseTo(regional ? 3.3 : 3);
    expect(result.embeddings.cost).toBeCloseTo(regional ? .022 : .02);
  });

  it.each(Object.keys(invoiceBenchmark.models).filter(name => invoiceBenchmark.models[name].status === 'measured'))('uses all measured invoice categories for %s without inferred embedding charges', modelName => {
    const measured = invoiceBenchmark.models[modelName].perPage!;
    const result = calculatePricing({ ...inputs, modelName, quantity: 3, embeddingsEnabled: true });
    expect(result.fe.inputTokens).toBeCloseTo(measured.input * 3);
    expect(result.fe.cachedInputTokens).toBeCloseTo((measured.cached_input ?? 0) * 3);
    expect(result.fe.outputTokens).toBeCloseTo(measured.output * 3);
    expect(result.ctx.tokens).toBe(measured.contextualization * 3);
    expect(result.embeddings).toEqual({ totalTokens: 0, cost: 0 });
    expect(calculatePricing({
      ...inputs, modelName, quantity: 3, embeddingsEnabled: true,
      customCachedInputTokens: 0, embeddingsTokensPerCall: 100
    }).embeddings.totalTokens).toBe(300);
  });

  it('converts text characters to pages for model tokens, not contextualization', () => {
    const result = calculatePricing({ ...inputs, fileType: 'text', quantity: 3001 });
    expect(result.ce.units).toBe(2);
    expect(result.ce.cost).toBe(0);
    expect(result.fe.inputTokens).toBe(5200);
    expect(result.ctx.tokens).toBe(3001);
  });

  it('marks PTU totals incomplete rather than treating tokens as free', () => {
    const result = calculatePricing({ ...inputs, deploymentType: 'ptu', embeddingsEnabled: true });
    expect(result.total).toBeNull();
    expect(result.fe.cost).toBeNull();
    expect(result.embeddings.cost).toBeNull();
    expect(result.knownSubtotal).toBe(6);
  });

  it.each([
    { quantity: -1 }, { quantity: Infinity }, { customInputTokens: -1 },
    { customOutputTokens: NaN }, { customCachedInputTokens: 2601 },
    { tokenPricing: { input_per_mtok: -1 } }, { tokenPricing: { cached_input_per_mtok: Infinity } }
  ])('rejects invalid quantities, cache counts, and rates: %j', override => {
    expect(() => calculatePricing({ ...inputs, ...override })).toThrow();
  });

  it('prices mixed asynchronous tiers without multiplying field extraction by the number of tiers', () => {
    const result = calculatePricing({
      ...inputs, quantity: 6000, documentQuantities: { minimal: 2000, basic: 3000, standard: 1000 }
    });
    expect(result.ce.cost).toBeCloseTo(8.02);
    expect(result.fe.inputTokens).toBe(6000 * 2600);
    expect(result.ctx.tokens).toBe(6000000);
  });

  it.each(['document', 'image', 'audio', 'video', 'text'] as const)('scales every optional component to the separate %s field volume', fileType => {
    const baseline = calculatePricing({ ...inputs, fileType, quantity: 6000, embeddingsEnabled: true });
    const result = calculatePricing({
      ...inputs, fileType, quantity: 6000, fieldQuantity: 3000, embeddingsEnabled: true
    });
    expect(result.ce.cost).toBe(baseline.ce.cost);
    expect(result.fe.inputTokens).toBe(baseline.fe.inputTokens / 2);
    expect(result.fe.outputTokens).toBe(baseline.fe.outputTokens / 2);
    expect(result.embeddings.totalTokens).toBe(baseline.embeddings.totalTokens / 2);
    expect(result.ctx.tokens).toBe(baseline.ctx.tokens / 2);
  });

  it('accepts zero field volume without requiring missing model rates', () => {
    const result = calculatePricing({
      ...inputs, fieldQuantity: 0, modelName: 'gpt-6.1-astra', embeddingsEnabled: true
    });
    expect(result.total).toBe(5);
    expect(result.missingRates).toEqual([]);
  });

  it.each([
    { fieldQuantity: -1 }, { fieldQuantity: Infinity }, { fieldQuantity: 1001 },
    { documentQuantities: { minimal: 0, basic: 0, standard: 500 } },
    { documentQuantities: { minimal: -1, basic: 1, standard: 1000 } },
    { documentQuantities: { minimal: NaN, basic: 0, standard: 1000 } },
    { processingMode: 'sync' as const, documentQuantities: { minimal: 1000, basic: 0, standard: 0 } }
  ])('rejects invalid tier and field volumes: %j', override => {
    expect(() => calculatePricing({ ...inputs, ...override })).toThrow();
  });

  it('prices mixed Basic and Standard tiers in Sync mode and excludes field extraction', () => {
    const result = calculatePricing({
      ...inputs, quantity: 5000, processingMode: 'sync',
      documentQuantities: { minimal: 0, basic: 2000, standard: 3000 },
      embeddingsEnabled: true, contextualizationType: 'advanced', modelName: 'unknown'
    });
    expect(result.ce.cost).toBe(25.5);
    expect(result.total).toBe(25.5);
    expect(result.fe.totalTokens).toBe(0);
    expect(result.ctx.cost).toBe(0);
    expect(result.embeddings.cost).toBe(0);
  });

  it('uses explicit processing mode instead of a legacy tier-mode setting', () => {
    expect(calculatePricing({ ...inputs, documentMode: 'basic_sync', processingMode: 'async', fieldExtractionEnabled: false }).ce.cost).toBe(1);
    expect(calculatePricing({ ...inputs, documentMode: 'standard', processingMode: 'sync' }).total).toBe(7.5);
  });

  it.each(['image', 'audio', 'video'] as const)('rejects unsupported Sync %s calculations', fileType => {
    expect(() => calculatePricing({ ...inputs, fileType, processingMode: 'sync' })).toThrow('Document and Text only');
  });

  it('supports Text in Sync without field extraction charges', () => {
    const result = calculatePricing({
      ...inputs, fileType: 'text', quantity: 3000000, processingMode: 'sync',
      embeddingsEnabled: true, modelName: 'unknown'
    });
    expect(result.total).toBe(0);
    expect(result.fe.totalTokens).toBe(0);
    expect(result.ctx.tokens).toBe(0);
    expect(result.embeddings.totalTokens).toBe(0);
  });
});
