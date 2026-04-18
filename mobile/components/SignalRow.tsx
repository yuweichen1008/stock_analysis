/**
 * SignalRow — compact FlatList row for signal lists.
 * Shows ticker, name, RSI badge, bias badge, score bar.
 */
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Colors } from '../constants/colors';
import { SignalRow as SignalRowType } from '../lib/api';

interface Props {
  item:    SignalRowType;
  onPress?: () => void;
}

export default function SignalRow({ item, onPress }: Props) {
  const rsi    = typeof item.RSI === 'number' ? item.RSI : null;
  const bias   = typeof item.bias === 'number' ? item.bias : null;
  const score  = typeof item.score === 'number' ? item.score : null;
  const market = item.market ?? '';

  const rsiColor = rsi != null
    ? rsi < 30 ? Colors.bull : rsi > 70 ? Colors.bear : Colors.textSecondary
    : Colors.textMuted;

  const biasColor = bias != null
    ? bias > 0 ? Colors.bull : bias < 0 ? Colors.bear : Colors.textSecondary
    : Colors.textMuted;

  // Score bar: 0–100 scale
  const barWidth = score != null ? Math.min(100, Math.max(0, score)) : 0;

  return (
    <TouchableOpacity style={styles.row} onPress={onPress} activeOpacity={0.75}>
      {/* Left: ticker + name */}
      <View style={styles.left}>
        <View style={styles.tickerRow}>
          <Text style={styles.ticker}>{item.ticker}</Text>
          {market ? <Text style={styles.marketBadge}>{market}</Text> : null}
        </View>
        <Text style={styles.name} numberOfLines={1}>{item.name ?? ''}</Text>
      </View>

      {/* Middle: RSI + bias */}
      <View style={styles.mid}>
        {rsi != null && (
          <View style={[styles.badge, { backgroundColor: rsiColor + '22' }]}>
            <Text style={[styles.badgeText, { color: rsiColor }]}>RSI {rsi.toFixed(0)}</Text>
          </View>
        )}
        {bias != null && (
          <View style={[styles.badge, { backgroundColor: biasColor + '22', marginTop: 4 }]}>
            <Text style={[styles.badgeText, { color: biasColor }]}>
              {bias > 0 ? '+' : ''}{bias.toFixed(1)}%
            </Text>
          </View>
        )}
      </View>

      {/* Right: score bar */}
      {score != null && (
        <View style={styles.right}>
          <Text style={styles.scoreLabel}>{score.toFixed(0)}</Text>
          <View style={styles.barBg}>
            <View style={[styles.barFill, { width: `${barWidth}%` }]} />
          </View>
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  row:         { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, marginBottom: 6 },
  left:        { flex: 3 },
  tickerRow:   { flexDirection: 'row', alignItems: 'center', gap: 6 },
  ticker:      { fontSize: 15, fontWeight: '800', color: Colors.textPrimary },
  marketBadge: { fontSize: 10, color: Colors.textMuted, backgroundColor: Colors.elevated, paddingHorizontal: 5, paddingVertical: 1, borderRadius: 5 },
  name:        { fontSize: 11, color: Colors.textMuted, marginTop: 2 },
  mid:         { flex: 2, alignItems: 'flex-end', paddingHorizontal: 8 },
  badge:       { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 6 },
  badgeText:   { fontSize: 11, fontWeight: '700' },
  right:       { flex: 2, alignItems: 'flex-end' },
  scoreLabel:  { fontSize: 12, fontWeight: '700', color: Colors.textPrimary, marginBottom: 3 },
  barBg:       { width: 60, height: 4, backgroundColor: Colors.border, borderRadius: 2 },
  barFill:     { height: 4, backgroundColor: Colors.gold, borderRadius: 2 },
});
