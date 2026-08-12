import type { LocationHASensorReading } from '../api/client';

export type LocationSensorCategory = 'temperature' | 'humidity' | 'battery';

export interface LocationSensorCategoryDefaults {
  alertAbove: string;
  alertBelow: string;
  notifyOnAlert: boolean;
  showOnCard: boolean;
}

export type LocationSensorDefaults = Record<LocationSensorCategory, LocationSensorCategoryDefaults>;

const STORAGE_KEY = 'bambuddy-location-sensor-auto-add-defaults';

const EMPTY_CATEGORY_DEFAULTS: LocationSensorCategoryDefaults = {
  alertAbove: '',
  alertBelow: '',
  notifyOnAlert: false,
  showOnCard: true,
};

// Sensible out-of-the-box thresholds for a typical filament drybox, used
// until the user saves their own values in the Options modal.
export function defaultLocationSensorDefaults(): LocationSensorDefaults {
  return {
    temperature: { ...EMPTY_CATEGORY_DEFAULTS, alertAbove: '30', alertBelow: '20' },
    humidity: { ...EMPTY_CATEGORY_DEFAULTS, alertAbove: '30', alertBelow: '10' },
    battery: { ...EMPTY_CATEGORY_DEFAULTS, alertBelow: '10' },
  };
}

export function loadLocationSensorDefaults(): LocationSensorDefaults {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<LocationSensorDefaults>;
      const defaults = defaultLocationSensorDefaults();
      (Object.keys(defaults) as LocationSensorCategory[]).forEach((category) => {
        if (parsed[category]) defaults[category] = { ...defaults[category], ...parsed[category] };
      });
      return defaults;
    }
  } catch {
    return defaultLocationSensorDefaults();
  }
  return defaultLocationSensorDefaults();
}

export function saveLocationSensorDefaults(defaults: LocationSensorDefaults) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(defaults));
  } catch {
    return;
  }
}

const COLORIZE_VALUES_STORAGE_KEY = 'bambuddy-location-sensor-colorize-values';

export function loadLocationSensorColorizeValues(): boolean {
  try {
    const stored = localStorage.getItem(COLORIZE_VALUES_STORAGE_KEY);
    return stored ? stored === 'true' : true;
  } catch {
    return true;
  }
}

export function saveLocationSensorColorizeValues(value: boolean) {
  try {
    localStorage.setItem(COLORIZE_VALUES_STORAGE_KEY, String(value));
  } catch {
    return;
  }
}

export const LOCATION_SENSOR_ALERT_COLORS = ['red', 'orange', 'yellow', 'green', 'blue', 'purple', 'pink'] as const;
export type LocationSensorAlertColor = (typeof LOCATION_SENSOR_ALERT_COLORS)[number];

export const LOCATION_SENSOR_ALERT_COLOR_CLASSES: Record<LocationSensorAlertColor, string> = {
  red: 'text-red-400',
  orange: 'text-orange-400',
  yellow: 'text-yellow-400',
  green: 'text-green-400',
  blue: 'text-blue-400',
  purple: 'text-purple-400',
  pink: 'text-pink-400',
};

const ALERT_ABOVE_COLOR_STORAGE_KEY = 'bambuddy-location-sensor-alert-above-color';
const ALERT_BELOW_COLOR_STORAGE_KEY = 'bambuddy-location-sensor-alert-below-color';
const ALERT_OPTIMAL_COLOR_STORAGE_KEY = 'bambuddy-location-sensor-alert-optimal-color';

function isAlertColor(value: string | null): value is LocationSensorAlertColor {
  return !!value && (LOCATION_SENSOR_ALERT_COLORS as readonly string[]).includes(value);
}

export function loadLocationSensorAlertAboveColor(): LocationSensorAlertColor {
  try {
    const stored = localStorage.getItem(ALERT_ABOVE_COLOR_STORAGE_KEY);
    return isAlertColor(stored) ? stored : 'purple';
  } catch {
    return 'purple';
  }
}

export function saveLocationSensorAlertAboveColor(color: LocationSensorAlertColor) {
  try {
    localStorage.setItem(ALERT_ABOVE_COLOR_STORAGE_KEY, color);
  } catch {
    return;
  }
}

export function loadLocationSensorAlertBelowColor(): LocationSensorAlertColor {
  try {
    const stored = localStorage.getItem(ALERT_BELOW_COLOR_STORAGE_KEY);
    return isAlertColor(stored) ? stored : 'red';
  } catch {
    return 'red';
  }
}

export function saveLocationSensorAlertBelowColor(color: LocationSensorAlertColor) {
  try {
    localStorage.setItem(ALERT_BELOW_COLOR_STORAGE_KEY, color);
  } catch {
    return;
  }
}

export function loadLocationSensorAlertOptimalColor(): LocationSensorAlertColor {
  try {
    const stored = localStorage.getItem(ALERT_OPTIMAL_COLOR_STORAGE_KEY);
    return isAlertColor(stored) ? stored : 'green';
  } catch {
    return 'green';
  }
}

export function saveLocationSensorAlertOptimalColor(color: LocationSensorAlertColor) {
  try {
    localStorage.setItem(ALERT_OPTIMAL_COLOR_STORAGE_KEY, color);
  } catch {
    return;
  }
}

export type LocationSensorAlertStatus = 'above' | 'below' | 'ok' | null;

export function locationSensorReadingAlertStatus(reading: LocationHASensorReading): LocationSensorAlertStatus {
  if (!reading.reachable || reading.state === null) return null;
  if (reading.kind === 'numeric') {
    if (reading.alert_above === null && reading.alert_below === null) return null;
    if (reading.value === null) return null;
    if (reading.alert_above !== null && reading.value > reading.alert_above) return 'above';
    if (reading.alert_below !== null && reading.value < reading.alert_below) return 'below';
    return 'ok';
  }
  if (reading.alert_state === null) return null;
  return reading.state.toLowerCase() === reading.alert_state ? 'above' : 'ok';
}

export function locationSensorValueColorClass(
  status: LocationSensorAlertStatus,
  aboveColor: LocationSensorAlertColor,
  belowColor: LocationSensorAlertColor,
  optimalColor: LocationSensorAlertColor
): string {
  if (status === 'above') return LOCATION_SENSOR_ALERT_COLOR_CLASSES[aboveColor];
  if (status === 'below') return LOCATION_SENSOR_ALERT_COLOR_CLASSES[belowColor];
  if (status === 'ok') return LOCATION_SENSOR_ALERT_COLOR_CLASSES[optimalColor];
  return '';
}
