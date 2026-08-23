import { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ListPlus, Plus, Loader2, Pencil, Trash2, X } from 'lucide-react';
import { api, type CustomFieldDef } from '../api/client';
import { Button } from './Button';
import { ConfirmModal } from './ConfirmModal';
import { useToast } from '../contexts/ToastContext';
import { inventoryCustomFieldsQueryKey } from '../utils/inventoryQueries';

interface CustomFieldsModalProps {
  open: boolean;
  onClose: () => void;
}

// Mirrors custom_field_service.SUPPORTED_FIELD_TYPES, which in turn mirrors
// Spoolman's own extra-field types. `choice` is the only one with options.
const FIELD_TYPES = [
  'text',
  'integer',
  'integer_range',
  'float',
  'float_range',
  'datetime',
  'boolean',
  'choice',
] as const;
type FieldType = (typeof FIELD_TYPES)[number];

/**
 * CRUD for user-defined spool fields. Same shape as LocationsModal — list plus
 * an inner editor — with an option editor on top, since a select field is only
 * useful once it has values to choose from.
 */
export function CustomFieldsModal({ open, onClose }: CustomFieldsModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<CustomFieldDef | null>(null);
  const [name, setName] = useState('');
  const [fieldType, setFieldType] = useState<FieldType>('text');
  const [options, setOptions] = useState<string[]>([]);
  const [optionDraft, setOptionDraft] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<CustomFieldDef | null>(null);

  const { data: fields = [], isLoading } = useQuery({
    queryKey: inventoryCustomFieldsQueryKey,
    queryFn: api.getCustomFields,
    enabled: open,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: inventoryCustomFieldsQueryKey });
    queryClient.invalidateQueries({ queryKey: ['inventory-spools'] });
    queryClient.invalidateQueries({ queryKey: ['spoolman-inventory-spools'] });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const trimmed = name.trim();
      if (!trimmed) throw new Error(t('customFields.nameRequired'));
      if (fieldType === 'choice' && options.length === 0) throw new Error(t('customFields.optionsRequired'));
      // Options are only sent for select — the backend rejects them on every
      // other type rather than storing something the form never shows.
      const payload = { name: trimmed, field_type: fieldType, options: fieldType === 'choice' ? options : [] };
      if (editing) {
        return api.updateCustomField(editing.id, payload);
      }
      return api.createCustomField(payload);
    },
    onSuccess: () => {
      showToast(t(editing ? 'customFields.updated' : 'customFields.created'), 'success');
      invalidate();
      setEditorOpen(false);
      setEditing(null);
      setName('');
      setFieldType('text');
      setOptions([]);
      setOptionDraft('');
    },
    onError: (err: Error) => {
      showToast(err.message || t('customFields.saveFailed'), 'error');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteCustomField(id),
    onSuccess: () => {
      showToast(t('customFields.deleted'), 'success');
      setDeleteTarget(null);
      invalidate();
    },
    onError: (err: Error) => {
      showToast(err.message || t('customFields.deleteFailed'), 'error');
    },
  });

  const openCreate = () => {
    setEditing(null);
    setName('');
    setFieldType('text');
    setOptions([]);
    setOptionDraft('');
    setEditorOpen(true);
  };

  const openEdit = (field: CustomFieldDef) => {
    setEditing(field);
    setName(field.name);
    setFieldType(FIELD_TYPES.includes(field.field_type as FieldType) ? (field.field_type as FieldType) : 'text');
    setOptions([...field.options]);
    setOptionDraft('');
    setEditorOpen(true);
  };

  const closeEditor = useCallback(() => {
    if (saveMutation.isPending) return;
    setEditorOpen(false);
    setEditing(null);
    setName('');
    setFieldType('text');
    setOptions([]);
    setOptionDraft('');
  }, [saveMutation.isPending]);

  // Esc closes the inner editor first, then the outer modal — but never while
  // a save or delete is in flight (mirrors LocationsModal).
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (saveMutation.isPending || deleteMutation.isPending) return;
      if (editorOpen) {
        closeEditor();
      } else if (!deleteTarget) {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, editorOpen, deleteTarget, saveMutation.isPending, deleteMutation.isPending, closeEditor, onClose]);

  // A field that no spool uses yet can still be retyped; once values exist the
  // backend refuses, so the control is disabled rather than failing on save.
  const typeLocked = Boolean(editing && editing.value_count > 0);

  const addOption = () => {
    const trimmed = optionDraft.trim();
    if (!trimmed) return;
    if (options.includes(trimmed)) {
      showToast(t('customFields.optionDuplicate'), 'info');
      setOptionDraft('');
      return;
    }
    setOptions((prev) => [...prev, trimmed]);
    setOptionDraft('');
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate();
  };

  if (!open) return null;

  const modalTitleId = 'custom-fields-modal-title';
  const editorTitleId = 'custom-field-editor-title';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/60"
        onClick={() => {
          if (saveMutation.isPending || deleteMutation.isPending) return;
          onClose();
        }}
      />
      <div
        className="relative w-full max-w-2xl mx-4 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-xl shadow-2xl max-h-[90vh] flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby={modalTitleId}
      >
        <div className="flex items-center justify-between gap-4 px-6 py-4 border-b border-bambu-dark-tertiary">
          <div>
            <h2 id={modalTitleId} className="text-lg font-semibold text-white flex items-center gap-2">
              <ListPlus className="w-5 h-5 text-bambu-green" />
              {t('customFields.title')}
            </h2>
            <p className="text-bambu-gray text-sm mt-0.5">{t('customFields.subtitle')}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={openCreate}>
              <Plus className="w-4 h-4" />
              {t('customFields.add')}
            </Button>
            <button
              type="button"
              className="p-1.5 text-bambu-gray hover:text-white rounded"
              onClick={onClose}
              aria-label={t('common.close')}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-16 text-bambu-gray">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              {t('common.loading')}
            </div>
          ) : fields.length === 0 ? (
            <div className="py-16 text-center text-bambu-gray">{t('customFields.empty')}</div>
          ) : (
            <table className="w-full text-sm table-fixed">
              <thead>
                <tr className="border-b border-bambu-dark-tertiary text-left text-bambu-gray">
                  <th className="px-4 py-3 font-medium w-1/4">{t('customFields.name')}</th>
                  <th className="px-4 py-3 font-medium w-44">{t('customFields.type')}</th>
                  <th className="px-4 py-3 font-medium">{t('customFields.options')}</th>
                  <th className="px-4 py-3 font-medium text-right w-24">{t('customFields.spools')}</th>
                  <th className="px-4 py-3 font-medium text-right w-32">{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {fields.map((field) => (
                  <tr key={field.id} className="border-b border-bambu-dark-tertiary/60 hover:bg-bambu-dark-tertiary/30">
                    <td className="px-4 py-3 text-white font-medium truncate">{field.name}</td>
                    <td className="px-4 py-3 text-bambu-gray truncate">{t(`customFields.types.${field.field_type}`)}</td>
                    <td className="px-4 py-3 text-bambu-gray truncate">{field.options.join(', ')}</td>
                    <td className="px-4 py-3 text-right text-bambu-gray">{field.value_count}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          className="p-1.5 text-bambu-gray hover:text-bambu-green rounded"
                          onClick={() => openEdit(field)}
                          title={t('common.edit')}
                          aria-label={t('customFields.editAria', {
                            name: field.name,
                            defaultValue: `Edit ${field.name}`,
                          })}
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          className="p-1.5 text-bambu-gray hover:text-red-600 dark:hover:text-red-400 rounded"
                          onClick={() => setDeleteTarget(field)}
                          title={t('common.delete')}
                          aria-label={t('customFields.deleteAria', {
                            name: field.name,
                            defaultValue: `Delete ${field.name}`,
                          })}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {editorOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" onClick={closeEditor} />
          <div
            className="relative w-full max-w-md mx-4 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-xl p-6 shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby={editorTitleId}
          >
            <h3 id={editorTitleId} className="text-lg font-semibold text-white mb-4">
              {editing ? t('customFields.edit') : t('customFields.add')}
            </h3>
            <form onSubmit={handleSave}>
              <label className="block text-sm font-medium text-bambu-gray mb-1" htmlFor="custom-field-name">
                {t('customFields.name')}
              </label>
              <input
                id="custom-field-name"
                type="text"
                maxLength={100}
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:outline-none focus:border-bambu-green mb-4"
                placeholder={t('customFields.namePlaceholder')}
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />

              <label className="block text-sm font-medium text-bambu-gray mb-1" htmlFor="custom-field-type">
                {t('customFields.type')}
              </label>
              <select
                id="custom-field-type"
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:outline-none focus:border-bambu-green disabled:opacity-50"
                value={fieldType}
                // Locked once values exist: each one was parsed against the old
                // type, and reinterpreting them wholesale isn't safe. The
                // backend enforces this too.
                disabled={typeLocked}
                onChange={(e) => setFieldType(e.target.value as FieldType)}
              >
                {FIELD_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {t(`customFields.types.${type}`)}
                  </option>
                ))}
              </select>
              <p className="text-xs text-bambu-gray mb-4 mt-1">
                {typeLocked ? t('customFields.typeLocked') : t('customFields.typeHint')}
              </p>

              {fieldType === 'choice' && (
                <>
              <label className="block text-sm font-medium text-bambu-gray mb-1" htmlFor="custom-field-option">
                {t('customFields.options')}
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  id="custom-field-option"
                  type="text"
                  maxLength={100}
                  className="flex-1 px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:outline-none focus:border-bambu-green"
                  placeholder={t('customFields.optionPlaceholder')}
                  value={optionDraft}
                  onChange={(e) => setOptionDraft(e.target.value)}
                  // Enter adds an option instead of submitting the form — the
                  // form's submit button is the only way to save.
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      addOption();
                    }
                  }}
                />
                <Button type="button" variant="secondary" onClick={addOption} disabled={!optionDraft.trim()}>
                  <Plus className="w-4 h-4" />
                </Button>
              </div>
              <div className="flex flex-wrap gap-2 mb-4 min-h-[2rem]">
                {options.length === 0 ? (
                  <span className="text-xs text-bambu-gray">{t('customFields.optionsRequired')}</span>
                ) : (
                  options.map((option) => (
                    <span
                      key={option}
                      className="inline-flex items-center gap-1 px-2 py-1 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-xs"
                    >
                      {option}
                      <button
                        type="button"
                        className="text-bambu-gray hover:text-red-600 dark:hover:text-red-400"
                        onClick={() => setOptions((prev) => prev.filter((o) => o !== option))}
                        aria-label={t('customFields.removeOptionAria', {
                          option,
                          defaultValue: `Remove ${option}`,
                        })}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))
                )}
              </div>
                </>
              )}

              <div className="flex justify-end gap-2">
                <Button type="button" variant="secondary" onClick={closeEditor}>
                  {t('common.cancel')}
                </Button>
                <Button
                  type="submit"
                  disabled={saveMutation.isPending || !name.trim() || (fieldType === 'choice' && options.length === 0)}
                >
                  {saveMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                  {t('common.save')}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {deleteTarget && (
        <ConfirmModal
          title={t('customFields.confirmDelete', { name: deleteTarget.name })}
          message={
            deleteTarget.value_count > 0
              ? t('customFields.confirmDeleteMessageInUse', { count: deleteTarget.value_count })
              : t('customFields.confirmDeleteMessage')
          }
          confirmText={t('common.delete')}
          variant="danger"
          isLoading={deleteMutation.isPending}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
