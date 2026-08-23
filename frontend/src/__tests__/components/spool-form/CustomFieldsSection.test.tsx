import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { render } from '../../utils';
import { CustomFieldsSection } from '../../../components/spool-form/CustomFieldsSection';
import { defaultFormData } from '../../../components/spool-form/types';
import type { CustomFieldDef } from '../../../api/client';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      (opts?.defaultValue as string) ?? key,
  }),
}));

const field = (over: Partial<CustomFieldDef> = {}): CustomFieldDef => ({
  id: 1,
  key: 'kunde',
  name: 'Kunde',
  field_type: 'choice',
  options: ['Acme', 'Globex'],
  sort_order: 0,
  value_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  ...over,
});

describe('CustomFieldsSection', () => {
  it('renders nothing when no fields are defined', () => {
    const { container } = render(
      <CustomFieldsSection formData={defaultFormData} updateField={vi.fn()} fields={[]} />,
    );
    expect(container.querySelector('select')).toBeNull();
  });

  it('renders one select per field with its options', () => {
    render(<CustomFieldsSection formData={defaultFormData} updateField={vi.fn()} fields={[field()]} />);
    const select = screen.getByLabelText('Kunde') as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toEqual(['', 'Acme', 'Globex']);
  });

  it('merges the picked value into the existing custom_fields map', () => {
    const updateField = vi.fn();
    const formData = { ...defaultFormData, custom_fields: { charge: 'B' } };
    render(
      <CustomFieldsSection formData={formData} updateField={updateField} fields={[field()]} />,
    );
    fireEvent.change(screen.getByLabelText('Kunde'), { target: { value: 'Globex' } });
    expect(updateField).toHaveBeenCalledWith('custom_fields', { charge: 'B', kunde: 'Globex' });
  });

  it('keeps a stored value that is no longer an option selectable', () => {
    // Otherwise the select would silently fall back to the empty option and
    // the next save would wipe a value the user never touched.
    const formData = { ...defaultFormData, custom_fields: { kunde: 'Initech' } };
    render(<CustomFieldsSection formData={formData} updateField={vi.fn()} fields={[field()]} />);
    const select = screen.getByLabelText('Kunde') as HTMLSelectElement;
    expect(select.value).toBe('Initech');
    expect(Array.from(select.options).map((o) => o.value)).toContain('Initech');
  });

  it.each([
    ['text', 'text'],
    ['integer', 'number'],
    ['float', 'number'],
    ['datetime', 'datetime-local'],
  ])('renders a %s field as an <input type=%s>', (fieldType, inputType) => {
    const def = field({ id: 2, key: 'notiz', name: 'Notiz', field_type: fieldType, options: [] });
    render(<CustomFieldsSection formData={defaultFormData} updateField={vi.fn()} fields={[def]} />);
    const input = screen.getByLabelText('Notiz') as HTMLInputElement;
    expect(input.tagName).toBe('INPUT');
    expect(input.type).toBe(inputType);
  });

  it('types free text straight into the value map', () => {
    const updateField = vi.fn();
    const def = field({ id: 2, key: 'notiz', name: 'Notiz', field_type: 'text', options: [] });
    render(<CustomFieldsSection formData={defaultFormData} updateField={updateField} fields={[def]} />);
    fireEvent.change(screen.getByLabelText('Notiz'), { target: { value: 'Charge 42' } });
    expect(updateField).toHaveBeenCalledWith('custom_fields', { notiz: 'Charge 42' });
  });

  it.each(['integer_range', 'float_range'])('renders %s as a pair of bounds', (fieldType) => {
    const updateField = vi.fn();
    const def = field({ id: 4, key: 'temp', name: 'Temperatur', field_type: fieldType, options: [] });
    const formData = { ...defaultFormData, custom_fields: { temp: '200,230' } };
    render(<CustomFieldsSection formData={formData} updateField={updateField} fields={[def]} />);

    const low = screen.getByLabelText('Temperatur') as HTMLInputElement;
    const high = screen.getByLabelText('Temperatur maximum') as HTMLInputElement;
    expect(low.value).toBe('200');
    expect(high.value).toBe('230');

    fireEvent.change(high, { target: { value: '240' } });
    expect(updateField).toHaveBeenCalledWith('custom_fields', { temp: '200,240' });
  });

  it('emits nothing for a half-filled range', () => {
    // "200," is not something the backend can store, so the value stays empty
    // until both bounds are present.
    const updateField = vi.fn();
    const def = field({ id: 4, key: 'temp', name: 'Temperatur', field_type: 'integer_range', options: [] });
    render(<CustomFieldsSection formData={defaultFormData} updateField={updateField} fields={[def]} />);
    fireEvent.change(screen.getByLabelText('Temperatur'), { target: { value: '200' } });
    expect(updateField).toHaveBeenCalledWith('custom_fields', { temp: '' });
  });

  it('falls back to a text box for a timestamp the picker cannot show', () => {
    // A datetime-local input renders empty for a value carrying a UTC offset,
    // which would make a stored value look unset.
    const def = field({ id: 5, key: 'dt', name: 'Geoeffnet', field_type: 'datetime', options: [] });
    const formData = { ...defaultFormData, custom_fields: { dt: '2026-08-23T14:30:00+02:00' } };
    render(<CustomFieldsSection formData={formData} updateField={vi.fn()} fields={[def]} />);
    const input = screen.getByLabelText('Geoeffnet') as HTMLInputElement;
    expect(input.type).toBe('text');
    expect(input.value).toBe('2026-08-23T14:30:00+02:00');
  });

  it('uses the native picker for a plain timestamp', () => {
    const def = field({ id: 5, key: 'dt', name: 'Geoeffnet', field_type: 'datetime', options: [] });
    const formData = { ...defaultFormData, custom_fields: { dt: '2026-08-23T14:30:00' } };
    render(<CustomFieldsSection formData={formData} updateField={vi.fn()} fields={[def]} />);
    const input = screen.getByLabelText('Geoeffnet') as HTMLInputElement;
    expect(input.type).toBe('datetime-local');
    // The DOM normalises a datetime-local value to minute precision; the stored
    // value keeps its seconds, and the save only sends fields the user changed.
    expect(input.value).toBe('2026-08-23T14:30');
  });

  it('renders a boolean field as a checkbox that stores an explicit false', () => {
    const updateField = vi.fn();
    const def = field({ id: 3, key: 'trocken', name: 'Trocken', field_type: 'boolean', options: [] });
    const formData = { ...defaultFormData, custom_fields: { trocken: 'true' } };
    render(<CustomFieldsSection formData={formData} updateField={updateField} fields={[def]} />);
    const box = screen.getByLabelText('Trocken') as HTMLInputElement;
    expect(box.type).toBe('checkbox');
    expect(box.checked).toBe(true);
    // Unchecking must store 'false', not '' -- "explicitly no" and "never
    // answered" are different answers.
    fireEvent.click(box);
    expect(updateField).toHaveBeenCalledWith('custom_fields', { trocken: 'false' });
  });
});
