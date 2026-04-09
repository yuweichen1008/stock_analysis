import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, FlatList, RefreshControl,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { Colors } from '../../constants/colors';
import { Signals, SignalsData } from '../../lib/api';
import SignalCard from '../../components/SignalCard';

type Market = 'TW' | 'US';

export default function MarketScreen() {
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [market, setMarket]         = useState<Market>('TW');
  const [tw, setTw]                 = useState<SignalsData | null>(null);
  const [us, setUs]                 = useState<SignalsData | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const [twData, usData] = await Promise.all([Signals.tw(), Signals.us()]);
      setTw(twData);
      setUs(usData);
    } catch (e) {
      console.warn('[Market] Fetch error:', e);
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

  const data     = market === 'TW' ? tw : us;
  const signals  = data?.signals  ?? [];
  const watchlist = data?.watchlist ?? [];
  const sections: { title: string; data: typeof signals }[] = [];
  if (signals.length)   sections.push({ title: `📈 訊號 (${signals.length})`,   data: signals });
  if (watchlist.length) sections.push({ title: `👀 觀察名單 (${watchlist.length})`, data: watchlist });

  return (
    <View style={styles.container}>
      {/* Tab switcher */}
      <View style={styles.switcher}>
        {(['TW', 'US'] as Market[]).map(m => (
          <TouchableOpacity
            key={m}
            style={[styles.switchBtn, market === m && styles.switchActive]}
            onPress={() => setMarket(m)}
          >
            <Text style={[styles.switchText, market === m && styles.switchTextActive]}>
              {m === 'TW' ? '🇹🇼 台股' : '🇺🇸 美股'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {sections.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.empty}>今日無訊號資料</Text>
        </View>
      ) : (
        <FlatList
          data={sections}
          keyExtractor={s => s.title}
          renderItem={({ item: section }) => (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>{section.title}</Text>
              {section.data.map((sig, i) => (
                <SignalCard
                  key={`${sig.ticker}-${i}`}
                  item={sig}
                  variant={section.title.startsWith('📈') ? 'signal' : 'watchlist'}
                />
              ))}
            </View>
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

const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: Colors.bg },
  center:          { flex: 1, justifyContent: 'center', alignItems: 'center' },
  switcher:        {
    flexDirection: 'row', padding: 12, gap: 8,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  switchBtn:       {
    flex: 1, paddingVertical: 10, borderRadius: 10,
    backgroundColor: Colors.surface, alignItems: 'center',
    borderWidth: 1, borderColor: Colors.border,
  },
  switchActive:    { borderColor: Colors.blue, backgroundColor: 'rgba(68,138,255,0.12)' },
  switchText:      { fontSize: 14, fontWeight: '600', color: Colors.textSecondary },
  switchTextActive:{ color: Colors.blue },
  list:            { padding: 12, paddingBottom: 32 },
  section:         { marginBottom: 16 },
  sectionTitle:    { fontSize: 14, fontWeight: '700', color: Colors.textSecondary, marginBottom: 8 },
  empty:           { color: Colors.textMuted, fontSize: 15 },
});
