import type {A2uiEvent, DoneEvent, ProgressEvent} from '../types/events';

export interface EventHandlers {
  onProgress: (event: ProgressEvent, eventId: string) => void;
  onA2ui: (event: A2uiEvent, eventId: string) => void;
  onDone: (event: DoneEvent, eventId: string) => void;
}

/** 建立 SSE。浏览器断线后会带上 Last-Event-ID 自动重连。 */
export function connectEvents(runId: string, handlers: EventHandlers): EventSource {
  const source = new EventSource(`/api/events/${runId}`);
  const seen = new Set<string>();

  const take = (event: MessageEvent): boolean => {
    if (!event.lastEventId || seen.has(event.lastEventId)) {
      return false;
    }
    seen.add(event.lastEventId);
    return true;
  };

  source.addEventListener('progress', (event) => {
    const message = event as MessageEvent;
    if (!take(message)) {
      return;
    }
    handlers.onProgress(JSON.parse(message.data) as ProgressEvent, message.lastEventId);
  });

  source.addEventListener('a2ui', (event) => {
    const message = event as MessageEvent;
    if (!take(message)) {
      return;
    }
    handlers.onA2ui(JSON.parse(message.data) as A2uiEvent, message.lastEventId);
  });

  source.addEventListener('done', (event) => {
    const message = event as MessageEvent;
    if (!take(message)) {
      return;
    }
    handlers.onDone(JSON.parse(message.data) as DoneEvent, message.lastEventId);
    source.close();
  });

  return source;
}
