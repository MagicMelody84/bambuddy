import { useOutletContext } from 'react-router-dom';
import type { SpoolBuddyOutletContext } from '../../components/spoolbuddy/SpoolBuddyLayout';
import { SpoolBuddyDashboard } from './SpoolBuddyDashboard';
import { SpoolBuddyLiteDashboard } from './SpoolBuddyLiteDashboard';

// Picks the dashboard variant based on the registered device's hardware_variant.
export function SpoolBuddyOverview() {
  const { device, deviceLoading } = useOutletContext<SpoolBuddyOutletContext>();
  // Render nothing while the device list is still loading rather than
  // defaulting to the full dashboard — `device` is undefined until the
  // query resolves, so guessing "standard" here flashed the full
  // printer/AMS dashboard on every load of Lite hardware before flipping
  // to the Lite one once the query settled.
  if (deviceLoading) return null;
  return device?.hardware_variant === 'lite' ? <SpoolBuddyLiteDashboard /> : <SpoolBuddyDashboard />;
}
