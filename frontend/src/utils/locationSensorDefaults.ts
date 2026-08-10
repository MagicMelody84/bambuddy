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

export function emptyLocationSensorDefaults(): LocationSensorDefaults {
  return {
    temperature: { ...EMPTY_CATEGORY_DEFAULTS },
    humidity: { ...EMPTY_CATEGORY_DEFAULTS },
    battery: { ...EMPTY_CATEGORY_DEFAULTS },
  };
}

export function loadLocationSensorDefaults(): LocationSensorDefaults {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<LocationSensorDefaults>;
      const defaults = emptyLocationSensorDefaults();
      (Object.keys(defaults) as LocationSensorCategory[]).forEach((category) => {
        if (parsed[category]) defaults[category] = { ...defaults[category], ...parsed[category] };
      });
      return defaults;
    }
  } catch {
    return emptyLocationSensorDefaults();
  }
  return emptyLocationSensorDefaults();
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

export const LOCATION_SENSOR_ALERT_COLORS = ['red', 'orange', 'yellow', 'blue', 'purple', 'pink'] as const;
export type LocationSensorAlertColor = (typeof LOCATION_SENSOR_ALERT_COLORS)[number];

export const LOCATION_SENSOR_ALERT_COLOR_CLASSES: Record<LocationSensorAlertColor, string> = {
  red: 'text-red-400',
  orange: 'text-orange-400',
  yellow: 'text-yellow-400',
  blue: 'text-blue-400',
  purple: 'text-purple-400',
  pink: 'text-pink-400',
};

const ALERT_ABOVE_COLOR_STORAGE_KEY = 'bambuddy-location-sensor-alert-above-color';
const ALERT_BELOW_COLOR_STORAGE_KEY = 'bambuddy-location-sensor-alert-below-color';

function isAlertColor(value: string | null): value is LocationSensorAlertColor {
  return !!value && (LOCATION_SENSOR_ALERT_COLORS as readonly string[]).includes(value);
}

export function loadLocationSensorAlertAboveColor(): LocationSensorAlertColor {
  try {
    const stored = localStorage.getItem(ALERT_ABOVE_COLOR_STORAGE_KEY);
    return isAlertColor(stored) ? stored : 'red';
  } catch {
    return 'red';
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
    return isAlertColor(stored) ? stored : 'blue';
  } catch {
    return 'blue';
  }
}

export function saveLocationSensorAlertBelowColor(color: LocationSensorAlertColor) {
  try {
    localStorage.setItem(ALERT_BELOW_COLOR_STORAGE_KEY, color);
  } catch {
    return;
  }
}
