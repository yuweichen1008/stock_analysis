import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Colors } from '../constants/colors';
import type { NewsItem } from '../lib/api';
import PcrBar from './PcrBar';

const PCR_LABEL_CONFIG: Record<string, { text: string; color: string; emoji: string }> = {
  extreme_fear:  { text: 'Extreme Fear',  color: Colors.bear, emoji: '😱' },
  fear:          { text: 'Fear',          color: '#f87171',   emoji: '😨' },
  neutral:       { text: 'Neutral',       color: Colors.textSecondary, emoji: '😐' },
  greed:         { text: 'Greed',         color: '#4ade80',   emoji: '😀' },
  extreme_greed: { text: 'Extreme Greed', color: Colors.bull, emoji: '🤑' },
};

const SENTIMENT_COLORS = {
  positive: Colors.bull,
  neutral:  Colors.textSecondary,
  negative: Colors.bear,
};

const MARKET_COLORS: Record<string, string> = {
  US:     Colors.blue,
  TW:     Colors.bear,
  MARKET: Colors.textMuted,
};

function timeAgo(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch {
    return '';
  }
}

interface Props {
  item:    NewsItem;
  onPress: () => void;
}

export default function NewsCard({ item, onPress }: Props) {
  const hasRealPcr = item.market === 'US' && item.pcr != null;
  const pcrCfg     = PCR_LABEL_CONFIG[item.pcr_label ?? ''] ?? null;
  const mktColor   = MARKET_COLORS[item.market] ?? Colors.textMuted;
  const sentColor  = SENTIMENT_COLORS[item.sentiment_label] ?? Colors.textSecondary;

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.75}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={[styles.marketBadge, { borderColor: mktColor }]}>
            <Text style={[styles.marketText, { color: mktColor }]}>{item.market}</Text>
          </View>
          {item.ticker && (
            <Text style={styles.ticker}>{item.ticker}</Text>
          )}
          {item.source && (
            <Text style={styles.source}>· {item.source}</Text>
          )}
        </View>
        <Text style={styles.time}>{timeAgo(item.published_at)}</Text>
      </View>

      {/* Headline */}
      <Text style={styles.headline} numberOfLines={2}>{item.headline}</Text>

      {/* PCR or sentiment */}
      {hasRealPcr ? (
        <View style={styles.pcrSection}>
          {pcrCfg && (
            <View style={styles.pcrLabelRow}>
              <Text style={[styles.pcrLabelText, { color: pcrCfg.color }]}>
                {pcrCfg.emoji} {pcrCfg.text}
              </Text>
            </View>
          )}
          <PcrBar
            putVolume={item.put_volume}
            callVolume={item.call_volume}
            pcr={item.pcr}
          />
        </View>
      ) : (
        <View style={styles.sentimentRow}>
          <Text style={styles.sentimentLabel}>Sentiment: </Text>
          <Text style={[styles.sentimentValue, { color: sentColor }]}>
            {item.sentiment_label}
            {item.sentiment_score != null
              ? ` (${item.sentiment_score > 0 ? '+' : ''}${item.sentiment_score.toFixed(2)})`
              : ''}
          </Text>
        </View>
      )}

      {/* Related */}
      {item.related_count > 0 && (
        <Text style={styles.relatedText}>🔗 {item.related_count} related news</Text>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.surface,
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: Colors.border,
    gap: 10,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flexShrink: 1,
  },
  marketBadge: {
    borderWidth: 1,
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  marketText: { fontSize: 10, fontWeight: '700' },
  ticker:     { fontSize: 13, fontWeight: '800', color: Colors.textPrimary },
  source:     { fontSize: 11, color: Colors.textSecondary, flexShrink: 1 },
  time:       { fontSize: 11, color: Colors.textMuted, marginLeft: 8 },
  headline: {
    fontSize: 13,
    fontWeight: '600',
    color: Colors.textPrimary,
    lineHeight: 18,
  },
  pcrSection:    { gap: 6 },
  pcrLabelRow:   { flexDirection: 'row' },
  pcrLabelText:  { fontSize: 12, fontWeight: '700' },
  sentimentRow:  { flexDirection: 'row', alignItems: 'center' },
  sentimentLabel:{ fontSize: 11, color: Colors.textMuted },
  sentimentValue:{ fontSize: 11, fontWeight: '600' },
  relatedText:   { fontSize: 11, color: Colors.textSecondary },
});
