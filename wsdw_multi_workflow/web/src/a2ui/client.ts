import type {A2uiMessage} from '@a2ui/web_core/v0_9';

interface StreamPayload {
  kind: 'data' | 'done' | 'error';
  messages?: A2uiMessage[];
  text?: string;
  conversation_id?: string;
}

/** 调用后端 /api/chat，把 SSE 中的 A2UI 消息交给回调。 */
export async function sendChat(
  query: string,
  conversationId: string,
  onMessages: (messages: A2uiMessage[]) => void,
): Promise<void> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      query,
      conversation_id: conversationId,
    }),
  });

  if (!response.ok) {
    throw new Error(`服务异常: ${response.status} ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('浏览器不支持流式读取');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const {done, value} = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, {stream: true});
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || '';

    for (const block of blocks) {
      const line = block
        .split('\n')
        .find(item => item.startsWith('data: '));
      if (!line) {
        continue;
      }
      const payload = JSON.parse(line.slice(6)) as StreamPayload;
      if (payload.kind === 'error') {
        throw new Error(payload.text || '智能体处理失败');
      }
      if (payload.kind === 'data' && payload.messages?.length) {
        onMessages(payload.messages);
      }
    }
  }
}
