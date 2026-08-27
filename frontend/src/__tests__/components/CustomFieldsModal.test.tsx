/**
 * Tests for the custom-fields management modal.
 *
 * The interesting behaviour is the option editor: a select field is useless
 * without options, so save stays blocked until at least one exists, and the
 * delete confirmation has to warn when values would go with it.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { render } from '../utils';
import { CustomFieldsModal } from '../../components/CustomFieldsModal';
import type { CustomFieldDef } from '../../api/client';

const existing: CustomFieldDef = {
  id: 1,
  key: 'kunde',
  name: 'Kunde',
  field_type: 'choice',
  options: ['Acme', 'Globex'],
  sort_order: 0,
  value_count: 3,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

vi.mock('../../api/client', () => ({
  api: {
    getSettings: vi.fn().mockResolvedValue({}),
    getAuthStatus: vi.fn().mockResolvedValue({ auth_enabled: false }),
    getCustomFields: vi.fn(),
    createCustomField: vi.fn().mockResolvedValue({ id: 2 }),
    updateCustomField: vi.fn().mockResolvedValue({ id: 1 }),
    deleteCustomField: vi.fn().mockResolvedValue({ status: 'deleted', values_removed: 3 }),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts?.defaultValue as string) ?? key,
  }),
}));

import { api } from '../../api/client';

const mockedApi = api as unknown as {
  getCustomFields: ReturnType<typeof vi.fn>;
  createCustomField: ReturnType<typeof vi.fn>;
  updateCustomField: ReturnType<typeof vi.fn>;
  deleteCustomField: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  vi.clearAllMocks();
  mockedApi.getCustomFields.mockResolvedValue([existing]);
});

describe('CustomFieldsModal', () => {
  it('renders nothing while closed', () => {
    render(<CustomFieldsModal open={false} onClose={vi.fn()} />);
    expect(screen.queryByText('customFields.title')).toBeNull();
  });

  it('lists existing fields with their options and usage count', async () => {
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    expect(await screen.findByText('Kunde')).toBeTruthy();
    expect(screen.getByText('kunde')).toBeTruthy();
    expect(screen.getByText('Acme, Globex')).toBeTruthy();
    expect(screen.getByText('customFields.types.choice')).toBeTruthy();
    expect(screen.getByText('3')).toBeTruthy();
  });

  it('creates a plain text field with nothing but a name', async () => {
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByText('customFields.add'));

    // text is the default, so no option editor is in the way.
    expect(screen.queryByLabelText('customFields.options')).toBeNull();

    fireEvent.change(screen.getByLabelText('customFields.name'), { target: { value: 'Notiz' } });
    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() =>
      expect(mockedApi.createCustomField).toHaveBeenCalledWith({
        name: 'Notiz',
        // Derived from the name, since the key input was left untouched.
        key: 'notiz',
        field_type: 'text',
        options: [],
      }),
    );
  });

  it('fills the key from the name until the user edits it', async () => {
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByText('customFields.add'));

    const nameInput = screen.getByLabelText('customFields.name');
    const keyInput = screen.getByLabelText('customFields.key') as HTMLInputElement;

    fireEvent.change(nameInput, { target: { value: 'Kunde / Projekt' } });
    expect(keyInput.value).toBe('kunde_projekt');

    // Once touched it stops following the name — a deliberate key must not be
    // overwritten by the next keystroke in the name field.
    fireEvent.change(keyInput, { target: { value: 'customer' } });
    fireEvent.change(nameInput, { target: { value: 'Kunde / Projekt / 2026' } });
    expect(keyInput.value).toBe('customer');

    fireEvent.click(screen.getByText('common.save'));
    await waitFor(() =>
      expect(mockedApi.createCustomField).toHaveBeenCalledWith({
        name: 'Kunde / Projekt / 2026',
        key: 'customer',
        field_type: 'text',
        options: [],
      }),
    );
  });

  it('leaves the key empty for a name with no latin characters', async () => {
    // This is the case the input exists for: the backend would otherwise
    // derive a digest that nobody can type into an API call.
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByText('customFields.add'));

    fireEvent.change(screen.getByLabelText('customFields.name'), { target: { value: '客户' } });
    const keyInput = screen.getByLabelText('customFields.key') as HTMLInputElement;
    expect(keyInput.value).toBe('');

    fireEvent.change(keyInput, { target: { value: 'customer' } });
    fireEvent.click(screen.getByText('common.save'));
    await waitFor(() =>
      expect(mockedApi.createCustomField).toHaveBeenCalledWith({
        name: '客户',
        key: 'customer',
        field_type: 'text',
        options: [],
      }),
    );
  });

  it('omits the key when it was left empty, so the backend derives one', async () => {
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByText('customFields.add'));
    fireEvent.change(screen.getByLabelText('customFields.name'), { target: { value: '客户' } });
    fireEvent.click(screen.getByText('common.save'));
    await waitFor(() =>
      expect(mockedApi.createCustomField).toHaveBeenCalledWith({
        name: '客户',
        field_type: 'text',
        options: [],
      }),
    );
  });

  it('shows the key read-only when editing and never sends it', async () => {
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByLabelText('Edit Kunde'));

    const keyInput = screen.getByLabelText('customFields.key') as HTMLInputElement;
    expect(keyInput.value).toBe('kunde');
    expect(keyInput.disabled).toBe(true);
    expect(screen.getByText('customFields.keyLocked')).toBeTruthy();

    fireEvent.change(screen.getByLabelText('customFields.name'), { target: { value: 'Auftraggeber' } });
    fireEvent.click(screen.getByText('common.save'));
    await waitFor(() =>
      expect(mockedApi.updateCustomField).toHaveBeenCalledWith(1, {
        name: 'Auftraggeber',
        field_type: 'choice',
        options: ['Acme', 'Globex'],
      }),
    );
  });

  it('offers every field type', async () => {
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByText('customFields.add'));
    const typeSelect = screen.getByLabelText('customFields.type') as HTMLSelectElement;
    // Deliberately the same list, in the same order, as Spoolman's own
    // extra-field types.
    expect(Array.from(typeSelect.options).map((o) => o.value)).toEqual([
      'text',
      'integer',
      'integer_range',
      'float',
      'float_range',
      'datetime',
      'boolean',
      'choice',
    ]);
  });

  it('blocks save until a dropdown field has at least one option', async () => {
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByText('customFields.add'));

    fireEvent.change(screen.getByLabelText('customFields.name'), { target: { value: 'Charge' } });
    fireEvent.change(screen.getByLabelText('customFields.type'), { target: { value: 'choice' } });

    const save = screen.getByText('common.save').closest('button') as HTMLButtonElement;
    await waitFor(() => expect(save.disabled).toBe(true));

    const optionInput = screen.getByLabelText('customFields.options');
    fireEvent.change(optionInput, { target: { value: 'A' } });
    fireEvent.keyDown(optionInput, { key: 'Enter' });

    await waitFor(() => expect(save.disabled).toBe(false));

    fireEvent.click(save);
    await waitFor(() =>
      expect(mockedApi.createCustomField).toHaveBeenCalledWith({
        name: 'Charge',
        key: 'charge',
        field_type: 'choice',
        options: ['A'],
      }),
    );
  });

  it('does not add the same option twice', async () => {
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByText('customFields.add'));
    fireEvent.change(screen.getByLabelText('customFields.name'), { target: { value: 'Charge' } });
    fireEvent.change(screen.getByLabelText('customFields.type'), { target: { value: 'choice' } });

    const optionInput = await screen.findByLabelText('customFields.options');
    for (const value of ['A', 'A']) {
      fireEvent.change(optionInput, { target: { value } });
      fireEvent.keyDown(optionInput, { key: 'Enter' });
    }

    fireEvent.click(screen.getByText('common.save'));
    await waitFor(() =>
      expect(mockedApi.createCustomField).toHaveBeenCalledWith({
        name: 'Charge',
        key: 'charge',
        field_type: 'choice',
        options: ['A'],
      }),
    );
  });

  it('edits an existing field without touching its key', async () => {
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByLabelText('Edit Kunde'));

    fireEvent.change(screen.getByLabelText('customFields.name'), { target: { value: 'Auftraggeber' } });
    fireEvent.click(screen.getByText('common.save'));

    await waitFor(() =>
      expect(mockedApi.updateCustomField).toHaveBeenCalledWith(1, {
        name: 'Auftraggeber',
        field_type: 'choice',
        options: ['Acme', 'Globex'],
      }),
    );
  });

  it('locks the type once spools hold a value', async () => {
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByLabelText('Edit Kunde'));
    // `existing` has value_count 3.
    expect((screen.getByLabelText('customFields.type') as HTMLSelectElement).disabled).toBe(true);
    expect(screen.getByText('customFields.typeLocked')).toBeTruthy();
  });

  it('leaves the type editable while the field is unused', async () => {
    mockedApi.getCustomFields.mockResolvedValue([{ ...existing, value_count: 0 }]);
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByLabelText('Edit Kunde'));
    expect((screen.getByLabelText('customFields.type') as HTMLSelectElement).disabled).toBe(false);
  });

  it('warns that stored values go with the field before deleting', async () => {
    render(<CustomFieldsModal open onClose={vi.fn()} />);
    fireEvent.click(await screen.findByLabelText('Delete Kunde'));

    expect(screen.getByText('customFields.confirmDeleteMessageInUse')).toBeTruthy();

    fireEvent.click(screen.getByText('common.delete'));
    await waitFor(() => expect(mockedApi.deleteCustomField).toHaveBeenCalledWith(1));
  });
});
