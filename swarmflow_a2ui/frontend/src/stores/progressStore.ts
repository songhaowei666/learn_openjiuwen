import {create} from 'zustand';
import type {NodeStatus, ProgressEvent} from '../types/events';

export interface ProgressNode {
  nodeId: string;
  nodeType: string;
  label: string;
  status: NodeStatus;
  parentId: string | null;
  tokens: number | null;
  detail?: string;
  surfaceId?: string;
}

interface ProgressState {
  nodes: Record<string, ProgressNode>;
  seen: Record<string, true>;
  runId: string | null;
  running: boolean;
  resultText: string | null;
  error: string | null;
  reset: () => void;
  setRun: (runId: string) => void;
  applyProgress: (event: ProgressEvent, eventId: string) => void;
  attachSurface: (nodeId: string, surfaceId: string) => void;
  clearSurface: (nodeId: string) => void;
  finish: (resultText: string | null, error: string | null) => void;
  setError: (error: string | null) => void;
}

/** 扁平 nodeId 映射。树形结构由组件按 parentId 派生。 */
export const useProgressStore = create<ProgressState>((set) => ({
  nodes: {},
  seen: {},
  runId: null,
  running: false,
  resultText: null,
  error: null,
  reset: () =>
    set({
      nodes: {},
      seen: {},
      runId: null,
      running: false,
      resultText: null,
      error: null,
    }),
  setRun: (runId) => set({runId, running: true, error: null, resultText: null}),
  applyProgress: (event, eventId) =>
    set((state) => {
      if (state.seen[eventId]) {
        return state;
      }
      const previous = state.nodes[event.nodeId];
      return {
        seen: {...state.seen, [eventId]: true},
        nodes: {
          ...state.nodes,
          [event.nodeId]: {
            nodeId: event.nodeId,
            nodeType: event.nodeType,
            label: event.label,
            status: event.status,
            parentId: event.parentId,
            tokens: event.tokens ?? previous?.tokens ?? null,
            detail: event.detail ?? previous?.detail,
            surfaceId: previous?.surfaceId,
          },
        },
      };
    }),
  attachSurface: (nodeId, surfaceId) =>
    set((state) => {
      const node = state.nodes[nodeId];
      if (!node) {
        return state;
      }
      return {nodes: {...state.nodes, [nodeId]: {...node, surfaceId}}};
    }),
  clearSurface: (nodeId) =>
    set((state) => {
      const node = state.nodes[nodeId];
      if (!node) {
        return state;
      }
      return {nodes: {...state.nodes, [nodeId]: {...node, surfaceId: undefined}}};
    }),
  finish: (resultText, error) => set({running: false, resultText, error}),
  setError: (error) => set({error}),
}));
