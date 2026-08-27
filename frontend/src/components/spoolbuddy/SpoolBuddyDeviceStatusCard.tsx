import { useTranslation } from 'react-i18next';

interface SpoolBuddyDeviceStatusCardProps {
  deviceOnline: boolean;
  scaleDisplayValue: number | null;
  hasTag: boolean;
}

// Connection / scale / NFC status block shared by SpoolBuddyDashboard (full)
// and SpoolBuddyLiteDashboard (reduced) — identical on both, only the
// surrounding page layout and action buttons differ between variants.
export function SpoolBuddyDeviceStatusCard({ deviceOnline, scaleDisplayValue, hasTag }: SpoolBuddyDeviceStatusCardProps) {
  const { t } = useTranslation();

  return (
    <div className="border border-dashed border-zinc-700/50 rounded-xl p-4">
      <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide mb-3">
        {t('spoolbuddy.dashboard.device', 'Device')}
      </h2>

      <div className="space-y-2.5">
        {/* Connection status */}
        <div className="flex items-center gap-3">
          <div className={`w-2.5 h-2.5 rounded-full ${deviceOnline ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-base text-zinc-400">
            {deviceOnline ? t('spoolbuddy.status.online', 'Online') : t('spoolbuddy.status.offline', 'Disconnected')}
          </span>
        </div>

        {/* Scale weight */}
        <div className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg">
          <div className="flex items-center gap-2">
            <svg className={`w-4 h-4 ${deviceOnline ? 'text-green-500' : 'text-zinc-500'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
            </svg>
            <span className="text-sm text-zinc-500">{t('spoolbuddy.spool.scaleWeight', 'Scale')}</span>
          </div>
          <span className="text-lg font-mono font-semibold text-zinc-100">
            {scaleDisplayValue !== null ? `${Math.abs(scaleDisplayValue) <= 20 ? 0 : Math.round(Math.max(0, scaleDisplayValue))}g` : '—'}
          </span>
        </div>

        {/* NFC status */}
        <div className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg">
          <div className="flex items-center gap-2">
            <svg className={`w-4 h-4 ${deviceOnline ? 'text-green-500' : 'text-zinc-500'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a4 4 0 014-4z" />
            </svg>
            <span className="text-sm text-zinc-500">NFC</span>
          </div>
          <span className={`text-sm font-medium ${hasTag ? 'text-green-500' : 'text-zinc-500'}`}>
            {hasTag ? t('spoolbuddy.dashboard.tagDetected', 'Tag detected') : t('spoolbuddy.dashboard.noTag', 'No tag')}
          </span>
        </div>
      </div>
    </div>
  );
}
