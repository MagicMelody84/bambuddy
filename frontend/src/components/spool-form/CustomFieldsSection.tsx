import { useTranslation } from 'react-i18next';
import type { CustomFieldsSectionProps } from './types';

const INPUT_CLASS =
  'w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:outline-none focus:border-bambu-green';

const RANGE_TYPES = ['integer_range', 'float_range'];

/** Stored ranges are "min,max"; the form edits the two bounds separately. */
function splitRange(value: string): [string, string] {
  const parts = value.split(',');
  return parts.length === 2 ? [parts[0].trim(), parts[1].trim()] : ['', ''];
}

/**
 * Renders one input per user-defined custom field, shaped by the field's type.
 * The types mirror Spoolman's own extra-field types, so a value means the same
 * thing in both inventory modes; values are keyed by the definition's stable
 * `key`, which is what both backends store.
 */
export function CustomFieldsSection({ formData, updateField, fields }: CustomFieldsSectionProps) {
  const { t } = useTranslation();

  if (fields.length === 0) return null;

  const setValue = (key: string, value: string) => {
    updateField('custom_fields', { ...formData.custom_fields, [key]: value });
  };

  return (
    <div className="space-y-3">
      {fields.map((field) => {
        const value = formData.custom_fields[field.key] ?? '';
        const inputId = `custom-field-${field.key}`;

        if (field.field_type === 'boolean') {
          return (
            <div key={field.id} className="flex items-center gap-2">
              <input
                id={inputId}
                type="checkbox"
                className="w-4 h-4 accent-bambu-green"
                checked={value === 'true'}
                // Unchecked stores 'false' rather than '' so "explicitly no" is
                // distinguishable from "never answered".
                onChange={(e) => setValue(field.key, e.target.checked ? 'true' : 'false')}
              />
              <label className="text-sm text-white" htmlFor={inputId}>
                {field.name}
              </label>
              {value !== '' && (
                <button
                  type="button"
                  className="text-xs text-bambu-gray hover:text-white underline"
                  onClick={() => setValue(field.key, '')}
                >
                  {t('customFields.clear')}
                </button>
              )}
            </div>
          );
        }

        if (field.field_type === 'choice') {
          // A value stored before an option was removed from the definition
          // would otherwise vanish from the select and be silently rewritten.
          const staleValue = value && !field.options.includes(value) ? value : null;
          return (
            <div key={field.id}>
              <label className="block text-sm text-bambu-gray mb-1" htmlFor={inputId}>
                {field.name}
              </label>
              <select
                id={inputId}
                className={INPUT_CLASS}
                value={value}
                onChange={(e) => setValue(field.key, e.target.value)}
              >
                <option value="">{t('customFields.noValue')}</option>
                {staleValue && (
                  <option value={staleValue}>
                    {t('customFields.staleOption', { value: staleValue, defaultValue: `${staleValue} (removed)` })}
                  </option>
                )}
                {field.options.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
          );
        }

        if (RANGE_TYPES.includes(field.field_type)) {
          const [low, high] = splitRange(value);
          const step = field.field_type === 'integer_range' ? '1' : 'any';
          // Only emit a value once both bounds are filled — a half-typed range
          // is not something the backend can store.
          const setBound = (nextLow: string, nextHigh: string) =>
            setValue(field.key, nextLow.trim() && nextHigh.trim() ? `${nextLow.trim()},${nextHigh.trim()}` : '');
          return (
            <div key={field.id}>
              <label className="block text-sm text-bambu-gray mb-1" htmlFor={inputId}>
                {field.name}
              </label>
              <div className="flex items-center gap-2">
                <input
                  id={inputId}
                  type="number"
                  step={step}
                  className={INPUT_CLASS}
                  placeholder={t('customFields.rangeMin')}
                  value={low}
                  onChange={(e) => setBound(e.target.value, high)}
                />
                <span className="text-bambu-gray text-sm">–</span>
                <input
                  aria-label={t('customFields.rangeMaxAria', {
                    name: field.name,
                    defaultValue: `${field.name} maximum`,
                  })}
                  type="number"
                  step={step}
                  className={INPUT_CLASS}
                  placeholder={t('customFields.rangeMax')}
                  value={high}
                  onChange={(e) => setBound(low, e.target.value)}
                />
              </div>
            </div>
          );
        }

        if (field.field_type === 'datetime') {
          // A datetime-local input only accepts YYYY-MM-DDTHH:MM(:SS); a value
          // carrying a UTC offset (which the API does store, and other tools
          // write) would render as empty. Show the part it can display and fall
          // back to a plain text box for anything it cannot, so the value stays
          // visible and editable instead of silently looking unset.
          const pickerValue = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(value) ? value : '';
          const displayable = value === '' || pickerValue !== '';
          return (
            <div key={field.id}>
              <label className="block text-sm text-bambu-gray mb-1" htmlFor={inputId}>
                {field.name}
              </label>
              <input
                id={inputId}
                type={displayable ? 'datetime-local' : 'text'}
                className={INPUT_CLASS}
                placeholder={t('customFields.noValue')}
                value={displayable ? pickerValue : value}
                onChange={(e) => setValue(field.key, e.target.value)}
              />
            </div>
          );
        }

        const isNumeric = field.field_type === 'integer' || field.field_type === 'float';
        return (
          <div key={field.id}>
            <label className="block text-sm text-bambu-gray mb-1" htmlFor={inputId}>
              {field.name}
            </label>
            <input
              id={inputId}
              type={isNumeric ? 'number' : 'text'}
              maxLength={field.field_type === 'text' ? 255 : undefined}
              step={field.field_type === 'integer' ? '1' : field.field_type === 'float' ? 'any' : undefined}
              className={INPUT_CLASS}
              placeholder={t('customFields.noValue')}
              value={value}
              onChange={(e) => setValue(field.key, e.target.value)}
            />
          </div>
        );
      })}
    </div>
  );
}
