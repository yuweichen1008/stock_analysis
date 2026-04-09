import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, FlatList, RefreshControl,
  StyleSheet, Text, View,
} from 'react-native';
import { Colors } from '../../constants/colors';
import { Sandbox, BetRow, UserData } from '../../lib/api';
import { getOrCreateDeviceId } from '../../lib/device';

export default function HistoryScreen() {
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [bets, setBets]             = useState<BetRow[]>([]);
  const [me, setMe]                 = useState<UserData | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const deviceId = await getOrCreateDeviceId();
      const [history, user] = await Promise.all([
        Sandbox.history(deviceId),
        Sandbox.me(deviceId),
      ]);
      setBets(history);
      setMe(user);
    } catch (e) {
      console.warn('[History] Fetch error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={Colors.gold} size="large" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Coins header */}
      {me && (
        <View style={styles.coinsHeader}>
          <View>
            <Text style={styles.coinsLabel}>虛擬幣餘額</Text>
            <Text style={styles.coinsValue}>{me.coins.toLocaleString()} coins</Text>
          </View>
          <View style={styles.statsGroup}>
            <StatItem label="勝" value={String(me.wins)} color={Colors.bull} />
            <StatItem label="敗" value={String(me.losses)} color={Colors.bear} />
            <StatItem label="勝率" value={`${me.win_rate_pct.toFixed(0)}%`} color={Colors.gold} />
          </View>
        </View>
      )}

      {bets.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.empty}>尚無下注紀錄</Text>
        </View>
      ) : (
        <FlatList
          data={bets}
          keyExtractor={(_, i) => String(i)}
          renderItem={({ item }) => <BetItem bet={item} />}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={Colors.gold} />
          }
          contentContainerStyle={styles.list}
        />
      )}
    </View>
  );
}

function BetItem({ bet }: { bet: BetRow }) {
  const isBull    = bet.direction === 'Bull';
  const settled   = bet.status === 'settled';
  const won       = settled && bet.is_correct;
  const payout    = bet.payout;

  return (
    <View style={styles.betRow}>
      <View style={styles.betLeft}>
        <Text style={styles.betDate}>{bet.date}</Text>
        <View style={[styles.dirPill, isBull ? styles.bullPill : styles.bearPill]}>
          <Text style={styles.dirText}>{isBull ? '🟢 多方' : '🔴 空方'}</Text>
        </View>
      </View>
      <View style={styles.betMid}>
        <Text style={styles.betAmount}>{bet.amount.toLocaleString()}</Text>
        <Text style={styles.betAmountLabel}>coins</Text>
      </View>
      <View style={styles.betRight}>
        {settled ? (
          <>
            <Text style={[styles.betPayout, { color: (payout ?? 0) >= 0 ? Colors.bull : Colors.bear }]}>
              {payout != null ? `${payout >= 0 ? '+' : ''}${payout.toLocaleString()}` : '—'}
            </Text>
            <Text style={[styles.betResult, { color: won ? Colors.bull : Colors.bear }]}>
              {won ? '✅ 命中' : '❌ 失準'}
            </Text>
          </>
        ) : (
          <Text style={styles.pending}>待結算</Text>
        )}
      </View>
    </View>
  );
}

function StatItem({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={{ alignItems: 'center', marginLeft: 14 }}>
      <Text style={{ fontSize: 17, fontWeight: '700', color }}>{value}</Text>
      <Text style={{ fontSize: 10, color: Colors.textMuted }}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: Colors.bg },
  center:       { flex: 1, justifyContent: 'center', alignItems: 'center' },
  coinsHeader:  {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    backgroundColor: Colors.surface, padding: 18, marginBottom: 2,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  coinsLabel:   { fontSize: 11, color: Colors.textMuted },
  coinsValue:   { fontSize: 22, fontWeight: '800', color: Colors.gold, marginTop: 2 },
  statsGroup:   { flexDirection: 'row' },
  list:         { padding: 12, paddingBottom: 32 },
  empty:        { color: Colors.textMuted, fontSize: 15 },
  betRow:       {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.surface, borderRadius: 12, padding: 14,
    marginBottom: 8,
  },
  betLeft:      { flex: 2 },
  betDate:      { fontSize: 12, color: Colors.textMuted, marginBottom: 4 },
  dirPill:      { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, alignSelf: 'flex-start' },
  bullPill:     { backgroundColor: Colors.bullDim },
  bearPill:     { backgroundColor: Colors.bearDim },
  dirText:      { fontSize: 12, fontWeight: '600', color: Colors.textPrimary },
  betMid:       { flex: 1, alignItems: 'center' },
  betAmount:    { fontSize: 16, fontWeight: '700', color: Colors.textPrimary },
  betAmountLabel: { fontSize: 10, color: Colors.textMuted },
  betRight:     { flex: 1, alignItems: 'flex-end' },
  betPayout:    { fontSize: 16, fontWeight: '700' },
  betResult:    { fontSize: 11, marginTop: 2, fontWeight: '600' },
  pending:      { fontSize: 12, color: Colors.textMuted },
});
