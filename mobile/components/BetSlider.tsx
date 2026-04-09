import { StyleSheet, Text, View, TouchableOpacity } from 'react-native';
import { Colors } from '../constants/colors';

interface Props {
  value:    number;
  min:      number;
  max:      number;
  onChange: (v: number) => void;
}

const PRESETS = [100, 500, 1000, 2000];
const STEP    = 100;

export default function BetSlider({ value, min, max, onChange }: Props) {
  const dec = () => onChange(Math.max(min, value - STEP));
  const inc = () => onChange(Math.min(max, value + STEP));

  return (
    <View>
      {/* Amount stepper */}
      <View style={styles.stepperRow}>
        <TouchableOpacity style={styles.stepBtn} onPress={dec} disabled={value <= min}>
          <Text style={[styles.stepBtnText, value <= min && styles.disabled]}>－</Text>
        </TouchableOpacity>

        <View style={styles.amountBox}>
          <Text style={styles.amountValue}>{value.toLocaleString()}</Text>
          <Text style={styles.amountUnit}>coins</Text>
        </View>

        <TouchableOpacity style={styles.stepBtn} onPress={inc} disabled={value >= max}>
          <Text style={[styles.stepBtnText, value >= max && styles.disabled]}>＋</Text>
        </TouchableOpacity>
      </View>

      {/* Preset buttons */}
      <View style={styles.presets}>
        {PRESETS.filter(p => p >= min && p <= max).map(p => (
          <TouchableOpacity
            key={p}
            style={[styles.preset, value === p && styles.presetActive]}
            onPress={() => onChange(p)}
          >
            <Text style={[styles.presetText, value === p && styles.presetTextActive]}>
              {p >= 1000 ? `${p / 1000}K` : p}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Win/loss preview */}
      <View style={styles.oddsRow}>
        <View style={styles.oddsItem}>
          <Text style={styles.oddsLabel}>獲勝 +coins</Text>
          <Text style={[styles.oddsValue, { color: Colors.bull }]}>+{value.toLocaleString()}</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.oddsItem}>
          <Text style={styles.oddsLabel}>落敗 -coins</Text>
          <Text style={[styles.oddsValue, { color: Colors.bear }]}>
            -{Math.floor(value / 2).toLocaleString()}
          </Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  stepperRow:       { flexDirection: 'row', alignItems: 'center', marginBottom: 14 },
  stepBtn:          {
    width: 48, height: 48, borderRadius: 12,
    backgroundColor: Colors.elevated, borderWidth: 1, borderColor: Colors.border,
    alignItems: 'center', justifyContent: 'center',
  },
  stepBtnText:      { fontSize: 22, color: Colors.textPrimary, fontWeight: '300', lineHeight: 26 },
  disabled:         { color: Colors.textMuted },
  amountBox:        { flex: 1, alignItems: 'center' },
  amountValue:      { fontSize: 28, fontWeight: '800', color: Colors.gold },
  amountUnit:       { fontSize: 12, color: Colors.textMuted, marginTop: 2 },
  presets:          { flexDirection: 'row', gap: 8, marginBottom: 16 },
  preset:           {
    flex: 1, paddingVertical: 9, borderRadius: 8,
    backgroundColor: Colors.elevated, borderWidth: 1, borderColor: Colors.border,
    alignItems: 'center',
  },
  presetActive:     { borderColor: Colors.gold, backgroundColor: 'rgba(255,167,38,0.12)' },
  presetText:       { fontSize: 13, color: Colors.textSecondary, fontWeight: '600' },
  presetTextActive: { color: Colors.gold },
  oddsRow:          {
    flexDirection: 'row', backgroundColor: Colors.elevated,
    borderRadius: 12, padding: 14,
  },
  oddsItem:         { flex: 1, alignItems: 'center' },
  oddsLabel:        { fontSize: 11, color: Colors.textMuted, marginBottom: 4 },
  oddsValue:        { fontSize: 18, fontWeight: '700' },
  divider:          { width: 1, backgroundColor: Colors.border, marginHorizontal: 8 },
});
