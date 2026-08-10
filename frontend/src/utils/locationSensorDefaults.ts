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
