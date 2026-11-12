import { api } from '../api';
import { isNativePlatform } from '../platform';

const STORAGE_KEY = 'waselni.stadia.key.v1';

type StoredKey = { role: string; key: string };

let memoryKey: string | null = null;
let memoryRole: string | null = null;
let activeRole: string | null = null;
let pending: Promise<string | null> | null = null;
let generation = 0;

async function secureStorage() {
  const module = await import('capacitor-secure-storage-plugin');
  return module.SecureStoragePlugin;
}

async function readStored(): Promise<StoredKey | null> {
  try {
    const plugin = await secureStorage();
    const { value } = await plugin.get({ key: STORAGE_KEY });
    const parsed = JSON.parse(value) as Partial<StoredKey>;
    if (parsed && typeof parsed.key === 'string' && typeof parsed.role === 'string') {
      return { role: parsed.role, key: parsed.key };
    }
  } catch {}
  return null;
}

async function writeStored(value: StoredKey): Promise<void> {
  try {
    const plugin = await secureStorage();
    await plugin.set({ key: STORAGE_KEY, value: JSON.stringify(value) });
  } catch {}
}

async function removeStored(): Promise<void> {
  try {
    const plugin = await secureStorage();
    await plugin.remove({ key: STORAGE_KEY });
  } catch {}
}

export function setStadiaRole(role?: string | null): void {
  const next = role || null;
  if (next === activeRole) return;
  activeRole = next;
  if (memoryKey && memoryRole && next && next !== memoryRole) {
    memoryKey = null;
    memoryRole = null;
    pending = null;
    generation += 1;
  }
}

export function clearStadiaKey(): void {
  memoryKey = null;
  memoryRole = null;
  activeRole = null;
  pending = null;
  generation += 1;
  void removeStored();
}

async function fetchFresh(): Promise<StoredKey> {
  const config = await api('/map/config/', { cache: 'no-store' });
  const key = typeof config?.api_key === 'string' ? config.api_key.trim() : '';
  if (!key) throw new Error('Map service is not configured.');
  return { role: typeof config?.role === 'string' ? config.role : '', key };
}

export async function getStadiaKey(): Promise<string | null> {
  if (!isNativePlatform()) return null;
  if (memoryKey) return memoryKey;
  if (pending) return pending;
  const requestedGeneration = generation;
  const task = (async () => {
    try {
      const fresh = await fetchFresh();
      if (requestedGeneration !== generation) return null;
      memoryKey = fresh.key;
      memoryRole = fresh.role || activeRole;
      await writeStored(fresh);
      return memoryKey;
    } catch (error) {
      const stored = await readStored();
      if (stored && activeRole && stored.role === activeRole && requestedGeneration === generation) {
        memoryKey = stored.key;
        memoryRole = stored.role;
        return memoryKey;
      }
      throw error;
    }
  })();
  pending = task;
  try {
    return await task;
  } finally {
    if (pending === task) pending = null;
  }
}
