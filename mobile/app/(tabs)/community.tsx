/**
 * Community tab — social signal feed with infinite scroll and reactions.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, FlatList, RefreshControl,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Colors } from '../../constants/colors';
import { Feed, PostItem } from '../../lib/api';
import PostCard from '../../components/PostCard';
import ErrorState from '../../components/ErrorState';

type MarketFilter = 'all' | 'TW' | 'US';
const MARKET_OPTIONS: MarketFilter[] = ['all', 'TW', 'US'];
const PAGE_SIZE = 20;

export default function CommunityScreen() {
  const router = useRouter();
  const [posts,      setPosts]      = useState<PostItem[]>([]);
  const [market,     setMarket]     = useState<MarketFilter>('all');
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore,    setHasMore]    = useState(true);
  const [error,      setError]      = useState<string | null>(null);
  const offset = useRef(0);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) { offset.current = 0; setRefreshing(true); }
    else setLoading(true);
    setError(null);
    try {
      const data = await Feed.list(market, PAGE_SIZE, offset.current);
      if (isRefresh) {
        setPosts(data);
      } else {
        setPosts(prev => [...prev, ...data]);
      }
      setHasMore(data.length === PAGE_SIZE);
      offset.current += data.length;
    } catch (e: any) {
      setError(e?.message ?? '載入失敗');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [market]);

  useEffect(() => { load(); }, [load]);

  const loadMore = async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const data = await Feed.list(market, PAGE_SIZE, offset.current);
      setPosts(prev => [...prev, ...data]);
      setHasMore(data.length === PAGE_SIZE);
      offset.current += data.length;
    } catch {} finally { setLoadingMore(false); }
  };

  if (error && posts.length === 0) return <ErrorState message={error} onRetry={() => load()} />;

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>👥 社群</Text>
        <TouchableOpacity
          style={styles.createBtn}
          onPress={() => router.push('/create-post')}
        >
          <Text style={styles.createBtnText}>+ 發文</Text>
        </TouchableOpacity>
      </View>

      {/* Market filter */}
      <View style={styles.filters}>
        {MARKET_OPTIONS.map(m => (
          <TouchableOpacity
            key={m}
            style={[styles.filterPill, market === m && styles.filterActive]}
            onPress={() => { setMarket(m); offset.current = 0; }}
          >
            <Text style={[styles.filterText, market === m && styles.filterTextActive]}>
              {m === 'all' ? '全部' : m}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading && posts.length === 0 ? (
        <View style={styles.center}>
          <ActivityIndicator color={Colors.gold} size="large" />
        </View>
      ) : (
        <FlatList
          data={posts}
          keyExtractor={p => String(p.id)}
          renderItem={({ item }) => <PostCard post={item} />}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={Colors.gold} />
          }
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          ListFooterComponent={
            loadingMore ? <ActivityIndicator color={Colors.gold} style={{ marginVertical: 16 }} /> : null
          }
          ListEmptyComponent={
            <View style={styles.center}>
              <Text style={styles.empty}>目前尚無貼文 — 率先發文吧！</Text>
            </View>
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: Colors.bg },
  center:          { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32 },
  header:          { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, paddingTop: 56, backgroundColor: Colors.surface, borderBottomWidth: 1, borderBottomColor: Colors.border },
  title:           { fontSize: 22, fontWeight: '800', color: Colors.textPrimary },
  createBtn:       { backgroundColor: Colors.tabActive, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 8 },
  createBtnText:   { fontSize: 13, fontWeight: '700', color: Colors.bg },
  filters:         { flexDirection: 'row', gap: 8, padding: 12, backgroundColor: Colors.surface },
  filterPill:      { paddingHorizontal: 14, paddingVertical: 7, borderRadius: 20, backgroundColor: Colors.elevated },
  filterActive:    { backgroundColor: Colors.tabActive },
  filterText:      { fontSize: 13, fontWeight: '600', color: Colors.textSecondary },
  filterTextActive:{ color: Colors.bg },
  list:            { padding: 12, paddingBottom: 32 },
  empty:           { color: Colors.textMuted, fontSize: 15, textAlign: 'center' },
});
