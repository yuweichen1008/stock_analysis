import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Colors } from '../../constants/colors';
import { Oracle, OracleRow, OracleStats, LiveData } from '../../lib/api';
import OracleCard from '../../components/OracleCard';

export default function TodayScreen() {
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [oracle, setOracle]       = useState<OracleRow | null>(null);
  const [stats, setStats]         = useState<OracleStats | null>(null);
  const [live, setLive]           = useState<LiveData | null>(null);
  const liveTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const [o, s, l] = await Promise.all([
        Oracle.today(),
        Oracle.stats(),
        Oracle.live(),
      ]);
      setOracle(o);
      setStats(s);
      setLive(l);
    } catch (e) {
      console.warn('[Today] Fetch error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    // Poll live data every 5 min
    liveTimer.current = setInterval(() => {
      Oracle.live().then(setLive).catch(() => {});
    }, 5 * 60 * 1000);
    return () => { if (liveTimer.current) clearInterval(liveTimer.current); };
  }, [load]);

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={Colors.gold} size="large" />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => load(true)}
          tintColor={Colors.gold}
        />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>🔮 Oracle</Text>
        <Text style={styles.headerSub}>TAIEX 大盤多空預測</Text>
      </View>

      {/* Oracle Hero Card */}
      <OracleCard oracle={oracle} live={live} />

      {/* Stats ribbon */}
      {stats && stats.resolved > 0 && (
        <View style={styles.statsRow}>
          <StatPill label="勝率" value={`${stats.win_rate_pct.toFixed(0)}%`} color={Colors.gold} />
          <StatPill label="連勝" value={`${stats.streak}`} color={stats.streak >= 2 ? Colors.bull : Colors.textSecondary} />
          <StatPill label="積分" value={`${stats.cumulative_score > 0 ? '+' : ''}${stats.cumulative_score}`} color={Colors.blue} />
          <StatPill label="戰績" value={`${stats.wins}/${stats.resolved}`} color={Colors.textSecondary} />
        </View>
      )}

      {/* Factor breakdown */}
      {oracle && oracle.factors && Object.keys(oracle.factors).length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📐 因子分析</Text>
          {Object.entries(oracle.factors).map(([key, val]) => (
            <FactorRow key={key} name={key} value={val as number} />
          ))}
        </View>
      )}

      {/* Live data footer */}
      {live?.last_updated && (
        <Text style={styles.liveNote}>
          台指 {live.current_level?.toLocaleString() ?? '—'}  ·  更新 {live.last_updated}
        </Text>
      )}
    </ScrollView>
  );
}

function StatPill({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={styles.pill}>
      <Text style={[styles.pillValue, { color }]}>{value}</Text>
      <Text style={styles.pillLabel}>{label}</Text>
    </View>
  );
}

function FactorRow({ name, value }: { name: string; value: number }) {
  const positive = value > 0;
  return (
    <View style={styles.factorRow}>
      <Text style={styles.factorName}>{name.replace(/_/g, ' ')}</Text>
      <Text style={[styles.factorVal, { color: positive ? Colors.bull : Colors.bear }]}>
        {positive ? '▲' : '▼'} {Math.abs(value).toFixed(2)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container:   { flex: 1, backgroundColor: Colors.bg },
  center:      { justifyContent: 'center', alignItems: 'center' },
  content:     { padding: 16, paddingBottom: 32 },
  header:      { marginBottom: 20, marginTop: 12 },
  headerTitle: { fontSize: 28, fontWeight: '800', color: Colors.textPrimary },
  headerSub:   { fontSize: 13, color: Colors.textSecondary, marginTop: 2 },
  statsRow:    { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 },
  pill:        {
    flex: 1, backgroundColor: Colors.surface, borderRadius: 12,
    alignItems: 'center', paddingVertical: 10, marginHorizontal: 3,
  },
  pillValue:   { fontSize: 16, fontWeight: '700' },
  pillLabel:   { fontSize: 10, color: Colors.textMuted, marginTop: 2 },
  card:        { backgroundColor: Colors.surface, borderRadius: 16, padding: 16, marginBottom: 16 },
  cardTitle:   { fontSize: 14, fontWeight: '700', color: Colors.textPrimary, marginBottom: 10 },
  factorRow:   { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5 },
  factorName:  { fontSize: 13, color: Colors.textSecondary, textTransform: 'capitalize' },
  factorVal:   { fontSize: 13, fontWeight: '600' },
  liveNote:    { textAlign: 'center', fontSize: 11, color: Colors.textMuted, marginTop: 8 },
});
