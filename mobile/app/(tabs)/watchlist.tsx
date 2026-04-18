/**
 * Watchlist tab — saved tickers, today's alerts, and search to add.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, FlatList, RefreshControl, StyleSheet,
  Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Colors } from '../../constants/colors';
import { Watchlist as WatchlistAPI, SignalRow } from '../../lib/api';
import { useWatchlistStore } from '../../store/watchlist';
import SignalRowComponent from '../../components/SignalRow';
import ErrorState from '../../components/ErrorState';

export default function WatchlistScreen() {
  const router = useRouter();
  const { items, loading: storeLoading, load, remove } = useWatchlistStore();
  const [alerts,        setAlerts]     = useState<SignalRow[]>([]);
  const [refreshing,    setRefreshing] = useState(false);
  const [query,         setQuery]      = useState('');
  const [searchResults, setResults]    = useState<SignalRow[]>([]);
  const [searching,     setSearching]  = useState(false);
  const [error,         setError]      = useState<string | null>(null);

  const refresh = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      await load();
      const a = await WatchlistAPI.alerts().catch(() => []);
      setAlerts(a);
    } catch (e: any) {
      setError(e?.message ?? '載入失敗');
    } finally {
      setRefreshing(false);
    }
  }, [load]);

  useEffect(() => { refresh(); }, []);

  // Debounced search
  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    const id = setTimeout(async () => {
      setSearching(true);
      try {
        const { Signals } = await import('../../lib/api');
        const res = await Signals.search(query.trim(), 'all', 10);
        setResults(res);
      } catch { setResults([]); }
      finally { setSearching(false); }
    }, 300);
    return () => clearTimeout(id);
  }, [query]);

  if (error) return <ErrorState message={error} onRetry={() => refresh()} />;

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>⭐ 自選股</Text>
      </View>

      {/* Search bar */}
      <View style={styles.searchBar}>
        <TextInput
          style={styles.searchInput}
          placeholder="搜尋股票代號或名稱…"
          placeholderTextColor={Colors.textMuted}
          value={query}
          onChangeText={setQuery}
          autoCapitalize="characters"
          returnKeyType="search"
        />
        {searching && <ActivityIndicator color={Colors.gold} size="small" style={{ marginRight: 10 }} />}
      </View>

      {/* Search results dropdown */}
      {query.trim() !== '' && searchResults.length > 0 && (
        <View style={styles.dropdown}>
          {searchResults.slice(0, 6).map(r => (
            <TouchableOpacity
              key={`${r.ticker}-${r.market}`}
              style={styles.dropdownRow}
              onPress={async () => {
                const { useWatchlistStore: wl } = await import('../../store/watchlist');
                await wl.getState().add(r.ticker!, r.market ?? 'US').catch(() => {});
                setQuery('');
              }}
            >
              <Text style={styles.dropTicker}>{r.ticker}</Text>
              <Text style={styles.dropName}>{r.name}</Text>
              <Text style={styles.dropMarket}>{r.market}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      <FlatList
        data={[]}   // spacer
        keyExtractor={() => 'spacer'}
        renderItem={() => null}
        ListHeaderComponent={() => (
          <>
            {/* Alerts section */}
            {alerts.length > 0 && (
              <View style={styles.section}>
                <View style={styles.sectionHeader}>
                  <Text style={styles.sectionTitle}>🔔 今日訊號提醒</Text>
                  <View style={styles.alertDot} />
                </View>
                {alerts.map(a => (
                  <SignalRowComponent
                    key={`${a.ticker}-${a.market}`}
                    item={a}
                    onPress={() => router.push(`/stock/${a.ticker}?market=${a.market ?? 'US'}`)}
                  />
                ))}
              </View>
            )}

            {/* Watchlist */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>📋 我的自選股 ({items.length})</Text>
              {storeLoading && <ActivityIndicator color={Colors.gold} style={{ marginVertical: 20 }} />}
              {!storeLoading && items.length === 0 && (
                <Text style={styles.empty}>尚無自選股 — 使用上方搜尋列新增</Text>
              )}
              {items.map(item => (
                <TouchableOpacity
                  key={item.id}
                  style={styles.watchlistRow}
                  onPress={() => router.push(`/stock/${item.ticker}?market=${item.market}`)}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.watchTicker}>{item.ticker}</Text>
                    <Text style={styles.watchMeta}>{item.market} · {item.added_at?.slice(0, 10) ?? ''}</Text>
                  </View>
                  <TouchableOpacity onPress={() => remove(item.ticker, item.market)} style={styles.removeBtn}>
                    <Text style={styles.removeTxt}>✕</Text>
                  </TouchableOpacity>
                </TouchableOpacity>
              ))}
            </View>
          </>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => refresh(true)} tintColor={Colors.gold} />}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: Colors.bg },
  header:       { padding: 16, paddingTop: 56, backgroundColor: Colors.surface, borderBottomWidth: 1, borderBottomColor: Colors.border },
  title:        { fontSize: 22, fontWeight: '800', color: Colors.textPrimary },
  searchBar:    { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, margin: 12, borderRadius: 12, borderWidth: 1, borderColor: Colors.border },
  searchInput:  { flex: 1, padding: 12, fontSize: 14, color: Colors.textPrimary },
  dropdown:     { backgroundColor: Colors.surface, marginHorizontal: 12, borderRadius: 12, borderWidth: 1, borderColor: Colors.border, overflow: 'hidden', marginTop: -4, zIndex: 10 },
  dropdownRow:  { flexDirection: 'row', alignItems: 'center', padding: 12, borderBottomWidth: 1, borderBottomColor: Colors.border },
  dropTicker:   { fontSize: 14, fontWeight: '800', color: Colors.textPrimary, width: 60 },
  dropName:     { flex: 1, fontSize: 12, color: Colors.textSecondary },
  dropMarket:   { fontSize: 11, color: Colors.textMuted, backgroundColor: Colors.elevated, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  section:      { paddingHorizontal: 12, marginTop: 6 },
  sectionHeader:{ flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: Colors.textSecondary, marginBottom: 10 },
  alertDot:     { width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.bull, marginLeft: 8, marginBottom: 8 },
  watchlistRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: 12, padding: 14, marginBottom: 8 },
  watchTicker:  { fontSize: 16, fontWeight: '800', color: Colors.textPrimary },
  watchMeta:    { fontSize: 11, color: Colors.textMuted, marginTop: 2 },
  removeBtn:    { padding: 8 },
  removeTxt:    { fontSize: 16, color: Colors.bear },
  empty:        { color: Colors.textMuted, fontSize: 14, textAlign: 'center', paddingVertical: 24 },
});
