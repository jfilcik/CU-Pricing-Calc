import publicPricing from './azure-openai-pricing.json';
import invoiceUsage from './invoice-token-defaults.json';

export type DocumentTier = 'minimal' | 'basic' | 'standard';
export type ProcessingMode = 'sync' | 'async';
export type DocumentMode = DocumentTier | 'basic_sync' | 'standard_sync';
export type ContextualizationType = 'standard' | 'advanced';
export type TokenDeploymentType = 'global' | 'regional' | 'data_zone';
export interface TokenPricing {
  input_per_mtok: number | null;
  cached_input_per_mtok: number | null;
  output_per_mtok: number | null;
}

export interface TokenUsageDefaults {
  in: number;
  out: number;
  cached_input?: number;
  contextualization?: number;
  embeddings?: number;
}

export interface InvoiceMeasurement {
  status: string;
  reason?: string;
  modelName?: string;
  apiVersion?: string;
  region?: string;
  measuredAt?: string;
  perPage?: {
    input: number;
    output: number;
    cached_input: number | null;
    contextualization: number;
    embeddings: number;
  };
}

export const publicPricingSnapshot = publicPricing;
export const invoiceBenchmark: {
  analyzerId: string; measuredAt: string; sampleUrl: string; sampleSha256: string;
  runsPerModel: number; apiVersion: string; region?: string; models: Record<string, InvoiceMeasurement>;
} = invoiceUsage;

export interface PricingConfig {
  ce: {
    document_per_1000_pages: Record<DocumentMode, number>;
    audio_per_minute: number;
    video_per_minute: number;
  };
  ctx: {
    per_mtok: Record<ContextualizationType, number>;
    units: {
      doc_page: number;
      text_page: number;
      text_chars: number;
      image: number;
      audio_minute: number;
      video_minute: number;
    };
  };
  models: Array<{
    name: string;
    class: 'regular' | 'mini';
    tokens_per_unit: {
      doc_page?: TokenUsageDefaults;
      text_page?: TokenUsageDefaults;
      image?: TokenUsageDefaults;
      audio_minute?: TokenUsageDefaults;
      video_minute?: TokenUsageDefaults;
    };
    pricing: {
      global: TokenPricing;
      regional: TokenPricing;
      data_zone: TokenPricing;
    };
  }>;
  embeddings: {
    [key: string]: {
      tokens_per_call: number;
      price_per_1k_tokens: number | null;
      pricing: Record<TokenDeploymentType, number | null>;
    };
  };
  page_from_chars: number;
}

export const pricingConfig: PricingConfig = {
  ce: {
    document_per_1000_pages: { minimal: 0.01, basic: 1, standard: 5, basic_sync: 1.5, standard_sync: 7.5 },
    audio_per_minute: 0.006,
    video_per_minute: 1 / 60
  },
  ctx: {
    per_mtok: { standard: 1, advanced: 3 },
    units: {
      doc_page: 1000,
      text_page: 1,
      text_chars: 1,
      image: 1000,
      audio_minute: 100000 / 60,
      video_minute: 1000000 / 60
    }
  },
  models: [
    {
      name: 'gpt-4o',
      class: 'regular',
      tokens_per_unit: {
        doc_page: { in: 2600, out: 90 },
        text_page: { in: 2600, out: 90 },
        image: { in: 1043, out: 170 },
        audio_minute: { in: 604, out: 19 },
        video_minute: { in: 10695, out: 3103 }
      },
      pricing: publicPricing.models['gpt-4o']
    },
    {
      name: 'gpt-4o-mini',
      class: 'mini', 
      tokens_per_unit: {
        doc_page: { in: 2600, out: 90 },
        text_page: { in: 2600, out: 90 },
        image: { in: 3476, out: 170 },
        audio_minute: { in: 604, out: 19 },
        video_minute: { in: 175575, out: 3103 }
      },
      pricing: publicPricing.models['gpt-4o-mini']
    },
    {
      name: 'gpt-4.1',
      class: 'regular',
      tokens_per_unit: {
        doc_page: { in: 2600, out: 90 },
        text_page: { in: 2600, out: 90 },
        image: { in: 1043, out: 170 },
        audio_minute: { in: 604, out: 19 },
        video_minute: { in: 10695, out: 3103 }
      },
      pricing: publicPricing.models['gpt-4.1']
    },
    {
      name: 'gpt-4.1-mini',
      class: 'mini',
      tokens_per_unit: {
        doc_page: { in: 2600, out: 90 },
        text_page: { in: 2600, out: 90 },
        image: { in: 3476, out: 170 },
        audio_minute: { in: 604, out: 19 },
        video_minute: { in: 175575, out: 3103 }
      },
      pricing: publicPricing.models['gpt-4.1-mini']
    },
    {
      name: 'gpt-4.1-nano',
      class: 'mini',
      tokens_per_unit: {
        doc_page: { in: 2600, out: 90 },
        text_page: { in: 2600, out: 90 },
        image: { in: 3476, out: 170 },
        audio_minute: { in: 604, out: 19 },
        video_minute: { in: 175575, out: 3103 }
      },
      pricing: publicPricing.models['gpt-4.1-nano']
    }
  ],
  embeddings: {
    'text-embedding-3-small': {
      tokens_per_call: 1500,
      ...publicPricing.embeddings['text-embedding-3-small']
    },
    'text-embedding-3-large': {
      tokens_per_call: 1500,
      ...publicPricing.embeddings['text-embedding-3-large']
    },
    'text-embedding-ada-002': {
      tokens_per_call: 1500,
      ...publicPricing.embeddings['text-embedding-ada-002']
    }
  },
  page_from_chars: 3000
};

export type ModelConfig = PricingConfig['models'][number];

// Reuse the matching GPT-4.1 size's planning estimates, not its token prices.
const additionalModels = [
  'gpt-6.1-luna', 'gpt-6.1-sol', 'gpt-6.1-astra',
  'gpt-6-luna', 'gpt-6-sol', 'gpt-6-astra',
  'gpt-5.6-tera', 'gpt-5.6-luna', 'gpt-5.6-sol',
  'gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.2', 'gpt-5.1',
  'gpt-5', 'gpt-5-mini', 'gpt-5-nano'
].map((name): ModelConfig => {
  const reference = name.endsWith('-nano') ? pricingConfig.models[4]
    : name.endsWith('-mini') ? pricingConfig.models[3] : pricingConfig.models[2];
  return {
    name,
    class: reference.class,
    tokens_per_unit: structuredClone(reference.tokens_per_unit),
    pricing: {
      global: { input_per_mtok: null, cached_input_per_mtok: null, output_per_mtok: null },
      regional: { input_per_mtok: null, cached_input_per_mtok: null, output_per_mtok: null },
      data_zone: { input_per_mtok: null, cached_input_per_mtok: null, output_per_mtok: null }
    }
  };
});
for (const version of ['2024-11-20', '2024-08-06']) {
  additionalModels.push({ ...structuredClone(pricingConfig.models[0]), name: `gpt-4o-${version}` });
}
pricingConfig.models.unshift(...additionalModels);

const publishedModelPrices: Record<string, ModelConfig['pricing']> = publicPricing.models;
for (const model of pricingConfig.models) {
  const prices = publishedModelPrices[model.name];
  if (!prices) throw new Error(`Public pricing snapshot has no entry for ${model.name}`);
  model.pricing = structuredClone(prices);
  const measured = invoiceBenchmark.models[model.name];
  if (measured?.status === 'measured' && measured.perPage) {
    model.tokens_per_unit.doc_page = {
      in: measured.perPage.input,
      out: measured.perPage.output,
      cached_input: measured.perPage.cached_input ?? 0,
      contextualization: measured.perPage.contextualization,
      embeddings: measured.perPage.embeddings
    };
  }
}

export const documentModeLabels: Record<DocumentMode, string> = {
  minimal: 'Document Minimal',
  basic: 'Document Basic (Read)',
  standard: 'Document Standard (Layout)',
  basic_sync: 'Document Basic Sync (Preview)',
  standard_sync: 'Document Standard Sync (Preview)'
};

export function isSyncMode(mode: DocumentMode): boolean {
  return mode === 'basic_sync' || mode === 'standard_sync';
}

export type FileType = 'document' | 'image' | 'video' | 'audio' | 'text';
export type DeploymentType = 'global' | 'regional' | 'data_zone' | 'ptu';

export const fileTypeLabels: Record<FileType, string> = {
  document: 'Document',
  image: 'Image', 
  video: 'Video',
  audio: 'Audio',
  text: 'Text'
};

export const fileTypeUnits: Record<FileType, string> = {
  document: 'pages',
  image: 'images',
  video: 'minutes', 
  audio: 'minutes',
  text: 'characters'
};

export const deploymentTypeLabels: Record<DeploymentType, string> = {
  global: 'Global',
  regional: 'Regional',
  data_zone: 'Data Zone',
  ptu: 'PTU'
};
