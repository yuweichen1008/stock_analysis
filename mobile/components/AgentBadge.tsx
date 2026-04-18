/**
 * AgentBadge — BUY / HOLD / SELL pill with color and conviction %.
 */
import { StyleSheet, Text, View } from 'react-native';
import { Colors } from '../constants/colors';

interface Props {
  signal:     'BUY' | 'HOLD' | 'SELL' | string;
  conviction?: number;   // 0-100
  compact?:   boolean;
}

const SIGNAL_COLORS: Record<string, { bg: string; text: string }> = {
  BUY:  { bg: Colors.bullDim, text: Colors.bull },
  SELL: { bg: Colors.bearDim, text: Colors.bear },
  HOLD: { bg: '#1e2330',      text: Colors.textSecondary },
};

export default function AgentBadge({ signal, conviction, compact }: Props) {
  const s = signal.toUpperCase();
  const colors = SIGNAL_COLORS[s] ?? SIGNAL_COLORS.HOLD;
  return (
    <View style={[styles.pill, { backgroundColor: colors.bg }, compact && styles.compact]}>
      <Text style={[styles.label, { color: colors.text }]}>
        {s}{conviction != null ? ` ${conviction}%` : ''}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill:    { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, alignSelf: 'flex-start' },
  compact: { paddingHorizontal: 6, paddingVertical: 2 },
  label:   { fontSize: 12, fontWeight: '700' },
});
