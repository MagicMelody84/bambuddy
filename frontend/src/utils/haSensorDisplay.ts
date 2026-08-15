import {
  Activity,
  AlertTriangle,
  Battery,
  DoorClosed,
  DoorOpen,
  Droplets,
  Gauge,
  Lock,
  LockOpen,
  Thermometer,
  Wind,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

/**
 * Display metadata for Home Assistant sensors, shared between the printer
 * and storage-location bindings. Both features read the same device classes
 * off the same kind of entity, so keeping one copy here means a new class
 * only needs adding in one place instead of drifting across every consumer.
 */

// Home Assistant's own device_class decides the wording, so a door reads
// "Open"/"Closed" rather than the "on"/"off" the API actually carries. Classes
// absent from this map fall through to on/off, which is what HA itself shows
// for a binary_sensor with no class.
export const HA_SENSOR_BINARY_LABELS: Record<string, { on: string; off: string }> = {
  door: { on: 'open', off: 'closed' },
  garage_door: { on: 'open', off: 'closed' },
  window: { on: 'open', off: 'closed' },
  opening: { on: 'open', off: 'closed' },
  lock: { on: 'unlocked', off: 'locked' },
  motion: { on: 'detected', off: 'clear' },
  occupancy: { on: 'detected', off: 'clear' },
  presence: { on: 'detected', off: 'clear' },
  smoke: { on: 'detected', off: 'clear' },
  gas: { on: 'detected', off: 'clear' },
  moisture: { on: 'wet', off: 'dry' },
  problem: { on: 'problem', off: 'ok' },
  safety: { on: 'problem', off: 'ok' },
  running: { on: 'running', off: 'stopped' },
};

export const HA_SENSOR_ICONS: Record<string, LucideIcon> = {
  door: DoorOpen,
  garage_door: DoorOpen,
  window: DoorOpen,
  opening: DoorOpen,
  lock: LockOpen,
  temperature: Thermometer,
  humidity: Droplets,
  moisture: Droplets,
  battery: Battery,
  motion: Activity,
  occupancy: Activity,
  presence: Activity,
  smoke: AlertTriangle,
  gas: AlertTriangle,
  problem: AlertTriangle,
  safety: AlertTriangle,
  running: Wind,
};

interface IconableReading {
  device_class: string | null;
  state: string | null;
  kind: 'binary' | 'numeric';
}

// A closed door wants the closed-door glyph — the map is keyed by class, so
// the two states that have a distinct "off" icon are special-cased here.
export function iconForHASensor(reading: IconableReading): LucideIcon {
  const deviceClass = reading.device_class ?? '';
  if (reading.state === 'off') {
    if (HA_SENSOR_ICONS[deviceClass] === DoorOpen) return DoorClosed;
    if (HA_SENSOR_ICONS[deviceClass] === LockOpen) return Lock;
  }
  return HA_SENSOR_ICONS[deviceClass] ?? (reading.kind === 'numeric' ? Gauge : Activity);
}
