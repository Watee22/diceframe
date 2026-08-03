import { api } from '@/api/client'
import { i18n } from '@/i18n'
import type { CharacterImportResponse } from '@/api/types'

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result || '')
      const comma = result.indexOf(',')
      resolve(comma >= 0 ? result.slice(comma + 1) : result)
    }
    reader.onerror = () => reject(new Error(i18n.global.t('fileReadFailed')))
    reader.readAsDataURL(file)
  })
}

export async function importTavernCard(
  file: File,
  opts?: { target?: 'character_card' | 'npc'; worldId?: string },
): Promise<CharacterImportResponse> {
  const fileData = await fileToBase64(file)
  const r = await api<CharacterImportResponse>('/character-cards/import', {
    method: 'POST',
    body: JSON.stringify({
      file_name: file.name,
      file_data: fileData,
      target: opts?.target,
      world_id: opts?.worldId,
    }),
  })
  if (!r.ok) throw new Error(r.error || i18n.global.t('importFailed'))
  return r
}
