import { api } from '@/api/client'
import type { TunnelStatus } from '@/api/types'

export const systemApi = {
  getTunnelStatus: () => api<TunnelStatus>('/system/tunnel'),
}
