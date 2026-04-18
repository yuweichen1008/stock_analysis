/**
 * ErrorState — reusable error display with a retry button.
 */
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Colors } from '../constants/colors';

interface Props {
  message?: string;
  onRetry?: () => void;
}

export default function ErrorState({ message = '載入失敗', onRetry }: Props) {
  return (
    <View style={styles.container}>
      <Text style={styles.icon}>⚠️</Text>
      <Text style={styles.message}>{message}</Text>
      {onRetry && (
        <TouchableOpacity style={styles.btn} onPress={onRetry}>
          <Text style={styles.btnText}>重試</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32, backgroundColor: Colors.bg },
  icon:      { fontSize: 40, marginBottom: 12 },
  message:   { fontSize: 15, color: Colors.textSecondary, textAlign: 'center', marginBottom: 20 },
  btn:       { backgroundColor: Colors.surface, borderRadius: 10, paddingHorizontal: 24, paddingVertical: 12, borderWidth: 1, borderColor: Colors.border },
  btnText:   { color: Colors.textPrimary, fontSize: 14, fontWeight: '600' },
});
