import type {A2uiMessage} from '@a2ui/web_core/v0_9';

/** 进度树节点状态。 */
export type NodeStatus = 'running' | 'completed' | 'waiting_for_human' | 'failed';

/** SSE progress 事件。 */
export interface ProgressEvent {
  type: 'progress';
  nodeId: string;
  nodeType: string;
  label: string;
  status: NodeStatus;
  parentId: string | null;
  tokens: number | null;
  detail?: string;
}

/** SSE a2ui 事件。 */
export interface A2uiEvent {
  type: 'a2ui';
  surfaceId: string;
  nodeId?: string;
  messages: A2uiMessage[];
}

/** SSE done 事件。 */
export interface DoneEvent {
  ok: boolean;
  result?: unknown;
  error?: string;
}
