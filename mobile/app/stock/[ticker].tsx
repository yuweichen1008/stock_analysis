/**
 * Stock detail screen — accessed via router.push('/stock/AAPL?market=US')
 * Shows: header (price, change, watchlist star), agent analysis, technicals, share button.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Colors } from '../../constants/colors';
import { Signals, SignalRow } from '../../lib/api';
import WatchlistButton from '../../components/WatchlistButton';
import AgentBadge from '../../components/AgentBadge';
import ErrorState from '../../components/ErrorState';
import { API_BASE } from '../../lib/api';

interface AgentResult {
  agent_name:   string;
  signal:       string;
  confidence:   number;
  reasoning:    string;
  data_quality: string;
}

interface AgentAnalysis {
  ticker:       string;
  market:       string;
  final_signal: string;
  conviction:   number;
  thesis:       string;
  agent_results: AgentResult[];
}

export default function StockDetailScreen() {
  const { ticker, market = 'US' } = useLocalSearchParams<{ ticker: string; market?: string }>();
  const router = useRouter();

  const [signal,   setSignal]   = useState<SignalRow | null>(null);
  const [analysis, setAnalysis] = useState<AgentAnalysis | null>(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [sigRows, agentData] = await Promise.allSettled([
        Signals.search(ticker as string, market as string, 1),
        fetch(`${API_BASE}/api/agents/analyze?ticker=${ticker}&market=${market}`)
          .then(r => r.ok ? r.json() : null),
      ]);
      if (sigRows.status === 'fulfilled' && sigRows.value.length > 0) {
        setSignal(sigRows.value[0]);
      }
      if (agentData.status === 'fulfilled' && agentData.value) {
        setAnalysis(agentData.value);
      }
    } catch (e: any) {
      setError(e?.message ?? '載入失敗');
    } finally {
      setLoading(false);
    }
  }, [ticker, market]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={Colors.gold} size="large" />
      </View>
    );
  }

  if (error) return <ErrorState message={error} onRetry={load} />;

  const price    = signal?.price;
  const bias     = signal?.bias;
  const rsi      = signal?.RSI;

  return (
    <View style={styles.container}>
      {/* Header bar */}
      <View style={styles.topBar}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>‹ 返回</Text>
        </TouchableOpacity>
        {ticker && market && (
          <WatchlistButton ticker={ticker as string} market={market as string} />
        )}
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Ticker header */}
        <View style={styles.tickerHeader}>
          <View>
            <Text style={styles.tickerText}>{ticker}</Text>
            <Text style={styles.nameText}>{signal?.name ?? ''}</Text>
          </View>
          <View style={styles.priceBlock}>
            {price != null && <Text style={styles.price}>${price.toFixed(2)}</Text>}
            {bias != null && (
              <Text style={[styles.change, { color: bias >= 0 ? Colors.bull : Colors.bear }]}>
                {bias >= 0 ? '+' : ''}{bias.toFixed(2)}%
              </Text>
            )}
          </View>
        </View>

        {/* Technical metrics */}
        {(rsi != null || signal?.score != null) && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>📊 技術指標</Text>
            {rsi != null && (
              <MetricRow label="RSI" value={rsi.toFixed(1)}
                color={rsi < 30 ? Colors.bull : rsi > 70 ? Colors.bear : Colors.textPrimary} />
            )}
            {signal?.score != null && (
              <MetricRow label="Score" value={(signal.score as number).toFixed(1)} color={Colors.gold} />
            )}
            {signal?.MA120 != null && (
              <MetricRow label="MA120" value={(signal.MA120 as number).toFixed(2)} color={Colors.textSecondary} />
            )}
            {signal?.vol_ratio != null && (
              <MetricRow label="Vol Ratio" value={(signal.vol_ratio as number).toFixed(2)} color={Colors.textSecondary} />
            )}
          </View>
        )}

        {/* Agent Analysis */}
        {analysis ? (
          <View style={styles.card}>
            <View style={styles.agentHeader}>
              <Text style={styles.cardTitle}>🤖 AI 代理分析</Text>
              <AgentBadge signal={analysis.final_signal} conviction={analysis.conviction} />
            </View>
            {analysis.thesis ? (
              <Text style={styles.thesis}>{analysis.thesis}</Text>
            ) : null}
            <View style={styles.agentGrid}>
              {analysis.agent_results.map(a => (
                <View key={a.agent_name} style={styles.agentCell}>
                  <Text style={styles.agentName}>{a.agent_name.replace('_agent', '').replace('_', ' ')}</Text>
                  <AgentBadge signal={a.signal} conviction={a.confidence} compact />
                </View>
              ))}
            </View>
          </View>
        ) : (
          <View style={[styles.card, styles.center]}>
            <Text style={styles.dimText}>AI 分析尚未載入 — 點此觸發分析</Text>
          </View>
        )}

        {/* Share to Community */}
        <TouchableOpacity
          style={styles.shareBtn}
          onPress={() => router.push(`/create-post?ticker=${ticker}&market=${market}`)}
        >
          <Text style={styles.shareBtnText}>💬 分享至社群</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

function MetricRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={styles.metricRow}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container:   { flex: 1, backgroundColor: Colors.bg },
  center:      { justifyContent: 'center', alignItems: 'center' },
  topBar:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, paddingTop: 56, backgroundColor: Colors.surface, borderBottomWidth: 1, borderBottomColor: Colors.border },
  backBtn:     { padding: 4 },
  backText:    { fontSize: 16, color: Colors.gold, fontWeight: '600' },
  content:     { padding: 16, paddingBottom: 40 },
  tickerHeader:{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16, marginTop: 8 },
  tickerText:  { fontSize: 30, fontWeight: '900', color: Colors.textPrimary },
  nameText:    { fontSize: 13, color: Colors.textSecondary, marginTop: 2 },
  priceBlock:  { alignItems: 'flex-end' },
  price:       { fontSize: 22, fontWeight: '800', color: Colors.textPrimary },
  change:      { fontSize: 14, fontWeight: '700', marginTop: 2 },
  card:        { backgroundColor: Colors.surface, borderRadius: 16, padding: 16, marginBottom: 14 },
  cardTitle:   { fontSize: 14, fontWeight: '700', color: Colors.textPrimary, marginBottom: 12 },
  agentHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  thesis:      { fontSize: 13, color: Colors.textSecondary, lineHeight: 20, marginBottom: 14 },
  agentGrid:   { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  agentCell:   { backgroundColor: Colors.elevated, borderRadius: 10, padding: 10, minWidth: '45%', flex: 1 },
  agentName:   { fontSize: 11, color: Colors.textMuted, textTransform: 'capitalize', marginBottom: 4 },
  metricRow:   { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: Colors.border },
  metricLabel: { fontSize: 13, color: Colors.textSecondary },
  metricValue: { fontSize: 13, fontWeight: '700' },
  dimText:     { color: Colors.textMuted, fontSize: 13, textAlign: 'center' },
  shareBtn:    { backgroundColor: Colors.tabActive, borderRadius: 12, padding: 16, alignItems: 'center', marginTop: 4 },
  shareBtnText:{ fontSize: 15, fontWeight: '700', color: Colors.bg },
});
