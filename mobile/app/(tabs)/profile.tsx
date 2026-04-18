/**
 * Profile tab — user info, wallet stats, leaderboard, notifications, sign out.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, Alert, FlatList, RefreshControl,
  ScrollView, StyleSheet, Switch, Text, TouchableOpacity, View,
} from 'react-native';
import { Colors } from '../../constants/colors';
import { Sandbox, LeaderboardRow } from '../../lib/api';
import { useAuthStore } from '../../store/auth';
import ErrorState from '../../components/ErrorState';

interface MeStats {
  coins:        number;
  total_bets:   number;
  wins:         number;
  win_rate_pct: number;
}

export default function ProfileScreen() {
  const { user, logout } = useAuthStore();
  const [me,         setMe]         = useState<MeStats | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error,      setError]      = useState<string | null>(null);
  const [notifEnabled, setNotif]    = useState(true);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    setError(null);
    try {
      const [stats, lb] = await Promise.allSettled([
        Sandbox.me(),
        Sandbox.leaderboard(10),
      ]);
      if (stats.status === 'fulfilled') setMe(stats.value);
      if (lb.status === 'fulfilled')    setLeaderboard(lb.value);
    } catch (e: any) {
      setError(e?.message ?? '載入失敗');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, []);

  const handleLogout = () => {
    Alert.alert('登出', '確定要登出嗎？', [
      { text: '取消', style: 'cancel' },
      { text: '登出', style: 'destructive', onPress: () => logout() },
    ]);
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={Colors.gold} size="large" />
      </View>
    );
  }

  if (error && !me) return <ErrorState message={error} onRetry={() => load()} />;

  const rank = leaderboard.findIndex(r => r.id === user?.id);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={Colors.gold} />}
    >
      {/* User card */}
      <View style={styles.userCard}>
        <View style={styles.avatarLarge}>
          <Text style={styles.avatarText}>
            {(user?.display_name ?? 'P')[0].toUpperCase()}
          </Text>
        </View>
        <View style={{ flex: 1, marginLeft: 16 }}>
          <Text style={styles.displayName}>{user?.display_name ?? 'Player'}</Text>
          {user?.email && <Text style={styles.email}>{user.email}</Text>}
          <View style={styles.authBadge}>
            <Text style={styles.authBadgeText}>
              {user?.auth_provider === 'apple' ? ' Apple' :
               user?.auth_provider === 'google' ? 'G Google' : '👤 訪客'}
            </Text>
          </View>
        </View>
      </View>

      {/* Wallet stats */}
      <View style={styles.statsCard}>
        <Text style={styles.sectionTitle}>💰 虛擬錢包</Text>
        <View style={styles.statsRow}>
          <StatPill label="餘額" value={`${(me?.coins ?? user?.coins ?? 0).toLocaleString()}`} color={Colors.gold} />
          <StatPill label="下注數" value={String(me?.total_bets ?? 0)} color={Colors.textPrimary} />
          <StatPill label="勝率" value={`${(me?.win_rate_pct ?? 0).toFixed(0)}%`} color={me && me.win_rate_pct >= 50 ? Colors.bull : Colors.bear} />
          {rank >= 0 && <StatPill label="排名" value={`#${rank + 1}`} color={Colors.blue} />}
        </View>
      </View>

      {/* Leaderboard */}
      {leaderboard.length > 0 && (
        <View style={styles.leaderCard}>
          <Text style={styles.sectionTitle}>🏆 排行榜 Top 10</Text>
          {leaderboard.map((row, i) => (
            <View key={row.id} style={[styles.lbRow, row.id === user?.id && styles.lbRowSelf]}>
              <Text style={styles.lbRank}>#{row.rank}</Text>
              <Text style={styles.lbName} numberOfLines={1}>{row.display_name}</Text>
              <Text style={styles.lbCoins}>{row.coins.toLocaleString()}</Text>
              <Text style={styles.lbWin}>{row.win_rate.toFixed(0)}%</Text>
            </View>
          ))}
        </View>
      )}

      {/* Notification toggle */}
      <View style={styles.settingsCard}>
        <Text style={styles.sectionTitle}>⚙️ 設定</Text>
        <View style={styles.settingsRow}>
          <Text style={styles.settingsLabel}>推播通知</Text>
          <Switch
            value={notifEnabled}
            onValueChange={setNotif}
            trackColor={{ false: Colors.border, true: Colors.tabActive + '80' }}
            thumbColor={notifEnabled ? Colors.tabActive : Colors.textMuted}
          />
        </View>
      </View>

      {/* Sign out */}
      <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
        <Text style={styles.logoutText}>登出</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

function StatPill({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={styles.statPill}>
      <Text style={[styles.pillValue, { color }]}>{value}</Text>
      <Text style={styles.pillLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: Colors.bg },
  center:       { justifyContent: 'center', alignItems: 'center' },
  content:      { padding: 16, paddingBottom: 40, paddingTop: 56 },
  userCard:     { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: 16, padding: 20, marginBottom: 14 },
  avatarLarge:  { width: 60, height: 60, borderRadius: 30, backgroundColor: Colors.elevated, justifyContent: 'center', alignItems: 'center' },
  avatarText:   { fontSize: 26, fontWeight: '800', color: Colors.gold },
  displayName:  { fontSize: 18, fontWeight: '800', color: Colors.textPrimary },
  email:        { fontSize: 12, color: Colors.textMuted, marginTop: 2 },
  authBadge:    { marginTop: 6, backgroundColor: Colors.elevated, alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  authBadgeText:{ fontSize: 11, color: Colors.textSecondary, fontWeight: '600' },
  statsCard:    { backgroundColor: Colors.surface, borderRadius: 16, padding: 16, marginBottom: 14 },
  statsRow:     { flexDirection: 'row', justifyContent: 'space-between', marginTop: 10 },
  statPill:     { flex: 1, alignItems: 'center', paddingVertical: 8 },
  pillValue:    { fontSize: 20, fontWeight: '800' },
  pillLabel:    { fontSize: 11, color: Colors.textMuted, marginTop: 2 },
  leaderCard:   { backgroundColor: Colors.surface, borderRadius: 16, padding: 16, marginBottom: 14 },
  lbRow:        { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: Colors.border },
  lbRowSelf:    { backgroundColor: Colors.tabActive + '22', marginHorizontal: -4, paddingHorizontal: 4, borderRadius: 8 },
  lbRank:       { width: 30, fontSize: 12, color: Colors.textMuted, fontWeight: '700' },
  lbName:       { flex: 1, fontSize: 13, color: Colors.textPrimary, fontWeight: '600' },
  lbCoins:      { width: 80, fontSize: 12, color: Colors.gold, textAlign: 'right', fontWeight: '700' },
  lbWin:        { width: 40, fontSize: 12, color: Colors.textSecondary, textAlign: 'right' },
  settingsCard: { backgroundColor: Colors.surface, borderRadius: 16, padding: 16, marginBottom: 14 },
  settingsRow:  { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 },
  settingsLabel:{ fontSize: 14, color: Colors.textPrimary },
  logoutBtn:    { borderWidth: 1, borderColor: Colors.bear, borderRadius: 12, padding: 16, alignItems: 'center', marginTop: 4 },
  logoutText:   { fontSize: 15, fontWeight: '700', color: Colors.bear },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: Colors.textSecondary },
  blue:         { color: '#64b5f6' },
});
