import { StyleSheet, Text, View } from 'react-native';
import { Colors } from '../constants/colors';
import { OracleRow, LiveData } from '../lib/api';

interface Props {
  oracle: OracleRow | null;
  live:   LiveData | null;
}

export default function OracleCard({ oracle, live }: Props) {
  if (!oracle || oracle.status === 'no_prediction') {
    return (
      <View style={[styles.card, styles.pending]}>
        <Text style={styles.pendingEmoji}>🌙</Text>
        <Text style={styles.pendingTitle}>今日預測尚未生成</Text>
        <Text style={styles.pendingHint}>每個交易日 08:00 TST 更新</Text>
      </View>
    );
  }

  const isBull   = oracle.direction === 'Bull';
  const conf     = oracle.confidence_pct ?? 0;
  const resolved = oracle.status === 'resolved';

  return (
    <View style={[styles.card, isBull ? styles.bull : styles.bear]}>
      {/* Direction + confidence */}
      <View style={styles.row}>
        <Text style={styles.dirEmoji}>{isBull ? '🟢' : '🔴'}</Text>
        <View style={styles.dirText}>
          <Text style={[styles.dirLabel, { color: isBull ? Colors.bull : Colors.bear }]}>
            {isBull ? '多方 BULL' : '空方 BEAR'}
          </Text>
          <Text style={styles.confidence}>信心 {conf.toFixed(0)}%</Text>
        </View>
        {resolved && (
          <View style={[styles.badge, oracle.is_correct ? styles.badgeWin : styles.badgeLoss]}>
            <Text style={styles.badgeText}>{oracle.is_correct ? '✅ 命中' : '❌ 失準'}</Text>
          </View>
        )}
      </View>

      {/* Confidence bar */}
      <View style={styles.barBg}>
        <View style={[
          styles.barFill,
          { width: `${conf}%`, backgroundColor: isBull ? Colors.bull : Colors.bear },
        ]} />
      </View>

      {/* Live data row */}
      {live?.current_level != null && (
        <View style={styles.liveRow}>
          <Text style={styles.liveLevel}>
            台指 {live.current_level.toLocaleString()}
          </Text>
          {live.change_pts != null && (
            <Text style={[
              styles.liveChange,
              { color: live.change_pts >= 0 ? Colors.bull : Colors.bear },
            ]}>
              {live.change_pts >= 0 ? '+' : ''}{live.change_pts.toFixed(0)} pts
              ({live.change_pct != null ? `${live.change_pct >= 0 ? '+' : ''}${live.change_pct.toFixed(2)}%` : ''})
            </Text>
          )}
        </View>
      )}

      {/* Resolved result */}
      {resolved && oracle.taiex_change_pts != null && (
        <View style={styles.resultRow}>
          <Text style={styles.resultText}>
            大盤 {oracle.taiex_change_pts >= 0 ? '+' : ''}{oracle.taiex_change_pts.toFixed(0)}pts
          </Text>
          {oracle.score_pts != null && (
            <Text style={[
              styles.resultScore,
              { color: oracle.score_pts >= 0 ? Colors.bull : Colors.bear },
            ]}>
              Oracle {oracle.score_pts >= 0 ? '+' : ''}{oracle.score_pts.toFixed(0)}分
            </Text>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card:         { borderRadius: 20, padding: 20, marginBottom: 16 },
  pending:      { backgroundColor: Colors.surface, alignItems: 'center', paddingVertical: 40 },
  bull:         {
    backgroundColor: Colors.bullDim,
    borderWidth: 1.5, borderColor: Colors.bull,
  },
  bear:         {
    backgroundColor: Colors.bearDim,
    borderWidth: 1.5, borderColor: Colors.bear,
  },
  pendingEmoji: { fontSize: 40, marginBottom: 12 },
  pendingTitle: { fontSize: 16, fontWeight: '700', color: Colors.textSecondary },
  pendingHint:  { fontSize: 12, color: Colors.textMuted, marginTop: 4 },
  row:          { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  dirEmoji:     { fontSize: 32, marginRight: 12 },
  dirText:      { flex: 1 },
  dirLabel:     { fontSize: 22, fontWeight: '800' },
  confidence:   { fontSize: 13, color: Colors.textSecondary, marginTop: 2 },
  badge:        { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20 },
  badgeWin:     { backgroundColor: Colors.bullDim, borderWidth: 1, borderColor: Colors.bull },
  badgeLoss:    { backgroundColor: Colors.bearDim, borderWidth: 1, borderColor: Colors.bear },
  badgeText:    { fontSize: 12, fontWeight: '700', color: Colors.textPrimary },
  barBg:        { height: 5, backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: 3, marginBottom: 14 },
  barFill:      { height: 5, borderRadius: 3 },
  liveRow:      { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  liveLevel:    { fontSize: 14, fontWeight: '600', color: Colors.textPrimary },
  liveChange:   { fontSize: 14, fontWeight: '700' },
  resultRow:    {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingTop: 10, borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.1)',
  },
  resultText:   { fontSize: 13, color: Colors.textSecondary },
  resultScore:  { fontSize: 13, fontWeight: '700' },
});
