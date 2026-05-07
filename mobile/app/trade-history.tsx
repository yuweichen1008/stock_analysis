/**
 * Trade history screen — full CTBC trade journal.
 * Pushed from Profile → "交易紀錄 →"
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, FlatList, RefreshControl,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { Stack } from 'expo-router';
import { Colors } from '../constants/colors';
import { Broker, TradeRow } from '../lib/api';

type FilterSide = 'all' | 'buy' | 'sell';
type FilterStatus = 'all' | 'pending' | 'filled' | 'cancelled' | 'rejected';

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function StatusBadge({ status }: { status: TradeRow['status'] }) {
  const colorMap: Record<string, string> = {
    pending:   Colors.gold,
    filled:    Colors.bull,
    cancelled: Colors.textMuted,
    rejected:  Colors.bear,
  };
  const color = colorMap[status] ?? Colors.textMuted;
  return (
    <View style={[styles.badge, { borderColor: color }]}>
      <Text style={[styles.badgeText, { color }]}>{status}</Text>
    </View>
  );
}

function TradeCard({ item }: { item: TradeRow }) {
  const isBuy = item.side === 'buy';
  const price = item.filled_price ?? item.limit_price;
  const hasPnl = item.realized_pnl != null;
  return (
    <View style={styles.card}>
      <View style={styles.cardRow}>
        <View style={[styles.sideTag, { backgroundColor: isBuy ? Colors.bullDim : Colors.bearDim }]}>
          <Text style={[styles.sideText, { color: isBuy ? Colors.bull : Colors.bear }]}>
            {isBuy ? '買' : '賣'}
          </Text>
        </View>
        <View style={{ flex: 1, marginLeft: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Text style={styles.ticker}>{item.ticker}</Text>
            <StatusBadge status={item.status} />
          </View>
          <Text style={styles.meta}>
            {item.qty.toLocaleString()}股 × NT${price?.toLocaleString('zh-TW', { minimumFractionDigits: 2 }) ?? '—'}
          </Text>
          <Text style={styles.date}>{fmtDate(item.executed_at ?? item.created_at)}</Text>
        </View>
        {hasPnl && (
          <Text style={[styles.pnl, { color: (item.realized_pnl ?? 0) >= 0 ? Colors.bull : Colors.bear }]}>
            {(item.realized_pnl ?? 0) >= 0 ? '+' : ''}
            {Math.round(item.realized_pnl ?? 0).toLocaleString()}
          </Text>
        )}
      </View>
      {item.signal_source && item.signal_source !== 'manual' && (
        <Text style={styles.source}>訊號來源: {item.signal_source}</Text>
      )}
    </View>
  );
}

export default function TradeHistoryScreen() {
  const [trades,     setTrades]     = useState<TradeRow[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filterSide, setFilterSide] = useState<FilterSide>('all');
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const data = await Broker.trades(200, 180);
      setTrades(data);
    } catch {
      // Silently fail — CTBC may not be configured
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = trades.filter(t => {
    if (filterSide !== 'all' && t.side !== filterSide) return false;
    if (filterStatus !== 'all' && t.status !== filterStatus) return false;
    return true;
  });

  // Summary stats
  const totalPnl = trades
    .filter(t => t.realized_pnl != null)
    .reduce((sum, t) => sum + (t.realized_pnl ?? 0), 0);
  const filledCount = trades.filter(t => t.status === 'filled').length;

  return (
    <>
      <Stack.Screen options={{ title: '交易紀錄', headerStyle: { backgroundColor: Colors.bg }, headerTintColor: Colors.textPrimary }} />
      <View style={styles.container}>
        {/* Summary bar */}
        <View style={styles.summaryBar}>
          <View style={styles.summaryItem}>
            <Text style={styles.summaryValue}>{trades.length}</Text>
            <Text style={styles.summaryLabel}>總委託</Text>
          </View>
          <View style={styles.summaryItem}>
            <Text style={styles.summaryValue}>{filledCount}</Text>
            <Text style={styles.summaryLabel}>成交</Text>
          </View>
          <View style={styles.summaryItem}>
            <Text style={[styles.summaryValue, { color: totalPnl >= 0 ? Colors.bull : Colors.bear }]}>
              {totalPnl >= 0 ? '+' : ''}{Math.round(totalPnl).toLocaleString()}
            </Text>
            <Text style={styles.summaryLabel}>已實現損益</Text>
          </View>
        </View>

        {/* Side filter */}
        <View style={styles.filterRow}>
          {(['all', 'buy', 'sell'] as FilterSide[]).map(f => (
            <TouchableOpacity
              key={f}
              style={[styles.filterPill, filterSide === f && styles.filterPillActive]}
              onPress={() => setFilterSide(f)}
            >
              <Text style={[styles.filterText, filterSide === f && styles.filterTextActive]}>
                {f === 'all' ? '全部' : f === 'buy' ? '買進' : '賣出'}
              </Text>
            </TouchableOpacity>
          ))}
          <View style={{ width: 1, backgroundColor: Colors.border, marginHorizontal: 6 }} />
          {(['pending', 'filled'] as FilterStatus[]).map(f => (
            <TouchableOpacity
              key={f}
              style={[styles.filterPill, filterStatus === f && styles.filterPillActive]}
              onPress={() => setFilterStatus(prev => prev === f ? 'all' : f)}
            >
              <Text style={[styles.filterText, filterStatus === f && styles.filterTextActive]}>
                {f === 'pending' ? '待成交' : '已成交'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {loading ? (
          <View style={styles.center}>
            <ActivityIndicator color={Colors.gold} />
          </View>
        ) : filtered.length === 0 ? (
          <View style={styles.center}>
            <Text style={{ fontSize: 32, marginBottom: 8 }}>📋</Text>
            <Text style={{ color: Colors.textMuted, fontSize: 14 }}>尚無交易紀錄</Text>
          </View>
        ) : (
          <FlatList
            data={filtered}
            keyExtractor={t => String(t.id)}
            renderItem={({ item }) => <TradeCard item={item} />}
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={Colors.gold} />
            }
            contentContainerStyle={{ paddingBottom: 32 }}
          />
        )}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  container:        { flex: 1, backgroundColor: Colors.bg },
  center:           { flex: 1, justifyContent: 'center', alignItems: 'center' },
  summaryBar:       { flexDirection: 'row', backgroundColor: Colors.surface, paddingVertical: 14, paddingHorizontal: 20, borderBottomWidth: 1, borderBottomColor: Colors.border },
  summaryItem:      { flex: 1, alignItems: 'center' },
  summaryValue:     { fontSize: 18, fontWeight: '800', color: Colors.textPrimary },
  summaryLabel:     { fontSize: 10, color: Colors.textMuted, marginTop: 2 },
  filterRow:        { flexDirection: 'row', paddingHorizontal: 12, paddingVertical: 8, gap: 6, borderBottomWidth: 1, borderBottomColor: Colors.border, flexWrap: 'wrap' },
  filterPill:       { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20, borderWidth: 1, borderColor: Colors.border },
  filterPillActive: { borderColor: Colors.tabActive, backgroundColor: Colors.elevated },
  filterText:       { fontSize: 12, color: Colors.textMuted },
  filterTextActive: { color: Colors.textPrimary, fontWeight: '700' },
  card:             { marginHorizontal: 12, marginTop: 10, backgroundColor: Colors.surface, borderRadius: 12, padding: 14 },
  cardRow:          { flexDirection: 'row', alignItems: 'flex-start' },
  sideTag:          { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  sideText:         { fontSize: 15, fontWeight: '800' },
  ticker:           { fontSize: 16, fontWeight: '800', color: Colors.textPrimary },
  meta:             { fontSize: 12, color: Colors.textSecondary, marginTop: 2 },
  date:             { fontSize: 11, color: Colors.textMuted, marginTop: 2 },
  pnl:              { fontSize: 16, fontWeight: '800', textAlign: 'right' },
  source:           { marginTop: 6, fontSize: 10, color: Colors.textMuted },
  badge:            { borderWidth: 1, borderRadius: 6, paddingHorizontal: 5, paddingVertical: 1 },
  badgeText:        { fontSize: 9, fontWeight: '700' },
});
