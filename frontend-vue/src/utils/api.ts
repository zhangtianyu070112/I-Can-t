export type ApiError = {
  code: string
  message: string
}

export type ApiResponse<T> = {
  request_id: string
  success: boolean
  data: T
  error?: ApiError | null
}

export async function apiPost<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  const resp = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return resp.json()
}

export async function apiGet<T>(path: string): Promise<ApiResponse<T>> {
  const resp = await fetch(path)
  return resp.json()
}

export type StreamEvent = {
  event: 'start' | 'status' | 'chunk' | 'final' | 'error' | 'done' | string
  data: any
}

export async function apiStream<T>(
  path: string,
  body: unknown,
  handlers: {
    onStart?: (data: any) => void
    onStatus?: (data: any) => void
    onChunk?: (data: any) => void
    onFinal?: (data: T) => void
    onError?: (message: string, data?: any) => void
    onDone?: () => void
  },
): Promise<void> {
  const resp = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
  })

  if (!resp.ok || !resp.body) {
    throw new Error(`流式请求失败：HTTP ${resp.status}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''

    for (const rawEvent of events) {
      const line = rawEvent
        .split('\n')
        .map((line) => line.trim())
        .find((line) => line.startsWith('data: '))
      if (!line) continue
      const payload = JSON.parse(line.slice(6)) as StreamEvent
      if (payload.event === 'start') handlers.onStart?.(payload.data)
      else if (payload.event === 'status') handlers.onStatus?.(payload.data)
      else if (payload.event === 'chunk') handlers.onChunk?.(payload.data)
      else if (payload.event === 'final') handlers.onFinal?.(payload.data as T)
      else if (payload.event === 'error') handlers.onError?.(payload.data?.message || '流式请求失败', payload.data)
      else if (payload.event === 'done') handlers.onDone?.()
    }
  }
}

