import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocationSensorDefaultsModal } from '../../components/LocationSensorDefaultsModal';
import { render } from '../utils';

describe('LocationSensorDefaultsModal', () => {
  beforeEach(() => {
    vi.mocked(window.localStorage.getItem).mockReset();
    vi.mocked(window.localStorage.setItem).mockReset();
  });

  it('shows a section for each of the three auto-add categories', async () => {
    render(<LocationSensorDefaultsModal onClose={() => {}} />);

    expect(await screen.findByText('Temperature')).toBeInTheDocument();
    expect(screen.getByText('Humidity')).toBeInTheDocument();
    expect(screen.getByText('Battery')).toBeInTheDocument();
  });

  it('saves the entered defaults to localStorage and closes', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<LocationSensorDefaultsModal onClose={onClose} />);

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
    render(<LocationSensorDefaultsModal onClose={() => {}} />);

    await screen.findByText('Battery');

    expect(screen.getAllByText(/^Above/)).toHaveLength(2);
    expect(screen.getAllByText(/^Below/)).toHaveLength(3);
    expect(screen.getAllByRole('spinbutton')).toHaveLength(5);
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
    render(<LocationSensorDefaultsModal onClose={() => {}} />);

    await screen.findByText('Battery');
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(window.localStorage.setItem).toHaveBeenCalledWith(
      'bambuddy-location-sensor-auto-add-defaults',
      expect.stringContaining('"battery":{"alertAbove":"","alertBelow":"15"')
    );
  });

  it('does not persist anything when cancelled', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<LocationSensorDefaultsModal onClose={onClose} />);

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(window.localStorage.setItem).not.toHaveBeenCalledWith(
      'bambuddy-location-sensor-auto-add-defaults',
      expect.anything()
    );
    expect(onClose).toHaveBeenCalled();
  });
});
