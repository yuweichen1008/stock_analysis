import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Colors } from '../constants/colors';
import type { PcrSnapshot } from '../lib/api';

const PCR_COLORS: Record<string, string> = {
  extreme_fear:  Colors.bear,
  fear:          '#f87171',
  neutral:       Colors.textSecondary,
  greed:         '#4ade80',
  extreme_greed: Colors.bull,
};

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

function trendArrow(first: number, last: number): string {
  if (last > first + 0.05) return '↑ Rising (more puts)';
  if (last < first - 0.05) return '↓ Falling (more calls)';
  return '→ Stable';
}

interface Props {
  ticker:    string | null;
  snapshots: PcrSnapshot[];
}

export default function PcrTimeline({ ticker, snapshots }: Props) {
  if (!snapshots.length) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyText}>
          No PCR history yet — check back after the next pipeline run (every 30 min during market hours).
        </Text>
      </View>
    );
  }

  const first = snapshots[0].pcr ?? 0;
  const last  = snapshots[snapshots.length - 1].pcr ?? 0;
  const trend = trendArrow(first, last);

  return (
    <View style={styles.container}>
      {/* Trend summary */}
      <View style={styles.trendRow}>
        <Text style={styles.trendLabel}>
          {ticker ? `${ticker} PCR Trend` : 'PCR Trend'}
        </Text>
        <Text style={styles.trendValue}>{trend}</Text>
      </View>

      {/* Horizontal scroll of snapshots */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.scroll}>
        <View style={styles.snapshotRow}>
          {snapshots.map((s, i) => {
            const color = PCR_COLORS[s.pcr_label ?? ''] ?? Colors.textSecondary;
            const isLast = i === snapshots.length - 1;
            return (
              <View key={i} style={styles.snapshotItem}>
                {/* Connector line */}
                {!isLast && <View style={[styles.connector, { backgroundColor: color }]} />}

                {/* Dot */}
                <View style={[styles.dot, { backgroundColor: color }]} />

                {/* Values */}
                <Text style={styles.snapTime}>{fmtTime(s.snapshot_at)}</Text>
                <Text style={[styles.snapPcr, { color }]}>
                  {s.pcr != null ? s.pcr.toFixed(2) : '—'}
                </Text>
                <Text style={[styles.snapLabel, { color }]}>
                  {(s.pcr_label ?? '').replace(/_/g, ' ')}
                </Text>
              </View>
            );
          })}
        </View>
      </ScrollView>

      {/* Latest volume */}
      {snapshots.length > 0 && (() => {
        const latest = snapshots[snapshots.length - 1];
        return (
          <View style={styles.volumeRow}>
            <Text style={[styles.volText, { color: Colors.bear }]}>
              Puts {latest.put_volume?.toLocaleString() ?? '—'}
            </Text>
            <Text style={[styles.volText, { color: Colors.bull }]}>
              Calls {latest.call_volume?.toLocaleString() ?? '—'}
            </Text>
          </View>
        );
      })()}
    </View>
  );
}

const styles = StyleSheet.create({
  container:  { gap: 12 },
  empty: {
    padding: 16,
    backgroundColor: Colors.elevated,
    borderRadius: 10,
  },
  emptyText: { fontSize: 13, color: Colors.textSecondary, textAlign: 'center' },
  trendRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  trendLabel: { fontSize: 13, fontWeight: '700', color: Colors.textPrimary },
  trendValue: { fontSize: 12, color: Colors.textSecondary },
  scroll:     { marginHorizontal: -4 },
  snapshotRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingHorizontal: 4,
    gap: 0,
  },
  snapshotItem: {
    alignItems: 'center',
    width: 72,
    paddingTop: 4,
    gap: 4,
  },
  connector: {
    position: 'absolute',
    top: 12,
    left: '50%',
    width: 72,
    height: 2,
  },
  dot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    zIndex: 1,
  },
  snapTime:  { fontSize: 10, color: Colors.textMuted },
  snapPcr:   { fontSize: 13, fontWeight: '800' },
  snapLabel: { fontSize: 9, textAlign: 'center' },
  volumeRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    backgroundColor: Colors.elevated,
    borderRadius: 10,
    paddingVertical: 8,
  },
  volText: { fontSize: 12, fontWeight: '600' },
});
