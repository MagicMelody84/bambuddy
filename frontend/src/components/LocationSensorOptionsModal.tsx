import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Battery, Droplets, RotateCcw, Save, Settings2, Thermometer, X } from 'lucide-react';
import { api } from '../api/client';
import { Button } from './Button';
import { ConfirmModal } from './ConfirmModal';
import { useToast } from '../contexts/ToastContext';
import {
  LOCATION_SENSOR_ALERT_COLORS,
  loadLocationSensorAlertAboveColor,
  loadLocationSensorAlertBelowColor,
  loadLocationSensorAlertOptimalColor,
  loadLocationSensorColorizeValues,
  loadLocationSensorDefaults,
  saveLocationSensorAlertAboveColor,
  saveLocationSensorAlertBelowColor,
  saveLocationSensorAlertOptimalColor,
  saveLocationSensorColorizeValues,
  saveLocationSensorDefaults,
  type LocationSensorAlertColor,
  type LocationSensorCategory,
  type LocationSensorCategoryDefaults,
  type LocationSensorDefaults,
} from '../utils/locationSensorDefaults';

interface Props {
  onClose: () => void;
}

const MIN_POLL_INTERVAL = 60;
const DEFAULT_POLL_INTERVAL = 120;

const CATEGORY_ICONS: Record<LocationSensorCategory, typeof Thermometer> = {
  temperature: Thermometer,
  humidity: Droplets,
  battery: Battery,
};

const CATEGORY_UNITS: Record<LocationSensorCategory, string> = {
  temperature: '°C',
  humidity: '%',
  battery: '%',
};

function categoryFor(deviceClass: string | null): LocationSensorCategory | null {
  if (deviceClass === 'temperature') return 'temperature';
  if (deviceClass === 'humidity' || deviceClass === 'moisture') return 'humidity';
  if (deviceClass === 'battery') return 'battery';
  return null;
}

function CategorySection({
  category,
  state,
  onChange,
}: {
  category: LocationSensorCategory;
  state: LocationSensorCategoryDefaults;
  onChange: (patch: Partial<LocationSensorCategoryDefaults>) => void;
}) {
  const { t } = useTranslation();
  const Icon = CATEGORY_ICONS[category];
  const unit = CATEGORY_UNITS[category];
  const hasAlertCondition = state.alertAbove !== '' || state.alertBelow !== '';

  return (
    <div className="p-3 border border-bambu-dark-tertiary rounded-lg space-y-3">
      <div className="flex items-center gap-1.5 text-sm text-white font-medium">
        <Icon className="w-4 h-4" />
        {t(`inventory.${category}`)}
      </div>

      {category === 'battery' ? (
        <div>
          <span className="block text-xs text-bambu-gray mb-1">
            {t('haSensors.alertBelow')} {unit}
          </span>
          <input
            type="number"
            step="any"
            value={state.alertBelow}
            onChange={(e) => onChange({ alertBelow: e.target.value })}
            className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white"
          />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className="block text-xs text-bambu-gray mb-1">
              {t('haSensors.alertAbove')} {unit}
            </span>
            <input
              type="number"
              step="any"
              value={state.alertAbove}
              onChange={(e) => onChange({ alertAbove: e.target.value })}
              className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white"
            />
          </div>
          <div>
            <span className="block text-xs text-bambu-gray mb-1">
              {t('haSensors.alertBelow')} {unit}
            </span>
            <input
              type="number"
              step="any"
              value={state.alertBelow}
              onChange={(e) => onChange({ alertBelow: e.target.value })}
              className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white"
            />
          </div>
        </div>
      )}

      <label className="flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={state.showOnCard}
          onChange={(e) => onChange({ showOnCard: e.target.checked })}
          className="w-4 h-4"
        />
        <span className="text-sm text-white">{t('locationHaSensors.showOnCard')}</span>
      </label>

      <label className="flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={state.notifyOnAlert}
          onChange={(e) => onChange({ notifyOnAlert: e.target.checked })}
          disabled={!hasAlertCondition}
          className="w-4 h-4"
        />
        <span className={`text-sm ${hasAlertCondition ? 'text-white' : 'text-bambu-gray'}`}>
          {t('haSensors.notifyOnAlert')}
        </span>
      </label>
    </div>
  );
}

export function LocationSensorOptionsModal({ onClose }: Props) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [defaults, setDefaults] = useState<LocationSensorDefaults>(() => loadLocationSensorDefaults());
  const [colorizeValues, setColorizeValues] = useState(() => loadLocationSensorColorizeValues());
  const [aboveColor, setAboveColor] = useState<LocationSensorAlertColor>(() => loadLocationSensorAlertAboveColor());
  const [belowColor, setBelowColor] = useState<LocationSensorAlertColor>(() => loadLocationSensorAlertBelowColor());
  const [optimalColor, setOptimalColor] = useState<LocationSensorAlertColor>(() => loadLocationSensorAlertOptimalColor());
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  const { data: appSettings } = useQuery({ queryKey: ['settings'], queryFn: api.getSettings });
  const [pollInterval, setPollInterval] = useState(DEFAULT_POLL_INTERVAL);
  useEffect(() => {
    if (appSettings) setPollInterval(appSettings.location_sensor_poll_interval);
  }, [appSettings]);

  const updateCategory = (category: LocationSensorCategory, patch: Partial<LocationSensorCategoryDefaults>) => {
    setDefaults((prev) => ({ ...prev, [category]: { ...prev[category], ...patch } }));
  };

  const persistDefaults = async () => {
    saveLocationSensorDefaults({ ...defaults, battery: { ...defaults.battery, alertAbove: '' } });
    saveLocationSensorColorizeValues(colorizeValues);
    saveLocationSensorAlertAboveColor(aboveColor);
    saveLocationSensorAlertBelowColor(belowColor);
    saveLocationSensorAlertOptimalColor(optimalColor);

    // Only touch the server when the interval actually changed. It is the
    // one field here that needs SETTINGS_UPDATE (admin); the rest are
    // localStorage-only, so a non-admin who leaves the interval alone can
    // still save their colour/threshold preferences without ever hitting a
    // permission check.
    const clampedInterval = Math.max(MIN_POLL_INTERVAL, pollInterval);
    if (appSettings && clampedInterval !== appSettings.location_sensor_poll_interval) {
      await api.updateSettings({ location_sensor_poll_interval: clampedInterval });
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    }
  };

  const saveMutation = useMutation({
    mutationFn: persistDefaults,
    onSuccess: () => {
      showToast(t('locationHaSensors.options.saved'), 'success');
      onClose();
    },
    onError: (err: Error) => {
      showToast(err.message || t('locationHaSensors.options.saveFailed'), 'error');
    },
  });

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate();
  };

  const resetMutation = useMutation({
    mutationFn: async () => {
      await persistDefaults();
      const sensors = await api.getLocationHASensors();
      const targets = sensors.filter((sensor) => categoryFor(sensor.device_class) !== null);
      await Promise.all(
        targets.map((sensor) => {
          const category = categoryFor(sensor.device_class)!;
          const categoryDefaults = defaults[category];
          return api.updateLocationHASensor(sensor.id, {
            alert_above:
              category !== 'battery' && categoryDefaults.alertAbove !== '' ? Number(categoryDefaults.alertAbove) : null,
            alert_below: categoryDefaults.alertBelow !== '' ? Number(categoryDefaults.alertBelow) : null,
            notify_on_alert: categoryDefaults.notifyOnAlert,
            show_on_card: categoryDefaults.showOnCard,
          });
        })
      );
      return targets.length;
    },
    onSuccess: (count) => {
      queryClient.invalidateQueries({ queryKey: ['locationHaSensors'] });
      queryClient.invalidateQueries({ queryKey: ['locationHaSensorReadings'] });
      showToast(t('locationHaSensors.options.resetDone', { count }), 'success');
      setShowResetConfirm(false);
      onClose();
    },
    onError: (err: Error) => {
      showToast(err.message || t('locationHaSensors.options.resetFailed'), 'error');
      setShowResetConfirm(false);
    },
  });

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-bambu-dark-secondary rounded-xl border border-bambu-dark-tertiary w-full max-w-lg max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-bambu-dark-tertiary">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-full bg-bambu-green/20 text-bambu-green">
              <Settings2 className="w-5 h-5" />
            </div>
            <h2 className="text-lg font-semibold text-white">{t('locationHaSensors.options.title')}</h2>
          </div>
          <button onClick={onClose} className="text-bambu-gray hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSave} className="px-6 pb-6 pt-3 space-y-4">
          <p className="text-xs text-bambu-gray">{t('locationHaSensors.options.description')}</p>

          <div className="space-y-3">
            <CategorySection
              category="temperature"
              state={defaults.temperature}
              onChange={(patch) => updateCategory('temperature', patch)}
            />
            <CategorySection
              category="humidity"
              state={defaults.humidity}
              onChange={(patch) => updateCategory('humidity', patch)}
            />
            <CategorySection
              category="battery"
              state={defaults.battery}
              onChange={(patch) => updateCategory('battery', patch)}
            />
          </div>

          <div className="pt-4 mt-4 border-t border-bambu-dark-tertiary">
            <p className="text-xs font-medium text-bambu-gray uppercase tracking-wider mb-3">
              {t('locationHaSensors.options.generalSettings')}
            </p>
          </div>

          <div className="p-3 border border-bambu-dark-tertiary rounded-lg space-y-2">
            <label className="block text-sm text-white" htmlFor="location-sensor-poll-interval">
              {t('locationHaSensors.options.pollInterval')}
            </label>
            <input
              id="location-sensor-poll-interval"
              type="number"
              min={MIN_POLL_INTERVAL}
              step="1"
              value={pollInterval}
              onChange={(e) => setPollInterval(Number(e.target.value))}
              onBlur={() => setPollInterval((prev) => Math.max(MIN_POLL_INTERVAL, prev || DEFAULT_POLL_INTERVAL))}
              className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white"
            />
            <p className="text-xs text-bambu-gray">{t('locationHaSensors.options.pollIntervalHint')}</p>
          </div>

          <div className="p-3 border border-bambu-dark-tertiary rounded-lg space-y-3">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={colorizeValues}
                onChange={(e) => setColorizeValues(e.target.checked)}
                className="w-4 h-4"
              />
              <span className="text-sm text-white">{t('locationHaSensors.options.colorizeValues')}</span>
            </label>

            <div className={`grid grid-cols-3 gap-x-3 gap-y-1 items-end ${colorizeValues ? '' : 'opacity-50'}`}>
              <label className="block text-xs text-bambu-gray" htmlFor="location-sensor-below-color">
                {t('locationHaSensors.options.belowColor')}
              </label>
              <label className="block text-xs text-bambu-gray" htmlFor="location-sensor-optimal-color">
                {t('locationHaSensors.options.optimalColor')}
              </label>
              <label className="block text-xs text-bambu-gray" htmlFor="location-sensor-above-color">
                {t('locationHaSensors.options.aboveColor')}
              </label>
              <select
                id="location-sensor-below-color"
                value={belowColor}
                onChange={(e) => setBelowColor(e.target.value as LocationSensorAlertColor)}
                disabled={!colorizeValues}
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white disabled:cursor-not-allowed"
              >
                {LOCATION_SENSOR_ALERT_COLORS.map((color) => (
                  <option key={color} value={color}>
                    {t(`locationHaSensors.options.colors.${color}`)}
                  </option>
                ))}
              </select>
              <select
                id="location-sensor-optimal-color"
                value={optimalColor}
                onChange={(e) => setOptimalColor(e.target.value as LocationSensorAlertColor)}
                disabled={!colorizeValues}
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white disabled:cursor-not-allowed"
              >
                {LOCATION_SENSOR_ALERT_COLORS.map((color) => (
                  <option key={color} value={color}>
                    {t(`locationHaSensors.options.colors.${color}`)}
                  </option>
                ))}
              </select>
              <select
                id="location-sensor-above-color"
                value={aboveColor}
                onChange={(e) => setAboveColor(e.target.value as LocationSensorAlertColor)}
                disabled={!colorizeValues}
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white disabled:cursor-not-allowed"
              >
                {LOCATION_SENSOR_ALERT_COLORS.map((color) => (
                  <option key={color} value={color}>
                    {t(`locationHaSensors.options.colors.${color}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex items-center justify-between gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => setShowResetConfirm(true)}>
              <RotateCcw className="w-4 h-4" />
              {t('locationHaSensors.options.reset')}
            </Button>
            <div className="flex items-center gap-2">
              <Button type="button" variant="secondary" onClick={onClose}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={saveMutation.isPending}>
                <Save className="w-4 h-4" />
                {t('common.save')}
              </Button>
            </div>
          </div>
        </form>
      </div>

      {showResetConfirm && (
        <ConfirmModal
          title={t('locationHaSensors.options.resetConfirm.title')}
          message={t('locationHaSensors.options.resetConfirm.message')}
          confirmText={t('locationHaSensors.options.reset')}
          variant="danger"
          overlayZIndex="z-[60]"
          isLoading={resetMutation.isPending}
          onConfirm={() => resetMutation.mutate()}
          onCancel={() => setShowResetConfirm(false)}
        />
      )}
    </div>
  );
}
