import { useRef } from 'react';

const WEIGHT_THRESHOLD = 3; // grams - ignore changes smaller than this

// Stabilized scale display: only updates when the change exceeds the
// threshold (or the reading is marked stable), so a noisy live scale
// doesn't bounce the displayed number on every WebSocket tick.
export function useStableScaleWeight(currentWeight: number | null, weightStable: boolean): number | null {
  const stableDisplayWeight = useRef<number | null>(null);
  if (currentWeight === null) {
    stableDisplayWeight.current = null;
  } else if (
    stableDisplayWeight.current === null ||
    Math.abs(currentWeight - stableDisplayWeight.current) >= WEIGHT_THRESHOLD ||
    weightStable
  ) {
    stableDisplayWeight.current = currentWeight;
  }
  return stableDisplayWeight.current;
}
