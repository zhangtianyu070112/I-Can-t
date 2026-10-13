type StorageKind = 'local' | 'session'

function resolveStorage(kind: StorageKind): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage
  } catch {
    return null
  }
}

export function readStorage(kind: StorageKind, key: string): string | null {
  try {
    return resolveStorage(kind)?.getItem(key) ?? null
  } catch {
    return null
  }
}

export function writeStorage(kind: StorageKind, key: string, value: string): boolean {
  try {
    const storage = resolveStorage(kind)
    if (!storage) return false
    storage.setItem(key, value)
    return true
  } catch {
    return false
  }
}

export function removeStorage(kind: StorageKind, key: string): boolean {
  try {
    const storage = resolveStorage(kind)
    if (!storage) return false
    storage.removeItem(key)
    return true
  } catch {
    return false
  }
}
