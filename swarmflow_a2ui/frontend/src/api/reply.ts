/** 把 A2UI 上的用户动作回传给正在等待的 human 节点。 */
export async function reply(
  runId: string,
  action: string,
  context: Record<string, unknown>,
): Promise<void> {
  const response = await fetch('/api/reply', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({run_id: runId, action, context}),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `回复失败：${response.status}`);
  }
}
