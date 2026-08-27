import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, X, AlertTriangle, Loader2 } from 'lucide-react';

interface SpoolBuddyWebInterfaceModalProps {
  hostname: string;
  ipAddress: string;
  onClose: () => void;
}

// Only the mixed-content case (https Bambuddy embedding a plain-http device)
// is deterministically detectable up front, so that one blocks the iframe
// attempt entirely. An X-Frame-Options/CSP frame-ancestors refusal or an
// unreachable device is NOT reliably detectable — browsers fire the
// iframe's onLoad even for a failed/blocked subframe navigation, so a
// "did it actually work" check would just be wrong. Rather than pretend to
// detect that, a permanent hint bar with an "open in new tab" escape hatch
// sits above the iframe at all times. The load timeout only exists to stop
// showing the spinner if onLoad never fires at all (a hung request).
const LOAD_TIMEOUT_MS = 6000;

export function SpoolBuddyWebInterfaceModal({ hostname, ipAddress, onClose }: SpoolBuddyWebInterfaceModalProps) {
  const { t } = useTranslation();
  const url = `http://${ipAddress}`;
  const isMixedContent = window.location.protocol === 'https:';
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (isMixedContent || loaded) return;
    const timer = setTimeout(() => setLoaded(true), LOAD_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [isMixedContent, loaded]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const titleId = 'spoolbuddy-web-interface-title';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div
        className="relative w-full max-w-4xl mx-4 h-[80vh] bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-xl shadow-2xl flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="flex items-center justify-between gap-4 px-4 py-3 border-b border-bambu-dark-tertiary shrink-0">
          <div className="min-w-0">
            <h2 id={titleId} className="text-sm font-semibold text-white truncate">
              {t('settings.spoolbuddy.webInterface')} — {hostname}
            </h2>
            <p className="text-xs text-bambu-gray font-mono truncate">{url}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 px-2 py-1 bg-bambu-dark hover:bg-bambu-dark-tertiary text-bambu-gray hover:text-white text-xs rounded-lg transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              {t('settings.spoolbuddy.openInNewTab')}
            </a>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 text-bambu-gray hover:text-white rounded"
              aria-label={t('common.close')}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {isMixedContent ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center px-6">
            <AlertTriangle className="w-8 h-8 text-amber-400" />
            <p className="text-sm text-bambu-gray max-w-sm">{t('settings.spoolbuddy.webInterfaceMixedContent')}</p>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 bg-bambu-green hover:bg-bambu-green/90 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              {t('settings.spoolbuddy.openInNewTab')}
            </a>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between gap-2 px-4 py-1.5 text-xs text-bambu-gray bg-bambu-dark/60 border-b border-bambu-dark-tertiary shrink-0">
              <span>{t('settings.spoolbuddy.webInterfaceHint')}</span>
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-bambu-green hover:underline shrink-0"
              >
                <ExternalLink className="w-3 h-3" />
                {t('settings.spoolbuddy.openInNewTab')}
              </a>
            </div>
            <div className="flex-1 min-h-0 relative">
              {!loaded && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <Loader2 className="w-6 h-6 animate-spin text-bambu-gray" />
                </div>
              )}
              {/* Sandboxed: the device page is third-party content reached by
                  an address the device itself reported at registration. The
                  grants are what a local device UI needs to function — scripts,
                  its own origin (so it can reach its own API), forms and
                  popups. Deliberately withheld: allow-top-navigation, which
                  would let the framed page navigate the whole Bambuddy tab
                  away, and allow-modals. */}
              <iframe
                src={url}
                title={`${hostname} web interface`}
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                className="w-full h-full border-0 rounded-b-xl bg-white"
                onLoad={() => setLoaded(true)}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
