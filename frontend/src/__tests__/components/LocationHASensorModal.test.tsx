import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocationHASensorModal } from '../../components/LocationHASensorModal';
import { api } from '../../api/client';
import { render } from '../utils';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    api: {
      ...actual.api,
      getSettings: vi.fn(),
      getBindableLocationHAEntities: vi.fn(),
      getLocationHASensors: vi.fn(),
      createLocationHASensor: vi.fn(),
      updateLocationHASensor: vi.fn(),
    },
  };
});

const getSettings = vi.mocked(api.getSettings);
const getEntities = vi.mocked(api.getBindableLocationHAEntities);
const getLocationSensors = vi.mocked(api.getLocationHASensors);
const createSensor = vi.mocked(api.createLocationHASensor);
const updateSensor = vi.mocked(api.updateLocationHASensor);

const LOCATIONS = [{ id: 7, name: 'Drybox 1' }] as never;

function settings(overrides = {}) {
  return {
    ha_enabled: true,
    ha_url: 'http://homeassistant.local:8123',
    ha_token: 'token',
    ...overrides,
  } as never;
}

describe('LocationHASensorModal', () => {
  beforeEach(() => {
    getSettings.mockReset();
    getEntities.mockReset();
    getEntities.mockResolvedValue([]);
    getLocationSensors.mockReset();
    getLocationSensors.mockResolvedValue([]);
    createSensor.mockReset();
    createSensor.mockResolvedValue({} as never);
    updateSensor.mockReset();
    updateSensor.mockResolvedValue({} as never);
    vi.mocked(window.localStorage.getItem).mockReset();
  });

  it('warns when Home Assistant is not configured at all', async () => {
    getSettings.mockResolvedValue(settings({ ha_enabled: false, ha_url: '', ha_token: '' }));

    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    expect(
      await screen.findByText(/Home Assistant is not configured/)
    ).toBeInTheDocument();
    expect(screen.getByText('Settings → Network → Home Assistant')).toBeInTheDocument();
  });

  it('warns when the integration is configured but switched off', async () => {
    getSettings.mockResolvedValue(settings({ ha_enabled: false }));

    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    expect(await screen.findByText(/Home Assistant is not configured/)).toBeInTheDocument();
  });

  it('does not ask Home Assistant for entities it cannot reach', async () => {
    getSettings.mockResolvedValue(settings({ ha_token: '' }));

    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await screen.findByText(/Home Assistant is not configured/);
    expect(getEntities).not.toHaveBeenCalled();
  });

  it('blocks saving a new sensor while unconfigured', async () => {
    getSettings.mockResolvedValue(settings({ ha_enabled: false }));

    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await screen.findByText(/Home Assistant is not configured/);
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
  });

  it('shows no warning once Home Assistant is configured', async () => {
    getSettings.mockResolvedValue(settings());

    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await waitFor(() => expect(getEntities).toHaveBeenCalled());
    expect(screen.queryByText(/Home Assistant is not configured/)).not.toBeInTheDocument();
  });

  it('only offers temperature, humidity, and battery entities, not other device classes', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_temp', friendly_name: 'Drybox 1 Temp', domain: 'sensor', device_class: 'temperature', unit_of_measurement: '°C', state: '21.0' },
      { entity_id: 'sensor.drybox_1_humidity', friendly_name: 'Drybox 1 Humidity', domain: 'sensor', device_class: 'humidity', unit_of_measurement: '%', state: '40' },
      { entity_id: 'sensor.drybox_1_battery', friendly_name: 'Drybox 1 Battery', domain: 'sensor', device_class: 'battery', unit_of_measurement: '%', state: '90' },
      { entity_id: 'binary_sensor.drybox_1_door', friendly_name: 'Drybox 1 Door', domain: 'binary_sensor', device_class: 'door', unit_of_measurement: null, state: 'off' },
    ] as never);

    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    expect(await screen.findByText('Drybox 1 Temp')).toBeInTheDocument();
    expect(screen.getByText('Drybox 1 Humidity')).toBeInTheDocument();
    expect(screen.getByText('Drybox 1 Battery')).toBeInTheDocument();
    expect(screen.queryByText('Drybox 1 Door')).not.toBeInTheDocument();
  });

  it('only offers a "below" alert threshold for battery sensors, not "above"', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_battery', friendly_name: 'Drybox 1 Battery', domain: 'sensor', device_class: 'battery', unit_of_measurement: '%', state: '90' },
    ] as never);
    getLocationSensors.mockResolvedValue([]);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Battery'));

    expect(screen.queryByText(/^Above/)).not.toBeInTheDocument();
    expect(screen.getByText(/^Below/)).toBeInTheDocument();
    expect(screen.getAllByRole('spinbutton')).toHaveLength(1);
  });

  it('prefills the name field from the entity\'s friendly name, not the raw entity id', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_temp', friendly_name: 'Drybox 1 Temp', domain: 'sensor', device_class: 'temperature', unit_of_measurement: '°C', state: '21.0' },
    ] as never);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Temp'));

    expect(screen.getByLabelText(/name/i)).toHaveValue('Drybox 1 Temp');
  });

  it('follows the name field to the newly picked entity, as long as it was not typed by hand', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_temp', friendly_name: 'Drybox 1 Temp', domain: 'sensor', device_class: 'temperature', unit_of_measurement: '°C', state: '21.0' },
      { entity_id: 'sensor.drybox_2_temp', friendly_name: 'Drybox 2 Temp', domain: 'sensor', device_class: 'temperature', unit_of_measurement: '°C', state: '19.0' },
    ] as never);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Temp'));
    expect(screen.getByLabelText(/name/i)).toHaveValue('Drybox 1 Temp');

    await user.click(screen.getByText('Drybox 2 Temp'));
    expect(screen.getByLabelText(/name/i)).toHaveValue('Drybox 2 Temp');
  });

  it('does not overwrite a hand-typed name when a different entity is picked', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_temp', friendly_name: 'Drybox 1 Temp', domain: 'sensor', device_class: 'temperature', unit_of_measurement: '°C', state: '21.0' },
      { entity_id: 'sensor.drybox_2_temp', friendly_name: 'Drybox 2 Temp', domain: 'sensor', device_class: 'temperature', unit_of_measurement: '°C', state: '19.0' },
    ] as never);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Temp'));
    const nameInput = screen.getByLabelText(/name/i);
    await user.clear(nameInput);
    await user.type(nameInput, 'My Custom Name');

    await user.click(screen.getByText('Drybox 2 Temp'));
    expect(screen.getByLabelText(/name/i)).toHaveValue('My Custom Name');
  });

  it('saves the friendly name, not the raw entity id', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_temp', friendly_name: 'Drybox 1 Temp', domain: 'sensor', device_class: 'temperature', unit_of_measurement: '°C', state: '21.0' },
    ] as never);
    getLocationSensors.mockResolvedValue([]);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Temp'));
    await user.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(createSensor).toHaveBeenCalledTimes(1));
    expect(createSensor).toHaveBeenCalledWith(expect.objectContaining({ name: 'Drybox 1 Temp' }));
  });

  it('requires a name before saving', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_temp', friendly_name: 'Drybox 1 Temp', domain: 'sensor', device_class: 'temperature', unit_of_measurement: '°C', state: '21.0' },
    ] as never);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Temp'));
    await user.clear(screen.getByLabelText(/name/i));
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(await screen.findByText('Enter a display name')).toBeInTheDocument();
    expect(createSensor).not.toHaveBeenCalled();
  });

  it('clears a stale "above" value when saving an existing battery sensor', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([]);
    getLocationSensors.mockResolvedValue([]);

    const user = userEvent.setup();
    render(
      <LocationHASensorModal
        sensor={
          {
            id: 1,
            location_id: 7,
            name: 'sensor.drybox_1_battery',
            entity_id: 'sensor.drybox_1_battery',
            kind: 'numeric',
            device_class: 'battery',
            unit: '%',
            alert_state: null,
            alert_above: 95,
            alert_below: 15,
            notify_on_alert: false,
            show_on_card: true,
            sort_order: 0,
            last_state: null,
            last_changed: null,
            last_checked: null,
            created_at: '',
            updated_at: '',
          } as never
        }
        locations={LOCATIONS}
        onClose={() => {}}
      />
    );

    await user.click(await screen.findByRole('button', { name: /save/i }));

    await waitFor(() => expect(updateSensor).toHaveBeenCalledTimes(1));
    expect(updateSensor).toHaveBeenCalledWith(1, expect.objectContaining({ alert_above: null, alert_below: 15 }));
  });

  it('shows the location field only when creating a new sensor', async () => {
    getSettings.mockResolvedValue(settings());

    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    expect(await screen.findByText('Drybox 1')).toBeInTheDocument();
  });

  it('asks to replace the existing sensor when adding a second temperature sensor', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      {
        entity_id: 'sensor.drybox_1_temp_2',
        friendly_name: 'Drybox 1 Temp 2',
        domain: 'sensor',
        device_class: 'temperature',
        unit_of_measurement: '°C',
        state: '21.0',
      },
    ] as never);
    getLocationSensors.mockResolvedValue([
      {
        id: 1,
        location_id: 7,
        name: 'sensor.drybox_1_temp',
        entity_id: 'sensor.drybox_1_temp',
        kind: 'numeric',
        device_class: 'temperature',
        unit: '°C',
        alert_state: null,
        alert_above: null,
        alert_below: null,
        notify_on_alert: false,
        show_on_card: true,
        sort_order: 0,
        last_state: null,
        last_changed: null,
        last_checked: null,
        created_at: '',
        updated_at: '',
      },
    ] as never);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Temp 2'));
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(await screen.findByText('Replace existing sensor?')).toBeInTheDocument();
    expect(
      screen.getByText(/already has a temperature sensor bound: sensor\.drybox_1_temp\./)
    ).toBeInTheDocument();
  });

  it('asks to replace the existing sensor when adding a second humidity sensor', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      {
        entity_id: 'sensor.drybox_1_humidity_2',
        friendly_name: 'Drybox 1 Humidity 2',
        domain: 'sensor',
        device_class: 'humidity',
        unit_of_measurement: '%',
        state: '45',
      },
    ] as never);
    getLocationSensors.mockResolvedValue([
      {
        id: 2,
        location_id: 7,
        name: 'sensor.drybox_1_humidity',
        entity_id: 'sensor.drybox_1_humidity',
        kind: 'numeric',
        device_class: 'humidity',
        unit: '%',
        alert_state: null,
        alert_above: null,
        alert_below: null,
        notify_on_alert: false,
        show_on_card: true,
        sort_order: 0,
        last_state: null,
        last_changed: null,
        last_checked: null,
        created_at: '',
        updated_at: '',
      },
    ] as never);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Humidity 2'));
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(await screen.findByText('Replace existing sensor?')).toBeInTheDocument();
    expect(
      screen.getByText(/already has a humidity sensor bound: sensor\.drybox_1_humidity\./)
    ).toBeInTheDocument();
  });

  it('offers to bind sibling entities when adding the first sensor for a location', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_humidity', friendly_name: 'Drybox 1 Humidity', domain: 'sensor', device_class: 'humidity', unit_of_measurement: '%', state: '40' },
      { entity_id: 'sensor.drybox_1_temperature', friendly_name: 'Drybox 1 Temperature', domain: 'sensor', device_class: 'temperature', unit_of_measurement: '°C', state: '21.0' },
      { entity_id: 'sensor.drybox_1_battery', friendly_name: 'Drybox 1 Battery', domain: 'sensor', device_class: 'battery', unit_of_measurement: '%', state: '90' },
    ] as never);
    getLocationSensors.mockResolvedValue([]);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Humidity'));
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(await screen.findByText('Add the other sensors too?')).toBeInTheDocument();
    const temperatureCheckbox = screen.getByRole('checkbox', { name: /drybox 1 temperature/i });
    const batteryCheckbox = screen.getByRole('checkbox', { name: /drybox 1 battery/i });
    expect(temperatureCheckbox).toBeChecked();
    expect(batteryCheckbox).toBeChecked();

    await user.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => expect(createSensor).toHaveBeenCalledTimes(3));
    expect(createSensor).toHaveBeenNthCalledWith(1, expect.objectContaining({ entity_id: 'sensor.drybox_1_humidity' }));
    expect(createSensor).toHaveBeenNthCalledWith(2, expect.objectContaining({ entity_id: 'sensor.drybox_1_temperature' }));
    expect(createSensor).toHaveBeenNthCalledWith(3, expect.objectContaining({ entity_id: 'sensor.drybox_1_battery' }));
  });

  it('only adds sibling entities left checked in the auto-add dialog', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_humidity', friendly_name: 'Drybox 1 Humidity', domain: 'sensor', device_class: 'humidity', unit_of_measurement: '%', state: '40' },
      { entity_id: 'sensor.drybox_1_temperature', friendly_name: 'Drybox 1 Temperature', domain: 'sensor', device_class: 'temperature', unit_of_measurement: '°C', state: '21.0' },
      { entity_id: 'sensor.drybox_1_battery', friendly_name: 'Drybox 1 Battery', domain: 'sensor', device_class: 'battery', unit_of_measurement: '%', state: '90' },
    ] as never);
    getLocationSensors.mockResolvedValue([]);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Humidity'));
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(await screen.findByText('Add the other sensors too?')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: /drybox 1 battery/i }));

    await user.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => expect(createSensor).toHaveBeenCalledTimes(2));
    expect(createSensor).toHaveBeenNthCalledWith(1, expect.objectContaining({ entity_id: 'sensor.drybox_1_humidity' }));
    expect(createSensor).toHaveBeenNthCalledWith(2, expect.objectContaining({ entity_id: 'sensor.drybox_1_temperature' }));
    expect(createSensor).not.toHaveBeenCalledWith(expect.objectContaining({ entity_id: 'sensor.drybox_1_battery' }));
  });

  it('applies the saved per-category defaults to auto-added sibling sensors', async () => {
    vi.mocked(window.localStorage.getItem).mockReturnValue(
      JSON.stringify({
        temperature: { alertAbove: '30', alertBelow: '', notifyOnAlert: true, showOnCard: true },
        battery: { alertAbove: '', alertBelow: '15', notifyOnAlert: true, showOnCard: false },
        humidity: { alertAbove: '', alertBelow: '', notifyOnAlert: false, showOnCard: true },
      })
    );
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_humidity', friendly_name: 'Drybox 1 Humidity', domain: 'sensor', device_class: 'humidity', unit_of_measurement: '%', state: '40' },
      { entity_id: 'sensor.drybox_1_temperature', friendly_name: 'Drybox 1 Temperature', domain: 'sensor', device_class: 'temperature', unit_of_measurement: '°C', state: '21.0' },
      { entity_id: 'sensor.drybox_1_battery', friendly_name: 'Drybox 1 Battery', domain: 'sensor', device_class: 'battery', unit_of_measurement: '%', state: '90' },
    ] as never);
    getLocationSensors.mockResolvedValue([]);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Humidity'));
    await user.click(screen.getByRole('button', { name: /save/i }));
    await screen.findByText('Add the other sensors too?');
    await user.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => expect(createSensor).toHaveBeenCalledTimes(3));
    expect(createSensor).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        entity_id: 'sensor.drybox_1_temperature',
        alert_above: 30,
        alert_below: null,
        notify_on_alert: true,
        show_on_card: true,
      })
    );
    expect(createSensor).toHaveBeenNthCalledWith(
      3,
      expect.objectContaining({
        entity_id: 'sensor.drybox_1_battery',
        alert_above: null,
        alert_below: 15,
        notify_on_alert: true,
        show_on_card: false,
      })
    );
  });

  it('prefills the form from saved category defaults when picking an entity while creating', async () => {
    vi.mocked(window.localStorage.getItem).mockReturnValue(
      JSON.stringify({
        temperature: { alertAbove: '', alertBelow: '', notifyOnAlert: false, showOnCard: true },
        humidity: { alertAbove: '70', alertBelow: '20', notifyOnAlert: true, showOnCard: false },
        battery: { alertAbove: '', alertBelow: '', notifyOnAlert: false, showOnCard: true },
      })
    );
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_humidity', friendly_name: 'Drybox 1 Humidity', domain: 'sensor', device_class: 'humidity', unit_of_measurement: '%', state: '40' },
    ] as never);
    getLocationSensors.mockResolvedValue([]);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Humidity'));

    const [aboveInput, belowInput] = screen.getAllByRole('spinbutton');
    expect(aboveInput).toHaveValue(70);
    expect(belowInput).toHaveValue(20);
    expect(screen.getByRole('checkbox', { name: /show on filament card/i })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: /send a notification/i })).toBeChecked();
  });

  it('does not overwrite an edited sensor with saved defaults when re-selecting its entity', async () => {
    vi.mocked(window.localStorage.getItem).mockReturnValue(
      JSON.stringify({
        temperature: { alertAbove: '', alertBelow: '', notifyOnAlert: false, showOnCard: true },
        humidity: { alertAbove: '999', alertBelow: '111', notifyOnAlert: true, showOnCard: false },
        battery: { alertAbove: '', alertBelow: '', notifyOnAlert: false, showOnCard: true },
      })
    );
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_humidity', friendly_name: 'Drybox 1 Humidity', domain: 'sensor', device_class: 'humidity', unit_of_measurement: '%', state: '40' },
    ] as never);
    getLocationSensors.mockResolvedValue([]);

    const user = userEvent.setup();
    render(
      <LocationHASensorModal
        sensor={
          {
            id: 1,
            location_id: 7,
            name: 'sensor.drybox_1_humidity',
            entity_id: 'sensor.drybox_1_humidity',
            kind: 'numeric',
            device_class: 'humidity',
            unit: '%',
            alert_state: null,
            alert_above: 55,
            alert_below: null,
            notify_on_alert: false,
            show_on_card: true,
            sort_order: 0,
            last_state: null,
            last_changed: null,
            last_checked: null,
            created_at: '',
            updated_at: '',
          } as never
        }
        locations={LOCATIONS}
        onClose={() => {}}
      />
    );

    await user.click(await screen.findByText('Drybox 1 Humidity'));

    const [aboveInput] = screen.getAllByRole('spinbutton');
    expect(aboveInput).toHaveValue(55);
  });

  it('says so when no sibling entities are found for the first sensor of a location', async () => {
    getSettings.mockResolvedValue(settings());
    getEntities.mockResolvedValue([
      { entity_id: 'sensor.drybox_1_humidity', friendly_name: 'Drybox 1 Humidity', domain: 'sensor', device_class: 'humidity', unit_of_measurement: '%', state: '40' },
    ] as never);
    getLocationSensors.mockResolvedValue([]);

    const user = userEvent.setup();
    render(<LocationHASensorModal locations={LOCATIONS} onClose={() => {}} />);

    await user.click(await screen.findByText('Drybox 1 Humidity'));
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(screen.queryByText('Add the other sensors too?')).not.toBeInTheDocument();
    expect(
      await screen.findByText(/No matching temperature, humidity, or battery sensors found/)
    ).toBeInTheDocument();
    await waitFor(() => expect(createSensor).toHaveBeenCalledTimes(1));
  });
});
