/**
 * Stock detail screen — accessed via router.push('/stock/AAPL?market=US')
 * Shows: header (price, bias, watchlist), technical metrics, RSI gauge,
 *        foreign flow (TW stocks), AI agent analysis, share button.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, Linking, ScrollView, StyleSheet,
  Text, TouchableOpacity, View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Colors } from '../../constants/colors';
import { Signals, SignalRow, API_BASE } from '../../lib/api';
import WatchlistButton from '../../components/WatchlistButton';
import AgentBadge from '../../components/AgentBadge';
import ErrorState from '../../components/ErrorState';

interface AgentResult {
  agent_name:   string;
  signal:       string;
  confidence:   number;
  reasoning:    string;
  data_quality: string;
}

interface AgentAnalysis {
  ticker:        string;
  market:        string;
  final_signal:  string;
  conviction:    number;
  thesis:        string;
  agent_results: AgentResult[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function rsiColor(rsi: number) {
  if (rsi < 30) return Colors.bull;
  if (rsi < 45) return '#ff8a65';
  if (rsi > 70) return Colors.bear;
  if (rsi > 60) return '#69f0ae';
  return Colors.textSecondary;
}

function flowLabel(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1e8) return `${(v / 1e8).toFixed(1)}億`;
  if (abs >= 1e4) return `${(v / 1e4).toFixed(0)}萬`;
  return String(Math.round(v));
}

// ── RSI gauge (pure View) ─────────────────────────────────────────────────────

function RsiGauge({ rsi }: { rsi: number }) {
  const color = rsiColor(rsi);
  const label = rsi < 30 ? '超賣' : rsi < 45 ? '偏低' : rsi > 70 ? '超買' : rsi > 60 ? '偏高' : '中性';
  const fillPct = Math.round(rsi);

  return (
    <View style={styles.gaugeWrap}>
      <View style={styles.gaugeTrack}>
        <View style={[styles.gaugeFill, { width: `${fillPct}%` as any, backgroundColor: color }]} />
        <View style={styles.gaugeZoneL} />
        <View style={styles.gaugeZoneR} />
      </View>
      <Text style={[styles.gaugeValue, { color }]}>{rsi.toFixed(1)}</Text>
      <Text style={[styles.gaugeLabel, { color }]}>{label}</Text>
    </View>
  );
}

// ── Foreign flow bar ──────────────────────────────────────────────────────────

function FlowBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = max > 0 ? Math.abs(value) / max : 0;
  const pos = value >= 0;
  const barWidth = pct * 120;

  return (
    <View style={styles.flowRow}>
      <Text style={styles.flowLabel}>{label}</Text>
      <View style={styles.flowTrack}>
        <View style={styles.flowCenter} />
        <View style={[
          styles.flowBar,
          {
            width: barWidth,
            backgroundColor: pos ? Colors.bear : Colors.bull,
            [pos ? 'left' : 'right']: '50%',
          },
        ]} />
      </View>
      <Text style={[styles.flowValue, { color: pos ? Colors.bear : Colors.bull }]}>
        {pos ? '+' : '-'}{flowLabel(value)}
      </Text>
    </View>
  );
}

// ── Metric row ────────────────────────────────────────────────────────────────

function MetricRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={styles.metricRow}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color }]}>{value}</Text>
    </View>
  );
}

// ── Main screen ───────────────────────────────────────────────────────────────

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
      if (sigRows.status === 'fulfilled' && sigRows.value.length > 0) setSignal(sigRows.value[0]);
      if (agentData.status === 'fulfilled' && agentData.value) setAnalysis(agentData.value);
    } catch (e: any) {
      setError(e?.message ?? '載入失敗');
    } finally {
      setLoading(false);
    }
  }, [ticker, market]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return <View style={[styles.container, styles.center]}><ActivityIndicator color={Colors.gold} size="large" /></View>;
  }
  if (error) return <ErrorState message={error} onRetry={load} />;

  const price = signal?.price as number | undefined;
  const bias  = signal?.bias  as number | undefined;
  const rsi   = signal?.RSI   as number | undefined;
  const score = signal?.score as number | undefined;
  const ma120 = signal?.MA120 as number | undefined;
  const volR  = signal?.vol_ratio as number | undefined;

  // Foreign flow (TW only)
  const f5  = signal?.f5  as number | undefined;
  const f20 = signal?.f20 as number | undefined;
  const f60 = signal?.f60 as number | undefined;
  const hasForeign = market === 'TW' && (f5 != null || f20 != null || f60 != null);
  const flowMax = Math.max(Math.abs(f5 ?? 0), Math.abs(f20 ?? 0), Math.abs(f60 ?? 0));

  const chartUrl = `https://lokistock.com/charts?ticker=${ticker}&market=${market}`;

  return (
    <View style={styles.container}>
      {/* Top bar */}
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
          <View style={{ flex: 1 }}>
            <Text style={styles.tickerText}>{ticker}</Text>
            {signal?.name ? <Text style={styles.nameText}>{String(signal.name)}</Text> : null}
          </View>
          <View style={styles.priceBlock}>
            {price != null && (
              <Text style={styles.price}>
                {market === 'TW' ? `NT$${price.toLocaleString('zh-TW')}` : `$${price.toFixed(2)}`}
              </Text>
            )}
            {bias != null && (
              <Text style={[styles.change, { color: bias >= 0 ? Colors.bear : Colors.bull }]}>
                {bias >= 0 ? '▲' : '▼'} {Math.abs(bias).toFixed(2)}%
              </Text>
            )}
          </View>
        </View>

        {/* Signal badge */}
        {signal?.is_signal && (
          <View style={[styles.signalBanner,
            { borderColor: signal.category === 'high_value_moat' ? Colors.gold : Colors.bear }]}>
            <Text style={[styles.signalBannerText,
              { color: signal.category === 'high_value_moat' ? Colors.gold : Colors.bear }]}>
              {signal.category === 'high_value_moat' ? '⭐ 高值護城河' : '📊 均值回歸訊號'}
            </Text>
          </View>
        )}

        {/* Technical metrics */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📊 技術指標</Text>
          <View style={styles.techRow}>
            <View style={{ flex: 1 }}>
              {rsi   != null && <MetricRow label="RSI(14)"  value={rsi.toFixed(1)}   color={rsiColor(rsi)} />}
              {score != null && <MetricRow label="信號分數" value={score.toFixed(1)} color={Colors.gold} />}
              {ma120 != null && <MetricRow label="MA120"    value={market === 'TW' ? `NT$${ma120.toLocaleString('zh-TW')}` : `$${ma120.toFixed(2)}`} color={Colors.textSecondary} />}
              {volR  != null && <MetricRow label="量比"     value={volR.toFixed(2)}  color={volR > 2 ? Colors.gold : Colors.textSecondary} />}
              {bias  != null && <MetricRow label="偏差(bias)" value={`${bias >= 0 ? '+' : ''}${bias.toFixed(2)}%`} color={bias >= 0 ? Colors.bear : Colors.bull} />}
            </View>
            {rsi != null && <RsiGauge rsi={rsi} />}
          </View>
        </View>

        {/* Foreign flow (TW only) */}
        {hasForeign && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>🏦 外資買賣超</Text>
            {f5  != null && <FlowBar label="5日"  value={f5}  max={flowMax} />}
            {f20 != null && <FlowBar label="20日" value={f20} max={flowMax} />}
            {f60 != null && <FlowBar label="60日" value={f60} max={flowMax} />}
            <Text style={styles.flowHint}>紅＝買超　綠＝賣超</Text>
          </View>
        )}

        {/* View chart button */}
        <TouchableOpacity
          style={styles.chartBtn}
          onPress={() => Linking.openURL(chartUrl)}
        >
          <Text style={styles.chartBtnText}>📈 查看完整圖表 (LokiStock)</Text>
        </TouchableOpacity>

        {/* AI agent analysis */}
        {analysis ? (
          <View style={styles.card}>
            <View style={styles.agentHeader}>
              <Text style={styles.cardTitle}>🤖 AI 代理分析</Text>
              <AgentBadge signal={analysis.final_signal} conviction={analysis.conviction} />
            </View>
            {analysis.thesis ? <Text style={styles.thesis}>{analysis.thesis}</Text> : null}
            <View style={styles.agentGrid}>
              {analysis.agent_results.map(a => (
                <View key={a.agent_name} style={styles.agentCell}>
                  <Text style={styles.agentName}>
                    {a.agent_name.replace('_agent', '').replace('_', ' ')}
                  </Text>
                  <AgentBadge signal={a.signal} conviction={a.confidence} compact />
                </View>
              ))}
            </View>
          </View>
        ) : (
          <View style={[styles.card, styles.center]}>
            <Text style={styles.dimText}>AI 分析尚未載入</Text>
          </View>
        )}

        {/* Share */}
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

const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: Colors.bg },
  center:          { justifyContent: 'center', alignItems: 'center' },
  topBar:          { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, paddingTop: 56, backgroundColor: Colors.surface, borderBottomWidth: 1, borderBottomColor: Colors.border },
  backBtn:         { padding: 4 },
  backText:        { fontSize: 16, color: Colors.gold, fontWeight: '600' },
  content:         { padding: 16, paddingBottom: 40 },
  tickerHeader:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12, marginTop: 8 },
  tickerText:      { fontSize: 30, fontWeight: '900', color: Colors.textPrimary },
  nameText:        { fontSize: 13, color: Colors.textSecondary, marginTop: 2 },
  priceBlock:      { alignItems: 'flex-end' },
  price:           { fontSize: 22, fontWeight: '800', color: Colors.textPrimary },
  change:          { fontSize: 14, fontWeight: '700', marginTop: 2 },
  signalBanner:    { borderWidth: 1, borderRadius: 10, paddingVertical: 8, paddingHorizontal: 14, marginBottom: 14, alignItems: 'center' },
  signalBannerText:{ fontSize: 13, fontWeight: '800' },
  card:            { backgroundColor: Colors.surface, borderRadius: 16, padding: 16, marginBottom: 14 },
  cardTitle:       { fontSize: 14, fontWeight: '700', color: Colors.textPrimary, marginBottom: 12 },
  techRow:         { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  // RSI gauge
  gaugeWrap:       { alignItems: 'center', paddingHorizontal: 4, minWidth: 72 },
  gaugeTrack:      { width: 72, height: 10, backgroundColor: Colors.elevated, borderRadius: 5, overflow: 'hidden', position: 'relative', marginBottom: 4 },
  gaugeFill:       { position: 'absolute', left: 0, top: 0, height: 10, borderRadius: 5, opacity: 0.85 },
  gaugeZoneL:      { position: 'absolute', left: 0, top: 0, width: '30%', height: 10, backgroundColor: Colors.bear, opacity: 0.15 },
  gaugeZoneR:      { position: 'absolute', right: 0, top: 0, width: '30%', height: 10, backgroundColor: Colors.bull, opacity: 0.15 },
  gaugeValue:      { fontSize: 18, fontWeight: '800', marginTop: 2 },
  gaugeLabel:      { fontSize: 10, fontWeight: '700', marginTop: 1 },
  // Metric rows
  metricRow:       { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: Colors.border },
  metricLabel:     { fontSize: 13, color: Colors.textSecondary },
  metricValue:     { fontSize: 13, fontWeight: '700' },
  // Foreign flow
  flowRow:         { flexDirection: 'row', alignItems: 'center', marginBottom: 8, gap: 8 },
  flowLabel:       { fontSize: 10, color: Colors.textMuted, width: 28 },
  flowTrack:       { flex: 1, height: 8, backgroundColor: Colors.elevated, borderRadius: 4, position: 'relative', overflow: 'hidden' },
  flowCenter:      { position: 'absolute', left: '50%', top: 0, width: 1, height: '100%', backgroundColor: Colors.border },
  flowBar:         { position: 'absolute', top: 1, height: 6, borderRadius: 3 },
  flowValue:       { fontSize: 10, fontWeight: '700', width: 56, textAlign: 'right' },
  flowHint:        { fontSize: 9, color: Colors.textMuted, marginTop: 4, textAlign: 'center' },
  // Chart button
  chartBtn:        { backgroundColor: Colors.elevated, borderWidth: 1, borderColor: Colors.tabActive, borderRadius: 12, padding: 14, alignItems: 'center', marginBottom: 14 },
  chartBtnText:    { fontSize: 14, fontWeight: '700', color: Colors.tabActive },
  // Agent
  agentHeader:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  thesis:          { fontSize: 13, color: Colors.textSecondary, lineHeight: 20, marginBottom: 14 },
  agentGrid:       { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  agentCell:       { backgroundColor: Colors.elevated, borderRadius: 10, padding: 10, minWidth: '45%', flex: 1 },
  agentName:       { fontSize: 11, color: Colors.textMuted, textTransform: 'capitalize', marginBottom: 4 },
  dimText:         { color: Colors.textMuted, fontSize: 13, textAlign: 'center' },
  shareBtn:        { backgroundColor: Colors.tabActive, borderRadius: 12, padding: 16, alignItems: 'center', marginTop: 4 },
  shareBtnText:    { fontSize: 15, fontWeight: '700', color: Colors.bg },
});
