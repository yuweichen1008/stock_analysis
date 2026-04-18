/**
 * WatchlistButton — star icon that reads/writes the Zustand watchlist store.
 * Haptic feedback on press.
 */
import { StyleSheet, Text, TouchableOpacity } from 'react-native';
import { Colors } from '../constants/colors';
import { useWatchlistStore } from '../store/watchlist';
import * as Haptics from 'expo-haptics';

interface Props {
  ticker: string;
  market: string;
}

export default function WatchlistButton({ ticker, market }: Props) {
  const { isSaved, add, remove } = useWatchlistStore();
  const saved = isSaved(ticker, market);

  const handlePress = async () => {
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (saved) {
      await remove(ticker, market).catch(() => {});
    } else {
      await add(ticker, market).catch(() => {});
    }
  };

  return (
    <TouchableOpacity style={styles.btn} onPress={handlePress} hitSlop={8}>
      <Text style={[styles.star, saved && styles.starFilled]}>
        {saved ? '⭐' : '☆'}
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  btn:        { padding: 6 },
  star:       { fontSize: 22, color: Colors.textMuted },
  starFilled: { color: Colors.gold },
});
