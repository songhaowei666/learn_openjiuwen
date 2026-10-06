import {FormEvent, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
  A2uiSurface,
  basicCatalog,
  MarkdownContext,
  type ReactComponentImplementation,
} from '@a2ui/react/v0_9';
import {renderMarkdown} from '@a2ui/markdown-it';
import {
  MessageProcessor,
  type A2uiClientAction,
  type A2uiMessage,
  type SurfaceModel,
} from '@a2ui/web_core/v0_9';
import {sendChat} from './a2ui/client';
import {welcomeMessages} from './a2ui/welcome';
import './App.css';

type TimelineItem =
  | {kind: 'user'; id: string; text: string}
  | {kind: 'surface'; id: string};

function newConversationId(): string {
  return crypto.randomUUID().slice(0, 8);
}

function queryFromAction(action: A2uiClientAction): string {
  const context = action.context || {};
  if (action.name === 'submit_answer') {
    return String(context.answer ?? '').trim();
  }
  return String(context.query ?? '').trim();
}

export function App() {
  const sendRef = useRef<((text: string) => Promise<void>) | null>(null);
  const [conversationId, setConversationId] = useState(newConversationId);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const processor = useMemo(() => {
    const instance = new MessageProcessor<ReactComponentImplementation>(
      [basicCatalog],
      (action: A2uiClientAction) => {
      const query = queryFromAction(action);
      if (query && sendRef.current) {
        void sendRef.current(query);
      }
    });
    instance.processMessages(welcomeMessages);
    return instance;
  }, [conversationId]);

  const [surfaces, setSurfaces] = useState<
    SurfaceModel<ReactComponentImplementation>[]
  >(() => Array.from(processor.model.surfacesMap.values()));
  const [timeline, setTimeline] = useState<TimelineItem[]>(() =>
    Array.from(processor.model.surfacesMap.values()).map(surface => ({
      kind: 'surface' as const,
      id: surface.id,
    })),
  );

  useEffect(() => {
    setSurfaces(Array.from(processor.model.surfacesMap.values()));
    setTimeline(
      Array.from(processor.model.surfacesMap.values()).map(surface => ({
        kind: 'surface',
        id: surface.id,
      })),
    );
    const created = processor.onSurfaceCreated(surface => {
      setSurfaces(Array.from(processor.model.surfacesMap.values()));
      setTimeline(prev => [...prev, {kind: 'surface', id: surface.id}]);
    });
    const deleted = processor.onSurfaceDeleted(() => {
      setSurfaces(Array.from(processor.model.surfacesMap.values()));
    });
    return () => {
      created.unsubscribe();
      deleted.unsubscribe();
    };
  }, [processor]);

  const send = useCallback(
    async (text: string) => {
      const query = text.trim();
      if (!query || busy) {
        return;
      }
      setBusy(true);
      setError(null);
      setTimeline(prev => [...prev, {kind: 'user', id: `user-${Date.now()}`, text: query}]);
      setInput('');
      try {
        await sendChat(query, conversationId, (messages: A2uiMessage[]) => {
          processor.processMessages(messages);
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [busy, conversationId, processor],
  );

  useEffect(() => {
    sendRef.current = send;
  }, [send]);

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      void send(input);
    },
    [input, send],
  );

  const resetConversation = useCallback(() => {
    setConversationId(newConversationId());
    setError(null);
    setInput('');
  }, []);

  const surfaceById = useMemo(() => {
    const map = new Map<string, SurfaceModel<ReactComponentImplementation>>();
    for (const surface of surfaces) {
      map.set(surface.id, surface);
    }
    return map;
  }, [surfaces]);

  return (
    <MarkdownContext.Provider value={renderMarkdown}>
      <div className="app-shell">
        <header className="app-header">
          <div>
            <h1>金融智能体</h1>
            <p>会话 {conversationId}</p>
          </div>
          <button type="button" className="ghost-button" onClick={resetConversation}>
            新会话
          </button>
        </header>

        <main className="app-main">
          {timeline.map(item => {
            if (item.kind === 'user') {
              return (
                <article className="user-bubble" key={item.id}>
                  {item.text}
                </article>
              );
            }
            const surface = surfaceById.get(item.id);
            if (!surface) {
              return null;
            }
            return (
              <section className="surface-wrap" key={item.id}>
                <A2uiSurface surface={surface} />
              </section>
            );
          })}
          {busy && <p className="status-text">正在处理...</p>}
          {error && <p className="error-text">{error}</p>}
        </main>

        <form className="composer" onSubmit={handleSubmit}>
          <input
            name="body"
            value={input}
            onChange={event => setInput(event.target.value)}
            placeholder="输入转账、理财或余额查询需求"
            disabled={busy}
            autoComplete="off"
          />
          <button type="submit" disabled={busy || !input.trim()}>
            发送
          </button>
        </form>
      </div>
    </MarkdownContext.Provider>
  );
}
