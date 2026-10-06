import {useEffect, useMemo, useRef, useState} from 'react';
import {basicCatalog, type ReactComponentImplementation} from '@a2ui/react/v0_9';
import {
  MessageProcessor,
  type A2uiClientAction,
  type SurfaceModel,
} from '@a2ui/web_core/v0_9';
import {connectEvents} from './api/events';
import {reply} from './api/reply';
import {AskInput} from './components/AskInput';
import {ProgressTree} from './components/ProgressTree';
import {useA2uiStore} from './stores/a2uiStore';
import {useProgressStore} from './stores/progressStore';
import './App.css';

/** 一次运行的事件订阅和 A2UI 渲染器。 */
function RunSession({runId}: {runId: string}) {
  const applyProgress = useProgressStore((state) => state.applyProgress);
  const attachSurface = useProgressStore((state) => state.attachSurface);
  const clearSurface = useProgressStore((state) => state.clearSurface);
  const finish = useProgressStore((state) => state.finish);
  const setError = useProgressStore((state) => state.setError);
  const messages = useA2uiStore((state) => state.messages);
  const append = useA2uiStore((state) => state.append);
  const actionRef = useRef<(action: A2uiClientAction) => void>(() => undefined);

  actionRef.current = (action) => {
    const context = (action.context ?? {}) as Record<string, unknown>;
    void reply(runId, action.name, context).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  };

  const processor = useMemo(
    () =>
      new MessageProcessor<ReactComponentImplementation>([basicCatalog], (action) => {
        actionRef.current(action);
      }),
    [],
  );

  const [surfaces, setSurfaces] = useState<SurfaceModel<ReactComponentImplementation>[]>(
    [],
  );
  const cursor = useRef(0);

  useEffect(() => {
    const fresh = messages.slice(cursor.current);
    if (fresh.length === 0) {
      return;
    }
    processor.processMessages(fresh);
    cursor.current = messages.length;
    setSurfaces(Array.from(processor.model.surfacesMap.values()));
  }, [messages, processor]);

  useEffect(() => {
    const source = connectEvents(runId, {
      onProgress: (event, eventId) => applyProgress(event, eventId),
      onA2ui: (event, eventId) => {
        const deleted = event.messages.some(
          (message) => 'deleteSurface' in message && message.deleteSurface,
        );
        append(event.messages, eventId);
        if (!event.nodeId) {
          return;
        }
        if (deleted) {
          clearSurface(event.nodeId);
        } else {
          attachSurface(event.nodeId, event.surfaceId);
        }
      },
      onDone: (event) => {
        const text =
          event.result === undefined ? null : JSON.stringify(event.result, null, 2);
        finish(text, event.ok ? null : event.error ?? '运行失败');
      },
    });
    return () => source.close();
  }, [append, applyProgress, attachSurface, clearSurface, finish, runId]);

  return <ProgressTree surfaces={new Map(surfaces.map((surface) => [surface.id, surface]))} />;
}

export function App() {
  const runId = useProgressStore((state) => state.runId);
  const running = useProgressStore((state) => state.running);
  const resultText = useProgressStore((state) => state.resultText);
  const error = useProgressStore((state) => state.error);
  const activeRunId = runId && runId !== 'pending' ? runId : null;

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>SwarmFlow 交互 Demo</h1>
        <p>提问后查看阶段进度。流程停在人工节点时，直接在该节点下完成表单。</p>
      </header>
      <AskInput />
      {error && <p className="error-text">{error}</p>}
      {activeRunId ? <RunSession key={activeRunId} runId={activeRunId} /> : <ProgressTree surfaces={new Map()} />}
      {!running && resultText && (
        <section className="result-panel">
          <h2>运行结果</h2>
          <pre>{resultText}</pre>
        </section>
      )}
    </div>
  );
}
