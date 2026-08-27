import { useState } from 'react';
import { useOutletContext, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { RotateCw, Settings as SettingsIcon } from 'lucide-react';
import type { SpoolBuddyOutletContext } from '../../components/spoolbuddy/SpoolBuddyLayout';
import { spoolbuddyApi } from '../../api/client';
import { SpoolInfoCard, UnknownTagCard } from '../../components/spoolbuddy/SpoolInfoCard';
import { SpoolBuddyDeviceStatusCard } from '../../components/spoolbuddy/SpoolBuddyDeviceStatusCard';
import { ConfirmModal } from '../../components/ConfirmModal';
import { useToast } from '../../contexts/ToastContext';
import { useStableScaleWeight } from '../../hooks/useStableScaleWeight';
import { IdleSpool, DeviceOfflineState } from './SpoolBuddyDashboard';

// --- SpoolBuddy Lite dashboard: scale + NFC status only, no printer/AMS
// integration. Actions are reduced to Reboot and a link to Settings — see
// SpoolBuddyDashboard.tsx for the full (standard hardware) overview.
export function SpoolBuddyLiteDashboard() {
  const { sbState, device } = useOutletContext<SpoolBuddyOutletContext>();
  const { t } = useTranslation();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const currentTagId = sbState.matchedSpool?.tag_uid ?? sbState.unknownTagUid ?? null;
  const currentWeight = sbState.weight;
  const scaleDisplayValue = useStableScaleWeight(currentWeight, sbState.weightStable);

  const [confirmReboot, setConfirmReboot] = useState(false);
  const rebootMutation = useMutation({
    mutationFn: () => spoolbuddyApi.systemCommand(device!.device_id, 'reboot'),
    onSuccess: () => {
      showToast(t('settings.spoolbuddy.commandQueued'), 'success');
      setConfirmReboot(false);
    },
    onError: (err: Error) => {
      showToast(err.message || t('settings.spoolbuddy.commandError'), 'error');
    },
  });

  return (
    <div className="h-full flex flex-col p-4 gap-4">
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Left column: Device status */}
        <div className="w-5/12 flex flex-col min-h-0">
          <SpoolBuddyDeviceStatusCard
            deviceOnline={sbState.deviceOnline}
            scaleDisplayValue={scaleDisplayValue}
            hasTag={Boolean(currentTagId)}
          />

          {/* Actions: Reboot + Settings only */}
          <div className="mt-3 border border-dashed border-zinc-700/50 rounded-xl p-4">
            <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide mb-3">
              {t('common.actions', 'Actions')}
            </h2>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setConfirmReboot(true)}
                disabled={!device || !sbState.deviceOnline}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-lg text-sm font-medium bg-amber-900/30 text-amber-400 hover:bg-amber-900/50 transition-colors min-h-[44px] disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <RotateCw className="w-4 h-4" />
                {t('settings.spoolbuddy.reboot', 'Reboot')}
              </button>
              <button
                type="button"
                onClick={() => navigate('/spoolbuddy/settings')}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-lg text-sm font-medium bg-zinc-800/60 text-zinc-300 hover:bg-zinc-700/60 transition-colors min-h-[44px]"
              >
                <SettingsIcon className="w-4 h-4" />
                {t('spoolbuddy.nav.settings', 'Settings')}
              </button>
            </div>
          </div>
        </div>

        {/* Right column: Current Spool */}
        <div className="w-7/12 min-h-0">
          <div className="border border-dashed border-zinc-700/50 rounded-xl p-6 h-full flex flex-col">
            <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide mb-4 shrink-0">
              {t('spoolbuddy.dashboard.currentSpool', 'Current Spool')}
            </h2>
            <div className="flex-1 flex items-center justify-center min-h-0">
              {!sbState.deviceOnline ? (
                <DeviceOfflineState />
              ) : sbState.matchedSpool ? (
                <SpoolInfoCard spool={sbState.matchedSpool} scaleWeight={currentWeight} />
              ) : sbState.unknownTagUid ? (
                <UnknownTagCard tagUid={sbState.unknownTagUid} scaleWeight={currentWeight} />
              ) : (
                <IdleSpool />
              )}
            </div>
          </div>
        </div>
      </div>

      {confirmReboot && device && (
        <ConfirmModal
          variant="danger"
          title={t('settings.spoolbuddy.rebootConfirmTitle')}
          message={t('settings.spoolbuddy.rebootConfirmBody', { hostname: device.hostname })}
          confirmText={t('settings.spoolbuddy.commandConfirm')}
          isLoading={rebootMutation.isPending}
          onConfirm={() => rebootMutation.mutate()}
          onCancel={() => setConfirmReboot(false)}
        />
      )}
    </div>
  );
}
