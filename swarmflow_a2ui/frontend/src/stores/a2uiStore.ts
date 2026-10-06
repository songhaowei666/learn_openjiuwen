import {create} from 'zustand';
import type {A2uiMessage} from '@a2ui/web_core/v0_9';

interface A2uiState {
  messages: A2uiMessage[];
  seen: Record<string, true>;
  reset: () => void;
  append: (messages: A2uiMessage[], eventId: string) => void;
}

/** A2UI 消息按到达顺序累积，同一事件 id 只处理一次。 */
export const useA2uiStore = create<A2uiState>((set) => ({
  messages: [],
  seen: {},
  reset: () => set({messages: [], seen: {}}),
  append: (messages, eventId) =>
    set((state) => {
      if (state.seen[eventId]) {
        return state;
      }
      return {
        seen: {...state.seen, [eventId]: true},
        messages: [...state.messages, ...messages],
      };
    }),
}));
