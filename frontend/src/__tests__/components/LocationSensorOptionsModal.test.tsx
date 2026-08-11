import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '../../api/client';
import { LocationSensorOptionsModal } from '../../components/LocationSensorOptionsModal';
import { render } from '../utils';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    api: {
      ...actual.api,
      getLocationHASensors: vi.fn(),
      updateLocationHASensor: vi.fn(),
      getSettings: vi.fn(),
      updateSettings: vi.fn(),
    },
  };
});

const getLocationSensors = vi.mocked(api.getLocationHASensors);
const updateSensor = vi.mocked(api.updateLocationHASensor);
const getSettings = vi.mocked(api.getSettings);
const updateSettings = vi.mocked(api.updateSettings);

describe('LocationSensorOptionsModal', () => {
  beforeEach(() => {
    vi.mocked(window.localStorage.getItem).mockReset();
    vi.mocked(window.localStorage.setItem).mockReset();
    getLocationSensors.mockReset();
    updateSensor.mockReset();
    getSettings.mockReset();
    updateSettings.mockReset();
    getSettings.mockResolvedValue({ location_sensor_poll_interval: 120 } as never);
    updateSettings.mockResolvedValue({} as never);
  });

  it('shows a section for each of the three auto-add categories', async () => {
    render(<LocationSensorOptionsModal onClose={() => {}} />);

    expect(await screen.findByText('Temperature')).toBeInTheDocument();
    expect(screen.getByText('Humidity')).toBeInTheDocument();
    expect(screen.getByText('Battery')).toBeInTheDocument();
  });

  it('saves the entered defaults to localStorage and closes', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<LocationSensorOptionsModal onClose={onClose} />);

    const aboveInputs = screen.getAllByText('Above °C');
    expect(aboveInputs.length).toBeGreaterThan(0);

    const inputs = screen.getAllByRole('spinbutton');
    await user.type(inputs[0], '30');

    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(window.localStorage.setItem).toHaveBeenCalledWith(
      'bambuddy-location-sensor-auto-add-defaults',
      expect.stringContaining('"alertAbove":"30"')
    );
    expect(onClose).toHaveBeenCalled();
  });

  it('does not offer an "above" threshold for the battery section', async () => {
    render(<LocationSensorOptionsModal onClose={() => {}} />);

    await screen.findByText('Battery');

    expect(screen.getAllByText(/^Above (°C|%)$/)).toHaveLength(2);
    expect(screen.getAllByText(/^Below (°C|%)$/)).toHaveLength(3);
    expect(screen.getAllByRole('spinbutton')).toHaveLength(6);
  });

  it('clears a stale saved "above" value for battery on save', async () => {
    vi.mocked(window.localStorage.getItem).mockReturnValue(
      JSON.stringify({
        temperature: { alertAbove: '', alertBelow: '', notifyOnAlert: false, showOnCard: true },
        humidity: { alertAbove: '', alertBelow: '', notifyOnAlert: false, showOnCard: true },
        battery: { alertAbove: '95', alertBelow: '15', notifyOnAlert: true, showOnCard: true },
      })
    );
    const user = userEvent.setup();
    render(<LocationSensorOptionsModal onClose={() => {}} />);

    await screen.findByText('Battery');
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(window.localStorage.setItem).toHaveBeenCalledWith(
      'bambuddy-location-sensor-auto-add-defaults',
      expect.stringContaining('"battery":{"alertAbove":"","alertBelow":"15"')
    );
  });

  it('saves the chosen above/below/optimal alert colors', async () => {
    const user = userEvent.setup();
    render(<LocationSensorOptionsModal onClose={() => {}} />);

    await screen.findByText('Battery');

    await user.selectOptions(screen.getByLabelText(/above threshold color/i), 'orange');
    await user.selectOptions(screen.getByLabelText(/below threshold color/i), 'purple');
    await user.selectOptions(screen.getByLabelText(/optimal value color/i), 'blue');
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(window.localStorage.setItem).toHaveBeenCalledWith('bambuddy-location-sensor-alert-above-color', 'orange');
    expect(window.localStorage.setItem).toHaveBeenCalledWith('bambuddy-location-sensor-alert-below-color', 'purple');
    expect(window.localStorage.setItem).toHaveBeenCalledWith('bambuddy-location-sensor-alert-optimal-color', 'blue');
  });

  it('loads the current poll interval and saves a changed value', async () => {
    getSettings.mockResolvedValue({ location_sensor_poll_interval: 300 } as never);
    const user = userEvent.setup();
    render(<LocationSensorOptionsModal onClose={() => {}} />);

    const input = await screen.findByLabelText(/update interval/i);
    await waitFor(() => expect(input).toHaveValue(300));

    await user.clear(input);
    await user.type(input, '90');
    await user.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith(expect.objectContaining({ location_sensor_poll_interval: 90 }))
    );
  });

  it('clamps a poll interval below the 60s minimum on blur', async () => {
    const user = userEvent.setup();
    render(<LocationSensorOptionsModal onClose={() => {}} />);

    const input = await screen.findByLabelText(/update interval/i);
    await waitFor(() => expect(input).toHaveValue(120));

    await user.clear(input);
    await user.type(input, '10');
    await user.tab();

    expect(input).toHaveValue(60);
  });

  it('disables the color pickers when colorizing is turned off', async () => {
    const user = userEvent.setup();
    render(<LocationSensorOptionsModal onClose={() => {}} />);

    await screen.findByText('Battery');

    await user.click(screen.getByLabelText(/colorize sensor values/i));

    expect(screen.getByLabelText(/above threshold color/i)).toBeDisabled();
    expect(screen.getByLabelText(/below threshold color/i)).toBeDisabled();
    expect(screen.getByLabelText(/optimal value color/i)).toBeDisabled();
  });

  it('asks for confirmation before overwriting existing sensors, then applies the configured values', async () => {
    getLocationSensors.mockResolvedValue([
      { id: 1, device_class: 'temperature' } as never,
      { id: 2, device_class: 'humidity' } as never,
      { id: 3, device_class: 'battery' } as never,
      { id: 4, device_class: 'door' } as never,
    ]);
    updateSensor.mockResolvedValue({} as never);
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<LocationSensorOptionsModal onClose={onClose} />);

    await screen.findByText('Battery');
    const inputs = screen.getAllByRole('spinbutton');
    await user.type(inputs[0], '30');

    await user.click(screen.getByRole('button', { name: /^reset$/i }));
    expect(updateSensor).not.toHaveBeenCalled();
    expect(await screen.findByText(/cannot be undone/i)).toBeInTheDocument();

    await user.click(screen.getAllByRole('button', { name: /^reset$/i })[1]);

    await waitFor(() => expect(updateSensor).toHaveBeenCalledTimes(3));
    expect(updateSensor).toHaveBeenCalledWith(1, expect.objectContaining({ alert_above: 30 }));
    expect(updateSensor).toHaveBeenCalledWith(3, expect.objectContaining({ alert_above: null }));
    expect(onClose).toHaveBeenCalled();

    // The on-screen values (not yet saved via the Save button) must be
    // persisted before the bulk apply, so future auto-added sensors use them too.
    expect(window.localStorage.setItem).toHaveBeenCalledWith(
      'bambuddy-location-sensor-auto-add-defaults',
      expect.stringContaining('"alertAbove":"30"')
    );
  });

  it('does not overwrite anything when the reset confirmation is cancelled', async () => {
    getLocationSensors.mockResolvedValue([{ id: 1, device_class: 'temperature' } as never]);
    const user = userEvent.setup();
    render(<LocationSensorOptionsModal onClose={() => {}} />);

    await screen.findByText('Battery');
    await user.click(screen.getByRole('button', { name: /^reset$/i }));
    await screen.findByText(/cannot be undone/i);

    const cancelButtons = screen.getAllByRole('button', { name: /cancel/i });
    await user.click(cancelButtons[cancelButtons.length - 1]);

    expect(updateSensor).not.toHaveBeenCalled();
  });

  it('does not persist anything when cancelled', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<LocationSensorOptionsModal onClose={onClose} />);

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(window.localStorage.setItem).not.toHaveBeenCalledWith(
      'bambuddy-location-sensor-auto-add-defaults',
      expect.anything()
    );
    expect(onClose).toHaveBeenCalled();
  });
});
