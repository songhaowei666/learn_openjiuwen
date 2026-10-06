import {FormEvent, useState} from 'react';
import {ask} from '../api/ask';
import {useA2uiStore} from '../stores/a2uiStore';
import {useProgressStore} from '../stores/progressStore';

/** 提问输入框。提交后重置进度树并启动一次运行。 */
export function AskInput() {
  const [question, setQuestion] = useState('帮我调研 openJiuwen SwarmFlow 的架构设计');
  const running = useProgressStore((state) => state.running);
  const setError = useProgressStore((state) => state.setError);
  const resetProgress = useProgressStore((state) => state.reset);
  const setRun = useProgressStore((state) => state.setRun);
  const resetA2ui = useA2uiStore((state) => state.reset);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || running) {
      return;
    }
    resetA2ui();
    resetProgress();
    setRun('pending');
    try {
      const runId = await ask(text);
      setRun(runId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      useProgressStore.setState({running: false, runId: null});
    }
  };

  return (
    <form className="ask-form" onSubmit={(event) => void onSubmit(event)}>
      <textarea
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        rows={3}
        disabled={running}
        placeholder="输入要调研的问题"
      />
      <button type="submit" disabled={running || !question.trim()}>
        {running ? '执行中' : '开始'}
      </button>
    </form>
  );
}
