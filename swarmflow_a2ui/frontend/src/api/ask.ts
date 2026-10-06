/** 向后端提交一个问题，返回本次运行 id。 */
export async function ask(question: string): Promise<string> {
  const response = await fetch('/api/ask', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question}),
  });
  if (!response.ok) {
    throw new Error(`提问失败：${response.status}`);
  }
  const payload = (await response.json()) as {run_id: string};
  return payload.run_id;
}
