import { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { MapPin, Plus, Loader2, Pencil, Trash2, X, Search, ArrowUp, ArrowDown, ArrowUpDown, Tag } from 'lucide-react';
import { api, type StorageLocation } from '../api/client';
import { Button } from './Button';
import { ConfirmModal } from './ConfirmModal';
import { useToast } from '../contexts/ToastContext';
import { inventoryLocationsQueryKey, invalidateInventoryLocations } from '../utils/inventoryQueries';

type SortDirection = 'asc' | 'desc';
type SortState = { column: 'name' | 'sensors' | 'spools'; direction: SortDirection } | null;

const columnSortValues: Record<'name' | 'sensors' | 'spools', (loc: StorageLocation, sensorCounts: Record<number, number>) => string | number> = {
  name: (loc) => loc.name.toLowerCase(),
  sensors: (loc, sensorCounts) => sensorCounts[loc.id] ?? 0,
  spools: (loc) => loc.spool_count,
};

interface LocationsModalProps {
  open: boolean;
  onClose: () => void;
  // Optional even with startCreating: a caller that just wants the inline
  // "create a location" dialog without picking one afterward can omit it.
  // The save always closes the modal regardless of whether this is set.
  onPickLocation?: (locationId: number) => void;
  startCreating?: boolean;
}

export function LocationsModal({ open, onClose, onPickLocation, startCreating }: LocationsModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<StorageLocation | null>(null);
  const [name, setName] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<StorageLocation | null>(null);
  const [search, setSearch] = useState('');
  const [sortState, setSortState] = useState<SortState>(null);

  const { data: locations = [], isLoading } = useQuery({
    queryKey: inventoryLocationsQueryKey,
    queryFn: api.getLocations,
    enabled: open,
  });

  const { data: locationSensors = [] } = useQuery({
    queryKey: ['locationHaSensors'],
    queryFn: () => api.getLocationHASensors(),
    enabled: open,
  });

  const sensorCountByLocation = locationSensors.reduce<Record<number, number>>((acc, sensor) => {
    acc[sensor.location_id] = (acc[sensor.location_id] ?? 0) + 1;
    return acc;
  }, {});

  const filteredLocations = locations.filter((loc) => loc.name.toLowerCase().includes(search.trim().toLowerCase()));

  const sortedLocations = sortState
    ? [...filteredLocations].sort((a, b) => {
        const extractor = columnSortValues[sortState.column];
        const va = extractor(a, sensorCountByLocation);
        const vb = extractor(b, sensorCountByLocation);
        if (va < vb) return sortState.direction === 'asc' ? -1 : 1;
        if (va > vb) return sortState.direction === 'asc' ? 1 : -1;
        return 0;
      })
    : filteredLocations;

  const handleSort = (column: 'name' | 'sensors' | 'spools') => {
    setSortState((prev) => {
      if (prev?.column === column) {
        return prev.direction === 'asc' ? { column, direction: 'desc' } : null;
      }
      return { column, direction: 'asc' };
    });
  };

  const invalidate = () => {
    invalidateInventoryLocations(queryClient);
    queryClient.invalidateQueries({ queryKey: ['inventory-spools'] });
    queryClient.invalidateQueries({ queryKey: ['spoolman-inventory-spools'] });
    queryClient.invalidateQueries({ queryKey: ['locationHaSensors'] });
    queryClient.invalidateQueries({ queryKey: ['locationHaSensorReadings'] });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const trimmed = name.trim();
      if (!trimmed) throw new Error(t('locations.nameRequired'));
      if (editing) {
        return api.updateLocation(editing.id, { name: trimmed });
      }
      return api.createLocation({ name: trimmed });
    },
    onSuccess: (saved) => {
      showToast(t(editing ? 'locations.updated' : 'locations.created'), 'success');
      invalidate();
      // startCreating mode has no location-list view to fall back to (see the
      // render branch below and closeEditor's own unconditional onClose), so
      // a save here must always close — with or without onPickLocation, which
      // is optional by design for a caller that only wants location
      // management, not a picker. Gating this on onPickLocation being set
      // used to leave editorOpen false with open still true: nothing left to
      // render, but the caller never told to close.
      if (!editing && startCreating) {
        onPickLocation?.(saved.id);
        onClose();
        return;
      }
      setEditorOpen(false);
      setEditing(null);
      setName('');
    },
    onError: (err: Error) => {
      showToast(err.message || t('locations.saveFailed'), 'error');
    },
  });

  const clearRfidMutation = useMutation({
    mutationFn: () => api.updateLocation(editing!.id, { tag_uid: null }),
    onSuccess: () => {
      showToast(t('locations.rfidCleared'), 'success');
      invalidate();
      setEditing((prev) => (prev ? { ...prev, tag_uid: null } : prev));
    },
    onError: (err: Error) => {
      showToast(err.message || t('locations.tagClearFailed'), 'error');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteLocation(id),
    onSuccess: () => {
      showToast(t('locations.deleted'), 'success');
      setDeleteTarget(null);
      invalidate();
    },
    onError: (err: Error) => {
      showToast(err.message || t('locations.deleteFailed'), 'error');
    },
  });

  const openCreate = () => {
    setEditing(null);
    setName('');
    setEditorOpen(true);
  };

  useEffect(() => {
    if (open && startCreating) {
      setEditing(null);
      setName('');
      setEditorOpen(true);
    }
  }, [open, startCreating]);

  const openEdit = (location: StorageLocation) => {
    setEditing(location);
    setName(location.name);
    setEditorOpen(true);
  };

  const closeEditor = useCallback(() => {
    if (saveMutation.isPending || clearRfidMutation.isPending) return;
    if (startCreating) {
      onClose();
      return;
    }
    setEditorOpen(false);
    setEditing(null);
    setName('');
  }, [saveMutation.isPending, clearRfidMutation.isPending, startCreating, onClose]);

  // Esc closes the inner editor first; if it's closed, Esc closes the outer
  // modal — but only when no mutation is mid-flight, so a stray keypress
  // during a network round-trip doesn't drop the user back into the
  // inventory page with an orphaned spinner (or, for clearRfidMutation,
  // doesn't let the editor be reassigned to a different location before
  // the in-flight clear's onSuccess callback fires against it).
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (saveMutation.isPending || deleteMutation.isPending || clearRfidMutation.isPending) return;
      if (editorOpen) {
        closeEditor();
      } else if (!deleteTarget) {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [
    open,
    editorOpen,
    deleteTarget,
    saveMutation.isPending,
    deleteMutation.isPending,
    clearRfidMutation.isPending,
    closeEditor,
    onClose,
  ]);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate();
  };

  if (!open) return null;

  const modalTitleId = 'locations-modal-title';
  const editorTitleId = 'location-editor-title';

  const editorForm = (
    <form onSubmit={handleSave}>
      <label className="block text-sm font-medium text-bambu-gray mb-1" htmlFor="location-name">
        {t('locations.name')}
      </label>
      <input
        id="location-name"
        type="text"
        maxLength={255}
        className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:outline-none focus:border-bambu-green mb-4"
        placeholder={t('locations.createPlaceholder')}
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />
      <div className="flex gap-2">
        {editing && (
          <Button
            type="button"
            variant="secondary"
            className="mr-auto"
            onClick={() => clearRfidMutation.mutate()}
            disabled={clearRfidMutation.isPending || !editing.tag_uid}
          >
            <Tag className="w-4 h-4" />
            {t('locations.clearRfid')}
          </Button>
        )}
        <Button type="button" variant="secondary" onClick={closeEditor}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" disabled={saveMutation.isPending || !name.trim()}>
          {saveMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
          {t('common.save')}
        </Button>
      </div>
    </form>
  );

  if (startCreating) {
    return editorOpen ? (
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        <div className="absolute inset-0 bg-black/60" onClick={closeEditor} />
        <div
          className="relative w-full max-w-md mx-4 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-xl p-6 shadow-2xl"
          role="dialog"
          aria-modal="true"
          aria-labelledby={editorTitleId}
        >
          <h3 id={editorTitleId} className="text-lg font-semibold text-white mb-4">
            {t('locations.add')}
          </h3>
          {editorForm}
        </div>
      </div>
    ) : null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/60"
        onClick={() => {
          if (saveMutation.isPending || deleteMutation.isPending) return;
          onClose();
        }}
      />
      <div
        className="relative w-full max-w-2xl mx-4 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-xl shadow-2xl max-h-[90vh] flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby={modalTitleId}
      >
        <div className="flex items-center justify-between gap-4 px-6 py-4 border-b border-bambu-dark-tertiary">
          <div>
            <h2 id={modalTitleId} className="text-lg font-semibold text-white flex items-center gap-2">
              <MapPin className="w-5 h-5 text-bambu-green" />
              {t('locations.title')}
            </h2>
            <p className="text-bambu-gray text-sm mt-0.5">{t('locations.subtitle')}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={openCreate}>
              <Plus className="w-4 h-4" />
              {t('locations.add')}
            </Button>
            <button
              type="button"
              className="p-1.5 text-bambu-gray hover:text-white rounded"
              onClick={onClose}
              aria-label={t('common.close')}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="px-6 py-3 border-b border-bambu-dark-tertiary">
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-bambu-gray/50" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('locations.search')}
              className="w-full pl-10 pr-8 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm placeholder:text-bambu-gray/50 focus:outline-none focus:border-bambu-green"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-bambu-gray hover:text-white"
                aria-label={t('common.clear')}
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Fixed to header + 10 rows (40px + 10 * ~47.8px) so the modal
            doesn't grow/shrink as the search narrows the result count. */}
        <div className="overflow-y-auto h-[518px]">
          {isLoading ? (
            <div className="flex items-center justify-center py-16 text-bambu-gray">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              {t('common.loading')}
            </div>
          ) : locations.length === 0 ? (
            <div className="py-16 text-center text-bambu-gray">{t('locations.empty')}</div>
          ) : sortedLocations.length === 0 ? (
            <div className="py-16 text-center text-bambu-gray">{t('locations.noSearchResults')}</div>
          ) : (
            <table className="w-full text-sm table-fixed">
              <thead>
                <tr className="border-b border-bambu-dark-tertiary text-left text-bambu-gray">
                  <th
                    className={`px-4 py-3 font-medium cursor-pointer select-none hover:text-bambu-green transition-colors ${sortState?.column === 'name' ? 'text-bambu-green' : ''}`}
                    onClick={() => handleSort('name')}
                  >
                    <span className="inline-flex items-center gap-1">
                      {t('locations.name')}
                      {sortState?.column === 'name' ? (
                        sortState.direction === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
                      ) : (
                        <ArrowUpDown className="w-3 h-3 opacity-30" />
                      )}
                    </span>
                  </th>
                  <th
                    className={`px-2 py-3 font-medium text-right w-24 cursor-pointer select-none hover:text-bambu-green transition-colors ${sortState?.column === 'sensors' ? 'text-bambu-green' : ''}`}
                    onClick={() => handleSort('sensors')}
                  >
                    <span className="inline-flex items-center gap-1 justify-end">
                      {t('locations.sensors')}
                      {sortState?.column === 'sensors' ? (
                        sortState.direction === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
                      ) : (
                        <ArrowUpDown className="w-3 h-3 opacity-30" />
                      )}
                    </span>
                  </th>
                  <th
                    className={`pl-[28px] pr-4 py-3 font-medium text-right w-28 cursor-pointer select-none hover:text-bambu-green transition-colors ${sortState?.column === 'spools' ? 'text-bambu-green' : ''}`}
                    onClick={() => handleSort('spools')}
                  >
                    <span className="inline-flex items-center gap-1 justify-end">
                      {t('locations.spools')}
                      {sortState?.column === 'spools' ? (
                        sortState.direction === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
                      ) : (
                        <ArrowUpDown className="w-3 h-3 opacity-30" />
                      )}
                    </span>
                  </th>
                  <th className="px-4 py-3 font-medium text-right w-32">{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {sortedLocations.map((loc) => (
                  <tr
                    key={loc.id}
                    className="border-b border-bambu-dark-tertiary/60 hover:bg-bambu-dark-tertiary/30 cursor-pointer"
                    onClick={() => {
                      if (onPickLocation) {
                        onPickLocation(loc.id);
                        onClose();
                      }
                    }}
                  >
                    <td className="px-4 py-3 text-white font-medium truncate">
                      <span className="inline-flex items-center gap-1.5">
                        {loc.name}
                        {loc.tag_uid && (
                          <Tag
                            className="w-3.5 h-3.5 text-bambu-green shrink-0"
                            aria-label={t('locations.hasTag')}
                          >
                            <title>{loc.tag_uid}</title>
                          </Tag>
                        )}
                      </span>
                    </td>
                    <td className="px-2 py-3 text-right text-bambu-gray">{sensorCountByLocation[loc.id] ?? 0}</td>
                    <td className="pl-[28px] pr-4 py-3 text-right text-bambu-gray">{loc.spool_count}</td>
                    <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          className="p-1.5 text-bambu-gray hover:text-bambu-green rounded"
                          onClick={() => openEdit(loc)}
                          title={t('common.edit')}
                          aria-label={t('locations.editAria', { name: loc.name, defaultValue: `Edit ${loc.name}` })}
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          className="p-1.5 text-bambu-gray hover:text-red-600 dark:hover:text-red-400 rounded disabled:opacity-40"
                          disabled={loc.spool_count > 0}
                          onClick={() => setDeleteTarget(loc)}
                          title={loc.spool_count > 0 ? t('locations.deleteBlocked') : t('common.delete')}
                          aria-label={t('locations.deleteAria', { name: loc.name, defaultValue: `Delete ${loc.name}` })}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {editorOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" onClick={closeEditor} />
          <div
            className="relative w-full max-w-md mx-4 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-xl p-6 shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby={editorTitleId}
          >
            <h3 id={editorTitleId} className="text-lg font-semibold text-white mb-4">
              {editing ? t('locations.edit') : t('locations.add')}
            </h3>
            {editorForm}
          </div>
        </div>
      )}

      {deleteTarget && (
        <ConfirmModal
          title={t('locations.confirmDelete', { name: deleteTarget.name })}
          message={
            sensorCountByLocation[deleteTarget.id]
              ? t('locations.confirmDeleteMessageWithSensors')
              : t('locations.confirmDeleteMessage')
          }
          confirmText={t('common.delete')}
          variant="danger"
          isLoading={deleteMutation.isPending}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
