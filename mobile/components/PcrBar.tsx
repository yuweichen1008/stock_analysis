import { StyleSheet, Text, View } from 'react-native';
import { Colors } from '../constants/colors';

interface Props {
  putVolume:  number | null;
  callVolume: number | null;
  pcr:        number | null;
}

function fmt(n: number | null): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export default function PcrBar({ putVolume, callVolume, pcr }: Props) {
  if (putVolume == null && callVolume == null) return null;

  const total   = (putVolume ?? 0) + (callVolume ?? 0);
  const putFrac = total > 0 ? (putVolume ?? 0) / total : 0.5;

  return (
    <View style={styles.container}>
      {/* Bar */}
      <View style={styles.track}>
        <View style={[styles.putFill,  { flex: putFrac }]} />
        <View style={[styles.callFill, { flex: 1 - putFrac }]} />
      </View>

      {/* Labels */}
      <View style={styles.labels}>
        <Text style={styles.putLabel}>Puts {fmt(putVolume)}</Text>
        {pcr != null && (
          <Text style={styles.pcrValue}>PCR {pcr.toFixed(2)}</Text>
        )}
        <Text style={styles.callLabel}>Calls {fmt(callVolume)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 4 },
  track: {
    flexDirection: 'row',
    height: 8,
    borderRadius: 4,
    overflow: 'hidden',
    backgroundColor: Colors.border,
  },
  putFill:  { backgroundColor: Colors.bear },
  callFill: { backgroundColor: Colors.bull },
  labels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  putLabel:  { fontSize: 11, color: Colors.bear },
  callLabel: { fontSize: 11, color: Colors.bull },
  pcrValue:  { fontSize: 11, fontWeight: '700', color: Colors.textPrimary },
});
