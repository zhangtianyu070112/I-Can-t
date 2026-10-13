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

function fallbackRequestId() {
  return `client-${Date.now().toString(36)}`
}

async function readApiResponse<T>(resp: Response): Promise<ApiResponse<T>> {
  const raw = await resp.text()
  let payload: Partial<ApiResponse<T>> | null = null
  if (raw.trim()) {
    try {
      payload = JSON.parse(raw) as Partial<ApiResponse<T>>
    } catch {
      payload = null
    }
  }

  if (payload && typeof payload === 'object' && typeof payload.success === 'boolean') {
    return {
      request_id: String(payload.request_id || resp.headers.get('x-request-id') || fallbackRequestId()),
      success: payload.success,
      data: payload.data as T,
      error: payload.error || null,
    }
  }

  const statusMessage = resp.ok
    ? '服务器返回了无法识别的响应，请重试。'
    : `请求失败（HTTP ${resp.status}），请稍后重试。`
  return {
    request_id: resp.headers.get('x-request-id') || fallbackRequestId(),
    success: false,
    data: null as T,
    error: {
      code: resp.ok ? 'INVALID_API_RESPONSE' : `HTTP_${resp.status}`,
      message: statusMessage,
    },
  }
}

export async function apiPost<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  try {
    const resp = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return await readApiResponse<T>(resp)
  } catch (reason: any) {
    return {
      request_id: fallbackRequestId(),
      success: false,
      data: null as T,
      error: { code: 'NETWORK_ERROR', message: reason?.message || '网络连接失败，请检查服务后重试。' },
    }
  }
}

export async function apiGet<T>(path: string): Promise<ApiResponse<T>> {
  try {
    const resp = await fetch(path)
    return await readApiResponse<T>(resp)
  } catch (reason: any) {
    return {
      request_id: fallbackRequestId(),
      success: false,
      data: null as T,
      error: { code: 'NETWORK_ERROR', message: reason?.message || '网络连接失败，请检查服务后重试。' },
    }
  }
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
      let payload: StreamEvent
      try {
        payload = JSON.parse(line.slice(6)) as StreamEvent
      } catch {
        throw new Error('流式响应格式错误，请重试。')
      }
      if (payload.event === 'start') handlers.onStart?.(payload.data)
      else if (payload.event === 'status') handlers.onStatus?.(payload.data)
      else if (payload.event === 'chunk') handlers.onChunk?.(payload.data)
      else if (payload.event === 'final') handlers.onFinal?.(payload.data as T)
      else if (payload.event === 'error') handlers.onError?.(payload.data?.message || '流式请求失败', payload.data)
      else if (payload.event === 'done') handlers.onDone?.()
    }
  }
}

