import type { BackupRestore, Preferences } from '../types'
import { api, requestApi } from './api'

export const getPreferences = () => api<Preferences | null>('/backup/preferences')

export const patchPreferences = (preferences: Partial<Preferences>) =>
  api<Preferences>('/backup/preferences', { method: 'PATCH', body: preferences })

export const exportBackup = () => requestApi('/backup/export')

export function importBackup(file: File) {
  const body = new FormData()
  body.append('file', file)
  return api<BackupRestore>('/backup/import', { body })
}
