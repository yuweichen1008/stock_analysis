/**
 * News tab — 12-hour rolling news feed with put/call ratio indicators.
 * US stocks show real PCR (options-derived); TW stocks show VADER sentiment proxy.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, FlatList, Linking, Modal,
  RefreshControl, SafeAreaView, ScrollView, StyleSheet,
  Text, TouchableOpacity, View,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Colors } from '../../constants/colors';
import { News, NewsItem, PcrSnapshot } from '../../lib/api';
import NewsCard from '../../components/NewsCard';
import PcrTimeline from '../../components/PcrTimeline';

type MarketFilter = 'all' | 'US' | 'TW';
const MARKET_OPTIONS: { value: MarketFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'US',  label: '🇺🇸 US' },
  { value: 'TW',  label: '🇹🇼 TW' },
];
const PAGE = 30;

export default function NewsScreen() {
  const [items,     setItems]     = useState<NewsItem[]>([]);
  const [market,    setMarket]    = useState<MarketFilter>('all');
  const [loading,   setLoading]   = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore,   setHasMore]   = useState(true);
  const [error,     setError]     = useState<string | null>(null);

  // Detail modal state
  const [selected,  setSelected]  = useState<NewsItem | null>(null);
  const [snapshots, setSnapshots] = useState<PcrSnapshot[]>([]);
  const [related,   setRelated]   = useState<NewsItem[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [modalVisible,  setModalVisible]  = useState(false);

  const offset = useRef(0);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) { offset.current = 0; setRefreshing(true); }
    else if (offset.current === 0) setLoading(true);
    setError(null);
    try {
      const data = await News.feed(market, 12, PAGE, offset.current);
      if (isRefresh || offset.current === 0) {
        setItems(data);
      } else {
        setItems(prev => [...prev, ...data]);
      }
      setHasMore(data.length === PAGE);
      offset.current += data.length;
    } catch (e: any) {
      setError(e?.message ?? '載入失敗');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [market]);

  // Reload when market filter changes
  useEffect(() => {
    offset.current = 0;
    setItems([]);
    setHasMore(true);
    load(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market]);

  // Refresh on tab focus
  useFocusEffect(useCallback(() => { load(true); }, [load]));

  const loadMore = async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const data = await News.feed(market, 12, PAGE, offset.current);
      setItems(prev => [...prev, ...data]);
      setHasMore(data.length === PAGE);
      offset.current += data.length;
    } catch { /* silent */ } finally {
      setLoadingMore(false);
    }
  };

  const openDetail = async (item: NewsItem) => {
    setSelected(item);
    setSnapshots([]);
    setRelated([]);
    setModalVisible(true);
    setDetailLoading(true);
    try {
      const [pcrData, relData] = await Promise.all([
        News.pcrHistory(item.id),
        News.related(item.id),
      ]);
      setSnapshots(pcrData.snapshots);
      setRelated(relData.related);
    } catch { /* silent */ } finally {
      setDetailLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>📰 News & PCR</Text>
        <Text style={styles.subtitle}>Last 12 hours</Text>
      </View>

      {/* Market filter pills */}
      <View style={styles.filterRow}>
        {MARKET_OPTIONS.map(opt => (
          <TouchableOpacity
            key={opt.value}
            style={[styles.filterPill, market === opt.value && styles.filterPillActive]}
            onPress={() => setMarket(opt.value)}
          >
            <Text style={[styles.filterText, market === opt.value && styles.filterTextActive]}>
              {opt.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* List */}
      {loading && items.length === 0 ? (
        <ActivityIndicator color={Colors.blue} style={{ marginTop: 40 }} />
      ) : error ? (
        <View style={styles.emptyState}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity onPress={() => load(true)}>
            <Text style={styles.retryText}>Retry</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={item => String(item.id)}
          renderItem={({ item }) => (
            <NewsCard item={item} onPress={() => openDetail(item)} />
          )}
          contentContainerStyle={styles.listContent}
          ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => load(true)}
              tintColor={Colors.blue}
            />
          }
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          ListFooterComponent={
            loadingMore ? <ActivityIndicator color={Colors.blue} style={{ marginVertical: 16 }} /> : null
          }
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Text style={styles.emptyText}>No news in the last 12 hours.</Text>
            </View>
          }
        />
      )}

      {/* Detail modal */}
      <Modal
        visible={modalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setModalVisible(false)}
      >
        <SafeAreaView style={styles.modal}>
          {/* Modal header */}
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setModalVisible(false)}>
              <Text style={styles.closeBtn}>✕ Close</Text>
            </TouchableOpacity>
            {selected?.url && (
              <TouchableOpacity onPress={() => Linking.openURL(selected.url!)}>
                <Text style={styles.articleLink}>View Article ↗</Text>
              </TouchableOpacity>
            )}
          </View>

          {selected && (
            <ScrollView style={styles.modalScroll} contentContainerStyle={styles.modalContent}>
              {/* Meta */}
              <View style={styles.metaRow}>
                {selected.ticker && <Text style={styles.metaTicker}>{selected.ticker}</Text>}
                {selected.source && <Text style={styles.metaSource}> · {selected.source}</Text>}
              </View>

              {/* Headline */}
              <Text style={styles.modalHeadline}>{selected.headline}</Text>

              {/* PCR or sentiment summary */}
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>
                  {selected.market === 'US' ? 'Put/Call Ratio' : 'Sentiment Proxy'}
                </Text>
                {selected.market === 'US' && selected.pcr != null ? (
                  <Text style={styles.pcrBig}>
                    {selected.pcr.toFixed(3)}{' '}
                    <Text style={styles.pcrLabelInline}>
                      ({(selected.pcr_label ?? '').replace(/_/g, ' ')})
                    </Text>
                  </Text>
                ) : (
                  <Text style={styles.sentimentBig}>
                    {selected.sentiment_label}
                    {selected.sentiment_score != null
                      ? ` (${selected.sentiment_score > 0 ? '+' : ''}${selected.sentiment_score.toFixed(2)})`
                      : ''}
                  </Text>
                )}
                {selected.market === 'TW' && (
                  <Text style={styles.proxyNote}>
                    Options PCR unavailable for TW stocks — using VADER NLP sentiment.
                  </Text>
                )}
              </View>

              {/* PCR timeline */}
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>
                  PCR History ({snapshots.length} snapshots)
                </Text>
                {detailLoading ? (
                  <ActivityIndicator color={Colors.blue} />
                ) : (
                  <PcrTimeline ticker={selected.ticker} snapshots={snapshots} />
                )}
              </View>

              {/* Related news */}
              {related.length > 0 && (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Related News ({related.length})</Text>
                  {related.map(rel => (
                    <TouchableOpacity
                      key={rel.id}
                      style={styles.relatedItem}
                      onPress={() => openDetail(rel)}
                    >
                      <View style={styles.relatedHeader}>
                        {rel.ticker && <Text style={styles.relatedTicker}>{rel.ticker}</Text>}
                        {rel.source && <Text style={styles.relatedSource}> · {rel.source}</Text>}
                        {rel.pcr != null && (
                          <Text style={styles.relatedPcr}> PCR {rel.pcr.toFixed(2)}</Text>
                        )}
                      </View>
                      <Text style={styles.relatedHeadline} numberOfLines={2}>
                        {rel.headline}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
            </ScrollView>
          )}
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:  { flex: 1, backgroundColor: Colors.bg },
  header:     { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 4 },
  title:      { fontSize: 22, fontWeight: '800', color: Colors.textPrimary },
  subtitle:   { fontSize: 13, color: Colors.textSecondary, marginTop: 2 },
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 8,
    gap: 8,
  },
  filterPill: {
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 6,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  filterPillActive: {
    backgroundColor: Colors.blue,
    borderColor: Colors.blue,
  },
  filterText:       { fontSize: 13, color: Colors.textSecondary, fontWeight: '600' },
  filterTextActive: { color: Colors.textPrimary },
  listContent: { paddingHorizontal: 16, paddingBottom: 16 },
  emptyState: { alignItems: 'center', marginTop: 60, gap: 12 },
  emptyText:  { color: Colors.textSecondary, fontSize: 15 },
  errorText:  { color: Colors.bear, fontSize: 15 },
  retryText:  { color: Colors.blue, fontSize: 14, fontWeight: '600' },

  // Modal
  modal: { flex: 1, backgroundColor: Colors.bg },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  closeBtn:     { color: Colors.textSecondary, fontSize: 15 },
  articleLink:  { color: Colors.blue, fontSize: 14, fontWeight: '600' },
  modalScroll:  { flex: 1 },
  modalContent: { padding: 16, gap: 20 },
  metaRow:      { flexDirection: 'row', alignItems: 'center' },
  metaTicker:   { fontSize: 14, fontWeight: '800', color: Colors.textPrimary },
  metaSource:   { fontSize: 13, color: Colors.textSecondary },
  modalHeadline: {
    fontSize: 18,
    fontWeight: '700',
    color: Colors.textPrimary,
    lineHeight: 26,
  },
  section: {
    backgroundColor: Colors.surface,
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: Colors.border,
    gap: 8,
  },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: Colors.textSecondary, textTransform: 'uppercase', letterSpacing: 0.5 },
  pcrBig: { fontSize: 32, fontWeight: '800', color: Colors.bear },
  pcrLabelInline: { fontSize: 14, fontWeight: '600', color: Colors.textSecondary },
  sentimentBig: { fontSize: 22, fontWeight: '700', color: Colors.bull },
  proxyNote: { fontSize: 11, color: Colors.textMuted, lineHeight: 16 },
  relatedItem: {
    backgroundColor: Colors.elevated,
    borderRadius: 10,
    padding: 12,
    gap: 4,
  },
  relatedHeader:   { flexDirection: 'row', alignItems: 'center' },
  relatedTicker:   { fontSize: 12, fontWeight: '700', color: Colors.textPrimary },
  relatedSource:   { fontSize: 11, color: Colors.textSecondary },
  relatedPcr:      { fontSize: 11, color: Colors.bear, fontWeight: '700' },
  relatedHeadline: { fontSize: 12, color: Colors.textPrimary, lineHeight: 17 },
});
