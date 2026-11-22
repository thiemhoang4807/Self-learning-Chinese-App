import type { ItemType } from '../types'

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  signal?: AbortSignal
  acceptStatus?: number
}

export async function requestApi(path: string, options?: RequestOptions): Promise<Response> {
  const body = options?.body
  const multipart = body instanceof FormData
  let response: Response
  try {
    response = await fetch('/api' + path, {
      method: options?.method ?? (body === undefined ? 'GET' : 'POST'),
      signal: options?.signal,
      headers: body === undefined || multipart ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
    })
  } catch (error) {
    if (options?.signal?.aborted) throw error
    throw new ApiError(0, 'Chưa kết nối được với máy chủ. Bạn thử lại nhé.')
  }

  if (response.ok || response.status === options?.acceptStatus) return response
  const payload = await response.json().catch(() => null)
  const detail = payload?.detail
  const viDetail = typeof detail === 'string' && /[À-ỹ]/u.test(detail) ? detail : null
  const fallback = response.status === 422
    ? 'Một số thông tin chưa đúng định dạng. Bạn kiểm tra lại nhé.'
    : response.status === 404
      ? 'Không tìm thấy nội dung này.'
      : response.status === 429
        ? 'Dịch vụ đang bận. Bạn thử lại sau một chút nhé.'
        : 'Chưa thực hiện được thao tác này. Bạn thử lại nhé.'
  throw new ApiError(response.status, viDetail || fallback)
}

export async function api<T>(path: string, options?: RequestOptions): Promise<T> {
  const response = await requestApi(path, options)
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Đã có lỗi xảy ra. Bạn thử lại nhé.'
}

export function withQuery(path: string, params: Record<string, string | number | boolean | null | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  return query.size ? path + '?' + query.toString() : path
}

export const queueItems = (itemType: ItemType, itemIds: number[]) =>
  api<{ queued: number }>('/study/queue', { body: { item_type: itemType, item_ids: itemIds } })

export const audioUrl = (text: string, rate = 1) => withQuery('/api/audio/tts', { text, rate })

export function reviewToken() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 15) | 64
  bytes[8] = (bytes[8] & 63) | 128
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-')
}
