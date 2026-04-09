import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, FlatList, RefreshControl,
  StyleSheet, Text, View,
} from 'react-native';
import { Colors } from '../../constants/colors';
import { Sandbox, LeaderboardRow } from '../../lib/api';
import { getOrCreateDeviceId } from '../../lib/device';

const MEDALS = ['🥇', '🥈', '🥉'];

export default function LeaderboardScreen() {
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [entries, setEntries]       = useState<LeaderboardRow[]>([]);
  const [myId, setMyId]             = useState<string | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const deviceId = await getOrCreateDeviceId();
      setMyId(deviceId);
      const data = await Sandbox.leaderboard(50);
      setEntries(data);
    } catch (e) {
      console.warn('[Leaderboard] Fetch error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={Colors.gold} size="large" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.titleRow}>
        <Text style={styles.title}>🏆 排行榜</Text>
      </View>

      {entries.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.empty}>尚無排行資料</Text>
        </View>
      ) : (
        <FlatList
          data={entries}
          keyExtractor={item => item.device_id}
          renderItem={({ item }) => (
            <LeaderRow entry={item} isMe={item.device_id === myId} />
          )}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={Colors.gold} />
          }
          contentContainerStyle={styles.list}
        />
      )}
    </View>
  );
}

function LeaderRow({ entry, isMe }: { entry: LeaderboardRow; isMe: boolean }) {
  const medal    = MEDALS[entry.rank - 1] ?? null;
  const rankText = medal ?? `#${entry.rank}`;

  return (
    <View style={[styles.row, isMe && styles.myRow]}>
      <Text style={[styles.rank, medal ? styles.medalRank : {}]}>{rankText}</Text>
      <View style={styles.nameCol}>
        <Text style={styles.nickname} numberOfLines={1}>
          {entry.nickname}{isMe ? '  (你)' : ''}
        </Text>
        <Text style={styles.stats}>
          {entry.wins}勝 / {entry.total_bets}場  勝率 {entry.win_rate.toFixed(0)}%
        </Text>
      </View>
      <Text style={styles.coins}>{entry.coins.toLocaleString()}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  center:    { flex: 1, justifyContent: 'center', alignItems: 'center' },
  titleRow:  { padding: 18, paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: Colors.border },
  title:     { fontSize: 22, fontWeight: '800', color: Colors.textPrimary },
  list:      { padding: 12, paddingBottom: 32 },
  empty:     { color: Colors.textMuted, fontSize: 15 },
  row:       {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.surface, borderRadius: 12, padding: 14, marginBottom: 8,
  },
  myRow:     { borderWidth: 1.5, borderColor: Colors.gold },
  rank:      { width: 40, fontSize: 14, color: Colors.textMuted, fontWeight: '700' },
  medalRank: { fontSize: 20 },
  nameCol:   { flex: 1, marginHorizontal: 8 },
  nickname:  { fontSize: 15, fontWeight: '700', color: Colors.textPrimary },
  stats:     { fontSize: 11, color: Colors.textMuted, marginTop: 2 },
  coins:     { fontSize: 16, fontWeight: '800', color: Colors.gold },
});
