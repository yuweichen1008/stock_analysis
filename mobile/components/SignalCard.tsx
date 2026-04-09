import { StyleSheet, Text, View } from 'react-native';
import { Colors } from '../constants/colors';
import { SignalRow } from '../lib/api';

interface Props {
  item:    SignalRow;
  variant: 'signal' | 'watchlist';
}

export default function SignalCard({ item, variant }: Props) {
  const rsi     = item.RSI != null ? Number(item.RSI) : null;
  const score   = item.score != null ? Number(item.score) : null;
  const price   = item.price != null ? Number(item.price) : null;
  const bias    = item.bias != null ? Number(item.bias) : null;
  const isSignal = variant === 'signal';

  return (
    <View style={[styles.card, isSignal ? styles.signalCard : styles.watchCard]}>
      <View style={styles.header}>
        <View style={styles.tickerRow}>
          <Text style={styles.ticker}>{item.ticker}</Text>
          {item.name ? <Text style={styles.name}>{String(item.name)}</Text> : null}
        </View>
        {score != null && (
          <View style={[styles.scoreBadge, score >= 70 ? styles.scoreBull : styles.scoreMid]}>
            <Text style={styles.scoreText}>{score.toFixed(0)}</Text>
          </View>
        )}
      </View>

      <View style={styles.metrics}>
        {price != null && <Metric label="Price" value={price.toFixed(2)} />}
        {rsi != null && (
          <Metric
            label="RSI"
            value={rsi.toFixed(1)}
            color={rsi < 30 ? Colors.bull : rsi > 70 ? Colors.bear : Colors.textSecondary}
          />
        )}
        {bias != null && (
          <Metric
            label="Bias"
            value={`${bias >= 0 ? '+' : ''}${bias.toFixed(1)}%`}
            color={bias >= 0 ? Colors.bull : Colors.bear}
          />
        )}
        {item.vol_ratio != null && (
          <Metric label="VolR" value={Number(item.vol_ratio).toFixed(1)} />
        )}
      </View>
    </View>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, color ? { color } : {}]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card:        {
    backgroundColor: Colors.surface, borderRadius: 14,
    padding: 14, marginBottom: 10,
    borderLeftWidth: 3,
  },
  signalCard:  { borderLeftColor: Colors.bull },
  watchCard:   { borderLeftColor: Colors.gold },
  header:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  tickerRow:   { flexDirection: 'row', alignItems: 'center', gap: 8 },
  ticker:      { fontSize: 16, fontWeight: '800', color: Colors.textPrimary },
  name:        { fontSize: 12, color: Colors.textSecondary, maxWidth: 140 },
  scoreBadge:  { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 20 },
  scoreBull:   { backgroundColor: Colors.bullDim, borderWidth: 1, borderColor: Colors.bull },
  scoreMid:    { backgroundColor: Colors.elevated, borderWidth: 1, borderColor: Colors.border },
  scoreText:   { fontSize: 12, fontWeight: '700', color: Colors.textPrimary },
  metrics:     { flexDirection: 'row', gap: 16 },
  metric:      {},
  metricLabel: { fontSize: 10, color: Colors.textMuted },
  metricValue: { fontSize: 13, fontWeight: '600', color: Colors.textPrimary, marginTop: 1 },
});
