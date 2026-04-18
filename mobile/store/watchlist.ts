/**
 * Zustand watchlist store — personal saved tickers.
 * Optimistic UI: updates state immediately, reverts on API error.
 */
import { create } from 'zustand';
import { Watchlist as WatchlistAPI, WatchlistItem } from '../lib/api';

interface WatchlistState {
  items:    WatchlistItem[];
  loading:  boolean;

  load:     () => Promise<void>;
  add:      (ticker: string, market: string, notes?: string) => Promise<void>;
  remove:   (ticker: string, market: string) => Promise<void>;
  isSaved:  (ticker: string, market: string) => boolean;
}

export const useWatchlistStore = create<WatchlistState>((set, get) => ({
  items:   [],
  loading: false,

  load: async () => {
    set({ loading: true });
    try {
      const items = await WatchlistAPI.list();
      set({ items });
    } catch {
      // silently fail — user might not be authenticated yet
    } finally {
      set({ loading: false });
    }
  },

  add: async (ticker, market, notes) => {
    // Optimistic add
    const optimistic: WatchlistItem = {
      id:       Date.now(),
      ticker:   ticker.toUpperCase(),
      market:   market.toUpperCase(),
      notes:    notes ?? null,
      added_at: new Date().toISOString(),
    };
    set(s => ({ items: [...s.items, optimistic] }));
    try {
      const saved = await WatchlistAPI.add(ticker, market, notes);
      // Replace optimistic entry with server-confirmed one
      set(s => ({
        items: s.items.map(i => (i.id === optimistic.id ? saved : i)),
      }));
    } catch (e) {
      // Revert on failure
      set(s => ({ items: s.items.filter(i => i.id !== optimistic.id) }));
      throw e;
    }
  },

  remove: async (ticker, market) => {
    const prev = get().items;
    // Optimistic remove
    set(s => ({
      items: s.items.filter(
        i => !(i.ticker === ticker.toUpperCase() && i.market === market.toUpperCase()),
      ),
    }));
    try {
      await WatchlistAPI.remove(ticker, market);
    } catch (e) {
      // Revert
      set({ items: prev });
      throw e;
    }
  },

  isSaved: (ticker, market) =>
    get().items.some(
      i => i.ticker === ticker.toUpperCase() && i.market === market.toUpperCase(),
    ),
}));
