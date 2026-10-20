import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import PricingCalculator from './PricingCalculator';
import { invoiceBenchmark, pricingConfig } from '@/lib/pricing-config';

const persisted = {
  clear: () => localStorage.clear(),
  set: (key: string, value: unknown) => localStorage.setItem(`cu-pricing:${key}`, JSON.stringify(value))
};

beforeEach(() => {
  persisted.clear();
  persisted.set('calc-model', 'gpt-4o');
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

const breakdown = () => within(screen.getByRole('region', { name: 'Your monthly estimate' }));

describe('Pricing calculator UI', () => {
  it('defaults new visitors to GPT-6.1 Sol with Global deployment', () => {
    persisted.clear();
    render(<PricingCalculator />);
    expect(screen.getByLabelText('Model').textContent).toBe('gpt-6.1-sol');
    expect(screen.getByLabelText('Deployment type').textContent).toBe('Global');
    expect(breakdown().getByText('$12.15')).toBeTruthy();
    expect(screen.getByText('Model pricing advanced settings - caching and pricing')).toBeTruthy();
    expect(screen.queryByText(/negotiated/i)).toBeNull();
  });

  it('uses Azure Content Understanding branding without AI', () => {
    render(<PricingCalculator />);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Pricing calculator');
    expect(screen.getByRole('heading', { name: 'Azure Content Understanding' })).toBeTruthy();
  });

  it('uses one complete model selector and applies matching defaults on selection', () => {
    persisted.set('calc-file-type', 'image');
    render(<PricingCalculator />);
    expect(screen.queryByLabelText('Model family')).toBeNull();
    fireEvent.keyDown(screen.getByLabelText('Model'), { key: ' ' });
    expect(screen.getAllByRole('option').map(option => option.textContent)).toEqual(
      pricingConfig.models.map(model => model.name)
    );
    fireEvent.click(screen.getByRole('option', { name: 'gpt-5.4-mini' }));
    expect((screen.getByLabelText('Total input tokens / image') as HTMLInputElement).value).toBe('3476');
    expect((screen.getByLabelText('Output tokens / image') as HTMLInputElement).value).toBe('170');
    fireEvent.keyDown(screen.getByLabelText('Model'), { key: ' ' });
    fireEvent.click(screen.getByRole('option', { name: 'gpt-6.1-astra' }));
    expect((screen.getByLabelText('Total input tokens / image') as HTMLInputElement).value).toBe('1043');
    expect((screen.getByLabelText('Output tokens / image') as HTMLInputElement).value).toBe('170');
  });

  it('restores a previously selected GPT-6 placeholder to a supported model', () => {
    persisted.set('calc-model', 'GPT-6 (custom deployment)');
    render(<PricingCalculator />);
    expect(screen.getByLabelText('Model').textContent).toBe('gpt-6-sol');
    expect(screen.queryByText(/Model .* not found/)).toBeNull();
  });

  it('shows public prices and updates totals for cached input without double billing', () => {
    render(<PricingCalculator />);
    expect(screen.getByText('public Azure OpenAI pricing')).toBeTruthy();
    expect(screen.getByLabelText('Cached input ($ / million tokens)').getAttribute('placeholder')).toBe('Public: 1.25');
    fireEvent.change(screen.getByLabelText('Cached input tokens / page'), { target: { value: '1000' } });
    expect(screen.queryByText(/Missing: Cached input token rate/)).toBeNull();
    fireEvent.change(screen.getByLabelText('Cached input ($ / million tokens)'), { target: { value: '1' } });
    expect(screen.queryByText(/Not a complete estimate/)).toBeNull();
    expect(breakdown().getByText('$11.95')).toBeTruthy();
  });

  it('shows measured invoice defaults, supports overrides, and resets every token category', () => {
    persisted.set('calc-model', 'gpt-4.1');
    render(<PricingCalculator />);
    const measured = invoiceBenchmark.models['gpt-4.1'].perPage!;
    expect(screen.getByText(/Document defaults measured using prebuilt-invoice/)).toBeTruthy();
    expect((screen.getByLabelText('Total input tokens / page') as HTMLInputElement).value).toBe(String(measured.input));
    expect((screen.getByLabelText('Cached input tokens / page') as HTMLInputElement).value).toBe('0');
    const embeddings = screen.getByLabelText('Embedding tokens / page') as HTMLInputElement;
    expect(embeddings.value).toBe('0');
    fireEvent.change(embeddings, { target: { value: '100' } });
    fireEvent.change(screen.getByLabelText('Cached input tokens / page'), { target: { value: '100' } });
    fireEvent.click(screen.getByRole('button', { name: 'Reset token estimates' }));
    expect(embeddings.value).toBe('0');
    expect((screen.getByLabelText('Cached input tokens / page') as HTMLInputElement).value).toBe('0');
    expect(within(breakdown().getByText('Model cached input').closest('div')!).getByText('$0')).toBeTruthy();
  });

  it('preserves custom pricing overrides for a model and deployment', () => {
    persisted.set('calc-token-rates-v2', { 'gpt-4o:global': { input_per_mtok: 0 } });
    render(<PricingCalculator />);
    expect((screen.getByLabelText('Uncached input ($ / million tokens)') as HTMLInputElement).value).toBe('0');
    expect(breakdown().getByText('$6.95')).toBeTruthy();
  });

  it.each([
    'gpt-5.6-tera', 'gpt-5.6-luna', 'gpt-5.6-sol',
    'gpt-6-luna', 'gpt-6-sol', 'gpt-6-astra'
  ])('shows measured South Central preview defaults for %s', modelName => {
    persisted.set('calc-model', modelName);
    render(<PricingCalculator />);
    const measurement = invoiceBenchmark.models[modelName];
    expect(measurement.status).toBe('measured');
    expect(screen.getByText(/Document defaults measured using prebuilt-invoice/).textContent)
      .toContain('in southcentralus using API 2026-06-01-preview');
    expect((screen.getByLabelText('Total input tokens / page') as HTMLInputElement).value)
      .toBe(String(measurement.perPage!.input));
    expect((screen.getByLabelText('Output tokens / page') as HTMLInputElement).value)
      .toBe(String(measurement.perPage!.output));
    expect((screen.getByLabelText('Cached input tokens / page') as HTMLInputElement).value)
      .toBe('0');
    expect((screen.getByLabelText('Embedding tokens / page') as HTMLInputElement).value).toBe('0');
    expect(screen.queryByText(/Token defaults are heuristic/)).toBeNull();
  });

  it('keeps GA measurement provenance when preview models are added', () => {
    persisted.set('calc-model', 'gpt-4.1');
    render(<PricingCalculator />);
    expect(screen.getByText(/Document defaults measured using prebuilt-invoice/).textContent)
      .toContain('in eastus2 using API 2025-11-01');
  });

  it('does not present GPT-6.1 document-only support as a measured invoice baseline', () => {
    persisted.set('calc-model', 'gpt-6.1-sol');
    render(<PricingCalculator />);
    expect(screen.getByText(/Token defaults are heuristic/).textContent)
      .toContain('Not supported by prebuilt-invoice in southcentralus with API 2026-06-01-preview');
    expect(screen.queryByText(/Document defaults measured using prebuilt-invoice/)).toBeNull();
  });

  it('displays invalid cached token counts instead of a total', () => {
    render(<PricingCalculator />);
    fireEvent.change(screen.getByLabelText('Cached input tokens / page'), { target: { value: '3000' } });
    expect(screen.getByRole('alert').textContent).toContain('cannot exceed');
    expect(screen.queryByText('Estimated Total Cost')).toBeNull();
  });

  it('honors persisted advanced contextualization with a mini model', () => {
    persisted.set('calc-context', 'advanced');
    persisted.set('calc-model', 'gpt-4o-mini');
    render(<PricingCalculator />);
    expect(screen.getByText('Contextualization (advanced)')).toBeTruthy();
    expect(breakdown().getByText('$8.50')).toBeTruthy();
  });

  it.each(['basic_sync', 'standard_sync'])('disables field extraction and hides model/context controls in %s', mode => {
    persisted.set('calc-document-mode', mode);
    persisted.set('calc-model', 'gpt-6-sol');
    render(<PricingCalculator />);
    const toggle = screen.getByRole('switch', { name: 'Enable field extraction' });
    expect(toggle.hasAttribute('disabled')).toBe(true);
    expect(toggle.getAttribute('aria-checked')).toBe('false');
    expect(screen.queryByLabelText('Cached input tokens / page')).toBeNull();
    expect(screen.queryByLabelText('Contextualization level')).toBeNull();
    expect(screen.queryByText(/Not a complete estimate/)).toBeNull();
    expect(breakdown().getByText(mode === 'basic_sync' ? '$1.50' : '$7.50')).toBeTruthy();
  });

  it('shows a known subtotal for missing GPT-6 rates, not a complete total', () => {
    persisted.set('calc-model', 'gpt-6.1-astra');
    persisted.set('calc-deployment', 'regional');
    render(<PricingCalculator />);
    expect(breakdown().getByText('Known subtotal (incomplete)')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('Input token rate, Output token rate');
  });

  it('honors zero input/output tokens', () => {
    render(<PricingCalculator />);
    fireEvent.change(screen.getByLabelText('Total input tokens / page'), { target: { value: '0' } });
    fireEvent.change(screen.getByLabelText('Output tokens / page'), { target: { value: '0' } });
    expect(breakdown().getByText('$6.00')).toBeTruthy();
  });

  it('adds document tier volumes and uses the sum for default field extraction', () => {
    render(<PricingCalculator />);
    expect((screen.getByLabelText('Monthly content extraction volume') as HTMLInputElement).readOnly).toBe(true);
    fireEvent.change(screen.getByLabelText('Basic volume'), { target: { value: '3000' } });
    expect(screen.queryByLabelText('Minimal volume')).toBeNull();
    expect(screen.getByText('Read')).toBeTruthy();
    expect(screen.getByText('Layout')).toBeTruthy();
    expect((screen.getByLabelText('Monthly content extraction volume') as HTMLInputElement).value).toBe('4000');
    expect((screen.getByLabelText('Monthly field extraction volume') as HTMLInputElement).value).toBe('4000');
    const row = breakdown().getByText('Content Extraction').closest('div')!;
    expect(within(row).getByText('$8')).toBeTruthy();
    expect(screen.getByText(/Document file type, 4,000 pages of input/)).toBeTruthy();
  });

  it('uses a separate field volume without charging content extraction twice', () => {
    render(<PricingCalculator />);
    fireEvent.change(screen.getByLabelText('Monthly field extraction volume'), { target: { value: '500' } });
    expect(breakdown().getByText('$9.23')).toBeTruthy();
    expect((screen.getByLabelText('Standard volume') as HTMLInputElement).value).toBe('1000');
    expect(screen.getByText(/Field extraction enabled for 500 pages/)).toBeTruthy();
  });

  it('rejects field volumes greater than content volumes', () => {
    render(<PricingCalculator />);
    fireEvent.change(screen.getByLabelText('Monthly field extraction volume'), { target: { value: '2000' } });
    expect(screen.getByRole('alert').textContent).toContain('cannot exceed content extraction volume');
    const input = screen.getByLabelText('Monthly field extraction volume');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(input.getAttribute('aria-describedby')).toContain(screen.getByRole('alert').id);
    expect(input.closest('.calc-field')?.contains(screen.getByRole('alert'))).toBe(true);
    expect(screen.queryByText('Estimated Total Cost')).toBeNull();
    fireEvent.change(input, { target: { value: '1000' } });
    expect(input.hasAttribute('aria-invalid')).toBe(false);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText('Estimated Total Cost')).toBeTruthy();
  });

  it('reveals an inline field-volume error even when settings were collapsed', () => {
    persisted.set('calc-field-extraction-expanded', false);
    persisted.set('calc-field-volumes-v1', { document: 2000 });
    render(<PricingCalculator />);
    expect(screen.getByRole('spinbutton', { name: 'Monthly field extraction volume' }).getAttribute('aria-invalid')).toBe('true');
    expect(screen.getByRole('alert').textContent).toContain('cannot exceed content extraction volume');
  });

  it('excludes saved Minimal allocations and explains that they must be reallocated', () => {
    persisted.set('calc-document-volumes-v1', { minimal: 2000, basic: 3000, standard: 1000 });
    render(<PricingCalculator />);
    expect(screen.queryByLabelText('Minimal volume')).toBeNull();
    expect((screen.getByLabelText('Monthly content extraction volume') as HTMLInputElement).value).toBe('4000');
    expect(screen.getByRole('status').textContent).toContain('Reallocate');
    expect(within(breakdown().getByText('Content Extraction').closest('div')!).getByText('$8')).toBeTruthy();
  });

  it('enforces the specified 10,000,000 billing-unit limit without a partial total', () => {
    render(<PricingCalculator />);
    fireEvent.change(screen.getByLabelText('Standard volume'), { target: { value: '10000001' } });
    expect(screen.getByRole('alert').textContent).toContain('between 0 and 10,000,000');
    expect(screen.queryByText('Estimated Total Cost')).toBeNull();
  });

  it('restores imported basic document volume into the matching tier', () => {
    persisted.set('calc-document-mode', 'basic');
    persisted.set('calc-quantity', 2500);
    render(<PricingCalculator />);
    expect((screen.getByLabelText('Basic volume') as HTMLInputElement).value).toBe('2500');
    expect((screen.getByLabelText('Standard volume') as HTMLInputElement).value).toBe('0');
    expect((screen.getByLabelText('Monthly content extraction volume') as HTMLInputElement).value).toBe('2500');
  });

  it.each([
    ['text', 'Text', '1000', 'page'],
    ['image', 'Image', '1', 'image'],
    ['audio', 'Audio', '60', 'minute'],
    ['video', 'Video', '60', 'minute']
  ])('updates the %s state, units, defaults, and document-only controls', (type, label, quantity, unit) => {
    render(<PricingCalculator />);
    fireEvent.keyDown(screen.getByLabelText('File type'), { key: ' ' });
    fireEvent.click(screen.getByRole('option', { name: label }));
    expect(screen.getByRole('heading', { name: `Content Understanding for ${label}` })).toBeTruthy();
    expect((screen.getByLabelText('Monthly content extraction volume') as HTMLInputElement).value).toBe(quantity);
    expect(screen.getByLabelText(`Total input tokens / ${unit}`)).toBeTruthy();
    expect(screen.queryByLabelText('Embeddings model')).toBeNull();
    expect(screen.queryByLabelText('Standard volume')).toBeNull();
    if (type === 'text') expect(screen.getByText(/1 page = 3,000 UTF-16 characters/)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('keeps the estimate and configuration summary when settings are collapsed', () => {
    render(<PricingCalculator />);
    fireEvent.click(screen.getByRole('button', { name: 'Hide field extraction settings' }));
    expect(screen.queryByRole('combobox', { name: 'Model' })).toBeNull();
    expect(breakdown().getByText('$13.45')).toBeTruthy();
    expect(screen.getByText(/Field extraction enabled for 1,000 pages/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Show field extraction settings' }));
    expect(screen.getByRole('combobox', { name: 'Model' })).toBeTruthy();
  });

  it('removes optional charges when field extraction is disabled', () => {
    render(<PricingCalculator />);
    fireEvent.click(screen.getByRole('switch', { name: 'Enable field extraction' }));
    expect(screen.queryByLabelText('Monthly field extraction volume')).toBeNull();
    expect(breakdown().queryByText('Model output')).toBeNull();
    expect(breakdown().getByText('$5.00')).toBeTruthy();
    expect(screen.getByText(/Field extraction disabled/)).toBeTruthy();
  });

  it('shows small token quantities precisely instead of rounding billable usage to zero', () => {
    render(<PricingCalculator />);
    fireEvent.change(screen.getByLabelText('Monthly field extraction volume'), { target: { value: '1' } });
    expect(screen.getByText('0.0026')).toBeTruthy();
    expect(screen.getByText('0.00009')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('restores asynchronous tier allocations after switching to sync and back', () => {
    render(<PricingCalculator />);
    fireEvent.change(screen.getByLabelText('Basic volume'), { target: { value: '2000' } });
    fireEvent.keyDown(screen.getByLabelText('Processing mode'), { key: ' ' });
    expect(screen.getAllByRole('option').map(option => option.textContent)).toEqual(['Async', 'Sync']);
    fireEvent.click(screen.getByRole('option', { name: 'Sync' }));
    expect(screen.getByRole('switch', { name: 'Enable field extraction' }).getAttribute('aria-checked')).toBe('false');
    expect((screen.getByLabelText('Basic volume') as HTMLInputElement).value).toBe('2000');
    expect((screen.getByLabelText('Standard volume') as HTMLInputElement).value).toBe('1000');
    expect(breakdown().getByText('$10.50')).toBeTruthy();
    expect((screen.getByLabelText('Monthly content extraction volume') as HTMLInputElement).value).toBe('3000');
    fireEvent.keyDown(screen.getByLabelText('Processing mode'), { key: ' ' });
    fireEvent.click(screen.getByRole('option', { name: 'Async' }));
    expect((screen.getByLabelText('Basic volume') as HTMLInputElement).value).toBe('2000');
    expect((screen.getByLabelText('Standard volume') as HTMLInputElement).value).toBe('1000');
    expect(screen.getByRole('switch', { name: 'Enable field extraction' }).getAttribute('aria-checked')).toBe('true');
  });

  it('keeps Basic and Standard editable in Sync mode and saves the processing mode separately', () => {
    render(<PricingCalculator />);
    fireEvent.keyDown(screen.getByLabelText('Processing mode'), { key: ' ' });
    fireEvent.click(screen.getByRole('option', { name: 'Sync' }));
    fireEvent.change(screen.getByLabelText('Basic volume'), { target: { value: '2000' } });
    fireEvent.change(screen.getByLabelText('Standard volume'), { target: { value: '3000' } });
    expect(breakdown().getByText('$25.50')).toBeTruthy();
    expect((screen.getByLabelText('Monthly content extraction volume') as HTMLInputElement).value).toBe('5000');
    expect(JSON.parse(localStorage.getItem('cu-pricing:calc-processing-mode')!)).toBe('sync');
    expect(screen.getByText(/Sync processing: 2,000 Basic/)).toBeTruthy();
  });

  it('retains a disabled field extraction preference across processing-mode changes', () => {
    persisted.set('calc-field-extraction-enabled', false);
    render(<PricingCalculator />);
    fireEvent.keyDown(screen.getByLabelText('Processing mode'), { key: ' ' });
    fireEvent.click(screen.getByRole('option', { name: 'Sync' }));
    fireEvent.keyDown(screen.getByLabelText('Processing mode'), { key: ' ' });
    fireEvent.click(screen.getByRole('option', { name: 'Async' }));
    expect(screen.getByRole('switch', { name: 'Enable field extraction' }).getAttribute('aria-checked')).toBe('false');
  });

  it('defaults measured models to uncached billing while allowing explicit cache estimates', () => {
    persisted.set('calc-model', 'gpt-4.1');
    render(<PricingCalculator />);
    const input = invoiceBenchmark.models['gpt-4.1'].perPage!.input;
    const inputCost = input * 1000 / 1000000 * pricingConfig.models.find(model => model.name === 'gpt-4.1')!.pricing.global.input_per_mtok!;
    const row = breakdown().getByText('Model uncached input').closest('div')!;
    expect(Number(row.querySelector('dd')!.textContent!.replace('$', ''))).toBeCloseTo(inputCost, 4);
    fireEvent.change(screen.getByLabelText('Cached input tokens / page'), { target: { value: '1000' } });
    expect((screen.getByLabelText('Cached input tokens / page') as HTMLInputElement).value).toBe('1000');
    expect(within(breakdown().getByText('Model cached input').closest('div')!).getByText('$0.5')).toBeTruthy();
  });

  it('links directly to pricing pages instead of the Azure calculator', () => {
    render(<PricingCalculator />);
    expect(screen.getByRole('link', { name: 'Content Understanding pricing page' }).getAttribute('href'))
      .toBe('https://azure.microsoft.com/en-us/pricing/details/content-understanding/');
    expect(screen.getByRole('link', { name: 'Azure OpenAI pricing page' }).getAttribute('href'))
      .toBe('https://azure.microsoft.com/en-us/pricing/details/azure-openai/');
    expect(screen.getAllByRole('link').some(link => link.getAttribute('href')?.includes('/pricing/calculator/'))).toBe(false);
  });

  it('limits Sync file types to Document and Text and restores all types in Async', () => {
    render(<PricingCalculator />);
    fireEvent.keyDown(screen.getByLabelText('Processing mode'), { key: ' ' });
    fireEvent.click(screen.getByRole('option', { name: 'Sync' }));
    fireEvent.keyDown(screen.getByLabelText('File type'), { key: ' ' });
    expect(screen.getAllByRole('option').map(option => option.textContent)).toEqual(['Document', 'Text']);
    fireEvent.click(screen.getByRole('option', { name: 'Text' }));
    expect(screen.getByLabelText('Processing mode').textContent).toBe('Sync');
    expect(screen.getByRole('switch', { name: 'Enable field extraction' }).hasAttribute('disabled')).toBe(true);
    expect(screen.queryByLabelText('Model')).toBeNull();
    expect(breakdown().getByText('$0.00')).toBeTruthy();
    fireEvent.keyDown(screen.getByLabelText('Processing mode'), { key: ' ' });
    fireEvent.click(screen.getByRole('option', { name: 'Async' }));
    expect(screen.getByRole('switch', { name: 'Enable field extraction' }).getAttribute('aria-checked')).toBe('true');
    fireEvent.keyDown(screen.getByLabelText('File type'), { key: ' ' });
    expect(screen.getAllByRole('option').map(option => option.textContent)).toEqual(['Document', 'Text', 'Image', 'Audio', 'Video']);
  });

  it.each(['image', 'audio', 'video'])('keeps %s in Async and disables Sync even with stale saved settings', fileType => {
    persisted.set('calc-file-type', fileType);
    persisted.set('calc-processing-mode', 'sync');
    render(<PricingCalculator />);
    expect(screen.getByLabelText('Processing mode').textContent).toBe('Async');
    expect(screen.queryByRole('alert')).toBeNull();
    fireEvent.keyDown(screen.getByLabelText('Processing mode'), { key: ' ' });
    expect(screen.getByRole('option', { name: 'Sync' }).getAttribute('aria-disabled')).toBe('true');
  });

  it('defaults document content and field volumes to 1,000 actual pages', () => {
    render(<PricingCalculator />);
    expect((screen.getByLabelText('Monthly content extraction volume') as HTMLInputElement).value).toBe('1000');
    expect((screen.getByLabelText('Standard volume') as HTMLInputElement).value).toBe('1000');
    expect((screen.getByLabelText('Monthly field extraction volume') as HTMLInputElement).value).toBe('1000');
    expect(screen.getByLabelText('Monthly field extraction volume').getAttribute('max')).toBe('1000');
    expect(document.getElementById('volume-standard-unit')!.textContent).toBe('pages');
    expect(screen.queryByText('x 1,000 pages')).toBeNull();
    expect(within(breakdown().getByText('Content Extraction').closest('div')!).getByText('$5')).toBeTruthy();
  });

  it('converts actual text pages into characters without multiplying model tokens by 1,000', () => {
    render(<PricingCalculator />);
    fireEvent.keyDown(screen.getByLabelText('File type'), { key: ' ' });
    fireEvent.click(screen.getByRole('option', { name: 'Text' }));
    fireEvent.change(screen.getByLabelText('Monthly content extraction volume'), { target: { value: '500' } });
    expect(JSON.parse(localStorage.getItem('cu-pricing:calc-quantity')!)).toBe(1500000);
    expect((screen.getByLabelText('Monthly field extraction volume') as HTMLInputElement).value).toBe('500');
    expect(within(breakdown().getByText('Model uncached input').closest('div')!).getByText('$3.25')).toBeTruthy();
    expect(within(breakdown().getByText('Contextualization (standard)').closest('div')!).getByText('$1.5')).toBeTruthy();
    expect(screen.getByText(/Text file type, 500 pages of input/)).toBeTruthy();
  });
});
