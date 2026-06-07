import { http } from './client'
import type { Disclosure } from '@/types'

export const disclosuresApi = {
  list: (params?: { code?: string; category?: string; hours?: number; limit?: number }) =>
    http.get<Disclosure[]>('/disclosures', { params }).then((r) => r.data),

  getById: (id: number) =>
    http.get<Disclosure>(`/disclosures/${id}`).then((r) => r.data),
}
