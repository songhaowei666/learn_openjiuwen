import {useEffect, useState} from 'react';

type Member = {
  member_name: string;
  display_name: string;
};

type ChatMessage = {
  message_id: string;
  client_message_id: string;
  sender: string;
  sender_name: string;
  content: string;
  mentions: string[];
};

type ExcerptNote = {
  notified: string[];
  excerpts: Record<string, string>;
};

type PostResult = {
  ok: boolean;
  duplicate: boolean;
  notified_members: string[];
  context_path: string;
  message: ChatMessage;
  excerpts: Record<string, string>;
  replies: Record<string, unknown>;
  reason?: string;
};

const SCRIPT: Array<{client_message_id: string; body: string; mentions: string[]}> = [
  {client_message_id: 'script-1', body: '预算 10 万，两周上线。', mentions: []},
  {client_message_id: 'script-2', body: '请评估技术可行性', mentions: ['research']},
  {client_message_id: 'script-3', body: '请看法务风险', mentions: ['legal']},
  {client_message_id: 'script-4', body: '请不存在的人看一下', mentions: ['ghost']},
  {client_message_id: 'script-2', body: '请评估技术可行性', mentions: ['research']},
];

function displayName(message: ChatMessage): string {
  if (message.sender === 'user') {
    return '用户';
  }
  return message.sender_name;
}

async function readJson(response: Response): Promise<PostResult> {
  return response.json() as Promise<PostResult>;
}

export function App() {
  const [members, setMembers] = useState<Member[]>([]);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [contextPath, setContextPath] = useState('');
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState<Record<string, ExcerptNote>>({});
  const [duplicates, setDuplicates] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<string[]>([]);

  async function loadRoom() {
    const [rosterRes, historyRes] = await Promise.all([
      fetch('/api/roster'),
      fetch('/api/history'),
    ]);
    const roster = (await rosterRes.json()) as {members: Member[]};
    const history = (await historyRes.json()) as {context_path: string; messages: ChatMessage[]};
    setMembers(roster.members);
    setChecked((current) => {
      const next = {...current};
      for (const member of roster.members) {
        if (next[member.member_name] === undefined) {
          next[member.member_name] = false;
        }
      }
      return next;
    });
    setMessages(history.messages);
    setContextPath(history.context_path);
  }

  useEffect(() => {
    void loadRoom();
  }, []);

  function applyResult(data: PostResult) {
    if (data.context_path) {
      setContextPath(data.context_path);
    }
    if (data.duplicate) {
      const marked: Record<string, boolean> = {};
      for (const name of data.message.mentions) {
        marked[`reply-${data.message.client_message_id}-${name}`] = true;
      }
      setDuplicates((current) => ({...current, ...marked}));
      return;
    }
    if (Object.keys(data.excerpts).length > 0) {
      setNotes((current) => ({
        ...current,
        [data.message.message_id]: {
          notified: data.notified_members,
          excerpts: data.excerpts,
        },
      }));
    }
  }

  async function send(body: string, mentions: string[], clientMessageId: string) {
    const response = await fetch('/api/messages', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({body, mentions, client_message_id: clientMessageId}),
    });
    const data = await readJson(response);
    if (!response.ok) {
      if (response.status === 400 && data.reason === 'invalid_group_chat') {
        setErrors((current) => [...current, '未知成员']);
        return;
      }
      throw new Error(data.reason || '发送失败');
    }
    applyResult(data);
    const historyRes = await fetch('/api/history');
    const history = (await historyRes.json()) as {context_path: string; messages: ChatMessage[]};
    setMessages(history.messages);
    setContextPath(history.context_path);
  }

  async function onSend() {
    const body = draft.trim();
    if (!body || busy) {
      return;
    }
    const mentions = members.filter((member) => checked[member.member_name]).map((member) => member.member_name);
    setBusy(true);
    try {
      await send(body, mentions, `manual-${crypto.randomUUID()}`);
      setDraft('');
    } finally {
      setBusy(false);
    }
  }

  async function onPlay() {
    if (busy) {
      return;
    }
    setBusy(true);
    try {
      for (const step of SCRIPT) {
        await send(step.body, step.mentions, step.client_message_id);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>专家协作空间</h1>
        <p>公开聊天室。不勾选专家时只归档；勾选谁，谁根据群聊摘录用真实模型当众回复。</p>
      </header>

      <section className="transcript" aria-label="聊天记录">
        {messages.map((message) => {
          const note = notes[message.message_id];
          const duplicated = duplicates[message.client_message_id];
          return (
            <article className={note ? 'row' : 'row solo'} key={message.message_id}>
              <div className={message.sender === 'user' ? 'bubble user' : 'bubble expert'}>
                <div className="name">
                  <span>{displayName(message)}</span>
                  {duplicated ? <span className="tag">重复发送</span> : null}
                </div>
                <p>{message.content}</p>
              </div>
              {note ? (
                <aside className="excerpt">
                  <p className="who">点名 {note.notified.join('、')}</p>
                  {Object.entries(note.excerpts).map(([name, text]) => (
                    <pre key={name}>{text}</pre>
                  ))}
                </aside>
              ) : null}
            </article>
          );
        })}
        {errors.map((text, index) => (
          <div className="error-line" key={`${text}-${index}`}>{text}</div>
        ))}
      </section>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          void onSend();
        }}
      >
        <textarea
          value={draft}
          placeholder="输入要归档的话"
          onChange={(event) => setDraft(event.target.value)}
        />
        <div className="actions">
          <div className="checks">
            {members.map((member) => (
              <label key={member.member_name}>
                <input
                  type="checkbox"
                  checked={checked[member.member_name] ?? false}
                  onChange={(event) => {
                    setChecked((current) => ({...current, [member.member_name]: event.target.checked}));
                  }}
                />
                {member.display_name}
              </label>
            ))}
          </div>
          <button type="submit" disabled={busy || draft.trim() === ''}>发送</button>
          <button className="secondary" type="button" disabled={busy} onClick={() => void onPlay()}>
            播放脚本
          </button>
        </div>
      </form>

      <footer className="footer">
        历史文件 <code>{contextPath || '尚未生成'}</code>
      </footer>
    </div>
  );
}
