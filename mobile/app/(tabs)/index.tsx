import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, RefreshControl, ScrollView,
  StyleSheet, Text, TouchableOpacity, View, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Colors } from '../../constants/colors';
import { Signals, SignalsData, Stocks, MoversData, BacktestResult, MoverRow, Weekly, WeeklySignalItem, WeeklySignalsResponse } from '../../lib/api';
import { getOrCreateDeviceId } from '../../lib/device';
import SignalCard from '../../components/SignalCard';

type Tab = 'signals' | 'movers' | 'backtest' | 'weekly';

export default function SignalsScreen() {
  const router = useRouter();
  const [tab, setTab]                   = useState<Tab>('movers');
  const [loading, setLoading]           = useState(true);
  const [refreshing, setRefreshing]     = useState(false);

  // Signals state
  const [twData, setTwData]             = useState<SignalsData | null>(null);
  const [usData, setUsData]             = useState<SignalsData | null>(null);
  const [market, setMarket]             = useState<'TW' | 'US'>('US');

  // Weekly signals state
  const [weeklyData, setWeeklyData]     = useState<WeeklySignalsResponse | null>(null);
  const [weeklyFilter, setWeeklyFilter] = useState<'all' | 'buy' | 'sell'>('all');

  // Movers + backtest state
  const [movers, setMovers]             = useState<MoversData | null>(null);
  const [moverCat, setMoverCat]         = useState<'all_movers' | 'top_gainers' | 'oversold' | 'high_volume'>('all_movers');
  const [backtest, setBacktest]         = useState<BacktestResult[] | null>(null);
  const [backtestLoading, setBtLoading] = useState(false);
  const [bettingOn, setBettingOn]       = useState<string | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const [tw, us, mv, wk] = await Promise.all([
        Signals.tw().catch(() => null),
        Signals.us().catch(() => null),
        Stocks.movers().catch(() => null),
        Weekly.signals().catch(() => null),
      ]);
      setTwData(tw);
      setUsData(us);
      setMovers(mv);
      setWeeklyData(wk);
    } catch (e) {
      console.warn('[Market] Fetch error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const loadBacktest = useCallback(async () => {
    if (!movers) return;
    setBtLoading(true);
    try {
      const tickers = movers.all_movers.slice(0, 8).map(m => m.ticker);
      const res = await Stocks.backtest(tickers);
      setBacktest(res.results);
    } catch (e) {
      console.warn('[Backtest] Error:', e);
    } finally {
      setBtLoading(false);
    }
  }, [movers]);

  useEffect(() => { load(); }, [load]);

  // Auto-load backtest when switching to that tab
  useEffect(() => {
    if (tab === 'backtest' && !backtest && movers) {
      loadBacktest();
    }
  }, [tab, backtest, movers, loadBacktest]);

  const placeBet = async (mover: MoverRow, direction: 'Bull' | 'Bear') => {
    setBettingOn(mover.ticker);
    try {
      const deviceId = await getOrCreateDeviceId();
      await Stocks.bet(deviceId, mover.ticker, direction, 200, mover.category);
      Alert.alert(
        '✅ 已下注',
        `${direction === 'Bull' ? '🟢 多方' : '🔴 空方'} ${mover.ticker}  200 coins\n結算：下個交易日收盤`,
      );
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? '下注失敗';
      const status = e?.response?.status;
      if (status === 409) {
        Alert.alert('ℹ️', `今日已押注 ${mover.ticker}`);
      } else {
        Alert.alert('❌ 失敗', detail);
      }
    } finally {
      setBettingOn(null);
    }
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={Colors.gold} size="large" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Top nav tabs */}
      <View style={styles.nav}>
        <NavBtn label="🔥 Movers"   active={tab === 'movers'}   onPress={() => setTab('movers')} />
        <NavBtn label="📈 Signals"  active={tab === 'signals'}  onPress={() => setTab('signals')} />
        <NavBtn label="📅 週訊號"   active={tab === 'weekly'}   onPress={() => setTab('weekly')} />
        <NavBtn label="🧪 Backtest" active={tab === 'backtest'} onPress={() => setTab('backtest')} />
      </View>

      <ScrollView
        style={{ flex: 1 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={Colors.gold} />}
        contentContainerStyle={styles.content}
      >
        {/* ── MOVERS tab ──────────────────────────────────────────── */}
        {tab === 'movers' && (
          <>
            {/* Category pills */}
            <View style={styles.pills}>
              {(['all_movers', 'top_gainers', 'oversold', 'high_volume'] as const).map(cat => (
                <TouchableOpacity
                  key={cat}
                  style={[styles.pill, moverCat === cat && styles.pillActive]}
                  onPress={() => setMoverCat(cat)}
                >
                  <Text style={[styles.pillText, moverCat === cat && styles.pillTextActive]}>
                    {catLabel(cat)}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {movers && (movers[moverCat] ?? []).length === 0 && (
              <Text style={styles.empty}>暫無資料（市場收盤中）</Text>
            )}

            {(movers?.[moverCat] ?? []).map(m => (
              <MoverCard
                key={m.ticker}
                mover={m}
                bettingOn={bettingOn}
                onBet={placeBet}
              />
            ))}

            {movers?.cached_at && (
              <Text style={styles.cacheNote}>
                更新：{new Date(movers.cached_at).toLocaleTimeString()}
              </Text>
            )}
          </>
        )}

        {/* ── SIGNALS tab ─────────────────────────────────────────── */}
        {tab === 'signals' && (
          <>
            <View style={styles.marketToggle}>
              {(['TW', 'US'] as const).map(m => (
                <TouchableOpacity
                  key={m}
                  style={[styles.toggleBtn, market === m && styles.toggleActive]}
                  onPress={() => setMarket(m)}
                >
                  <Text style={[styles.toggleText, market === m && styles.toggleTextActive]}>
                    {m === 'TW' ? '🇹🇼 台股' : '🇺🇸 美股'}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {(() => {
              const data = market === 'TW' ? twData : usData;
              const signals   = data?.signals   ?? [];
              const watchlist = data?.watchlist ?? [];
              if (!signals.length && !watchlist.length) {
                return <Text style={styles.empty}>今日無訊號資料</Text>;
              }
              return (
                <>
                  {signals.length > 0 && (
                    <>
                      <Text style={styles.sectionTitle}>📈 訊號 ({signals.length})</Text>
                      {signals.map((s, i) => <SignalCard key={i} item={s} variant="signal" />)}
                    </>
                  )}
                  {watchlist.length > 0 && (
                    <>
                      <Text style={styles.sectionTitle}>👀 觀察名單 ({watchlist.length})</Text>
                      {watchlist.map((s, i) => <SignalCard key={i} item={s} variant="watchlist" />)}
                    </>
                  )}
                </>
              );
            })()}
          </>
        )}

        {/* ── BACKTEST tab ────────────────────────────────────────── */}
        {tab === 'backtest' && (
          <>
            <Text style={styles.btDesc}>
              針對 Finviz 今日 Top Movers 進行 90 天均值回歸回測。
              進場訊號發出後次日開盤買入，持有1天。
            </Text>

            <TouchableOpacity
              style={[styles.btRefreshBtn, backtestLoading && styles.disabled]}
              onPress={loadBacktest}
              disabled={backtestLoading}
            >
              {backtestLoading
                ? <ActivityIndicator color={Colors.textPrimary} size="small" />
                : <Text style={styles.btRefreshText}>🔄 重新回測</Text>
              }
            </TouchableOpacity>

            {backtestLoading && (
              <View style={styles.center}>
                <Text style={styles.btHint}>回測中，約需 15–30 秒…</Text>
              </View>
            )}

            {backtest && backtest.map(r => <BacktestCard key={r.ticker} result={r} />)}

            {backtest && backtest.length === 0 && (
              <Text style={styles.empty}>無資料（請先前往 Movers 頁面載入）</Text>
            )}
          </>
        )}

        {/* ── WEEKLY tab ──────────────────────────────────────────── */}
        {tab === 'weekly' && (
          <>
            {weeklyData && (
              <Text style={styles.cacheNote}>
                週結算：{weeklyData.week_ending} · {weeklyData.count} 個訊號
              </Text>
            )}
            <View style={styles.pills}>
              {(['all', 'buy', 'sell'] as const).map(f => (
                <TouchableOpacity
                  key={f}
                  style={[styles.pill, weeklyFilter === f && styles.pillActive]}
                  onPress={() => setWeeklyFilter(f)}
                >
                  <Text style={[styles.pillText, weeklyFilter === f && styles.pillTextActive]}>
                    {f === 'all' ? '全部' : f === 'buy' ? '🟢 買入' : '🔴 賣出'}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {!weeklyData && <Text style={styles.empty}>週訊號載入中…</Text>}
            {weeklyData && weeklyData.signals.length === 0 && (
              <Text style={styles.empty}>本週暫無 ±5% 訊號</Text>
            )}
            {(weeklyData?.signals ?? [])
              .filter(s => weeklyFilter === 'all' || s.signal_type === weeklyFilter)
              .map(s => <WeeklySignalCard key={s.id} item={s} />)}
          </>
        )}
      </ScrollView>
    </View>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function NavBtn({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <TouchableOpacity
      style={[navStyles.btn, active && navStyles.active]}
      onPress={onPress}
    >
      <Text style={[navStyles.text, active && navStyles.activeText]}>{label}</Text>
    </TouchableOpacity>
  );
}

function MoverCard({ mover, bettingOn, onBet }: {
  mover: MoverRow;
  bettingOn: string | null;
  onBet: (m: MoverRow, d: 'Bull' | 'Bear') => void;
}) {
  const up      = mover.change >= 0;
  const loading = bettingOn === mover.ticker;

  return (
    <View style={moverStyles.card}>
      <View style={moverStyles.top}>
        <View style={moverStyles.info}>
          <Text style={moverStyles.ticker}>{mover.ticker}</Text>
          <Text style={moverStyles.name} numberOfLines={1}>{mover.name}</Text>
        </View>
        <View style={moverStyles.priceCol}>
          {mover.price != null && (
            <Text style={moverStyles.price}>${mover.price.toFixed(2)}</Text>
          )}
          <Text style={[moverStyles.change, { color: up ? Colors.bull : Colors.bear }]}>
            {up ? '+' : ''}{mover.change.toFixed(2)}%
          </Text>
        </View>
      </View>

      <View style={moverStyles.metrics}>
        {mover.rsi != null && (
          <Chip label="RSI" value={mover.rsi.toFixed(0)}
            color={mover.rsi < 30 ? Colors.bull : mover.rsi > 70 ? Colors.bear : Colors.textMuted} />
        )}
        <Chip label="Vol" value={fmtVol(mover.volume)} color={Colors.textMuted} />
        {mover.pe != null && <Chip label="P/E" value={mover.pe.toFixed(1)} color={Colors.textMuted} />}
        <Chip label={catEmoji(mover.category)} value={mover.category.replace('_', ' ')} color={Colors.gold} />
      </View>

      <View style={moverStyles.btns}>
        <TouchableOpacity
          style={[moverStyles.btn, moverStyles.bullBtn, loading && styles.disabled]}
          onPress={() => onBet(mover, 'Bull')}
          disabled={loading}
        >
          <Text style={moverStyles.btnTxt}>{loading ? '…' : '🟢 Bull +200'}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[moverStyles.btn, moverStyles.bearBtn, loading && styles.disabled]}
          onPress={() => onBet(mover, 'Bear')}
          disabled={loading}
        >
          <Text style={moverStyles.btnTxt}>{loading ? '…' : '🔴 Bear +200'}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function BacktestCard({ result }: { result: BacktestResult }) {
  const good = result.win_rate >= 55;
  return (
    <View style={btStyles.card}>
      <View style={btStyles.header}>
        <Text style={btStyles.ticker}>{result.ticker}</Text>
        <View style={[btStyles.badge, good ? btStyles.badgeGood : btStyles.badgeBad]}>
          <Text style={[btStyles.badgeText, { color: good ? Colors.bull : Colors.bear }]}>
            {result.win_rate.toFixed(0)}% WR
          </Text>
        </View>
      </View>
      <View style={btStyles.row}>
        <BtStat label="總交易" value={String(result.total_trades)} />
        <BtStat label="勝" value={String(result.wins)} color={Colors.bull} />
        <BtStat label="敗" value={String(result.losses)} color={Colors.bear} />
        <BtStat
          label="平均報酬"
          value={`${result.avg_return >= 0 ? '+' : ''}${result.avg_return.toFixed(2)}%`}
          color={result.avg_return >= 0 ? Colors.bull : Colors.bear}
        />
      </View>
      {result.last_signal && (
        <Text style={btStyles.last}>最近訊號：{result.last_signal}</Text>
      )}
    </View>
  );
}

function WeeklySignalCard({ item }: { item: WeeklySignalItem }) {
  const isBuy   = item.signal_type === 'buy';
  const retPct  = (item.return_pct * 100).toFixed(1);
  const qty     = item.last_price && item.last_price > 0
    ? (5 / item.last_price).toFixed(4)
    : null;
  const putFrac = (item.put_volume && item.call_volume && (item.put_volume + item.call_volume) > 0)
    ? item.put_volume / (item.put_volume + item.call_volume)
    : null;

  return (
    <View style={wkStyles.card}>
      <View style={wkStyles.header}>
        <View style={[wkStyles.badge, isBuy ? wkStyles.buyBadge : wkStyles.sellBadge]}>
          <Text style={[wkStyles.badgeText, { color: isBuy ? Colors.bull : Colors.bear }]}>
            {isBuy ? '🟢 買入' : '🔴 賣出'}
          </Text>
        </View>
        <Text style={wkStyles.ticker}>{item.ticker}</Text>
        <Text style={[wkStyles.ret, { color: isBuy ? Colors.bull : Colors.bear }]}>
          {isBuy ? '' : '+'}{retPct}%
        </Text>
      </View>

      <View style={wkStyles.row}>
        {item.last_price != null && (
          <Chip label="價格" value={`$${item.last_price.toFixed(2)}`} color={Colors.textPrimary} />
        )}
        {qty && <Chip label="≈數量" value={qty} color={Colors.textMuted} />}
        <Chip label="金額" value="$5" color={Colors.gold} />
        {item.pcr != null && (
          <Chip label="PCR" value={item.pcr.toFixed(2)} color={item.pcr > 1.0 ? Colors.bear : Colors.bull} />
        )}
      </View>

      {putFrac != null && (
        <View style={wkStyles.pcrBar}>
          <View style={[wkStyles.pcrPut, { flex: putFrac }]} />
          <View style={[wkStyles.pcrCall, { flex: 1 - putFrac }]} />
        </View>
      )}
      {item.pcr_label && (
        <Text style={wkStyles.pcrLabel}>{item.pcr_label.replace('_', ' ')}</Text>
      )}
    </View>
  );
}

function Chip({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={chipStyles.chip}>
      <Text style={chipStyles.label}>{label}</Text>
      <Text style={[chipStyles.value, { color }]}>{value}</Text>
    </View>
  );
}

function BtStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={{ alignItems: 'center', flex: 1 }}>
      <Text style={{ fontSize: 15, fontWeight: '700', color: color ?? Colors.textPrimary }}>{value}</Text>
      <Text style={{ fontSize: 10, color: Colors.textMuted, marginTop: 1 }}>{label}</Text>
    </View>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function catLabel(cat: string) {
  return { all_movers: 'ALL', top_gainers: '🚀 漲', oversold: '📉 超跌', high_volume: '📊 爆量' }[cat] ?? cat;
}
function catEmoji(cat: string) {
  return { top_gainer: '🚀', oversold: '📉', high_volume: '📊' }[cat] ?? '📌';
}
function fmtVol(v: number) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)     return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

// ── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: Colors.bg },
  center:       { alignItems: 'center', justifyContent: 'center', padding: 20 },
  content:      { padding: 12, paddingBottom: 40 },
  nav:          { flexDirection: 'row', padding: 10, gap: 6, borderBottomWidth: 1, borderBottomColor: Colors.border },
  pills:        { flexDirection: 'row', gap: 6, marginBottom: 12, flexWrap: 'wrap' },
  pill:         { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  pillActive:   { borderColor: Colors.gold, backgroundColor: 'rgba(255,167,38,0.15)' },
  pillText:     { fontSize: 12, color: Colors.textSecondary, fontWeight: '600' },
  pillTextActive:{ color: Colors.gold },
  empty:        { color: Colors.textMuted, fontSize: 14, textAlign: 'center', marginTop: 40 },
  cacheNote:    { fontSize: 11, color: Colors.textMuted, textAlign: 'center', marginTop: 8 },
  marketToggle: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  toggleBtn:    { flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: Colors.surface, alignItems: 'center', borderWidth: 1, borderColor: Colors.border },
  toggleActive: { borderColor: Colors.blue, backgroundColor: 'rgba(68,138,255,0.12)' },
  toggleText:   { fontSize: 13, fontWeight: '600', color: Colors.textSecondary },
  toggleTextActive: { color: Colors.blue },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: Colors.textSecondary, marginBottom: 8, marginTop: 4 },
  btDesc:       { fontSize: 12, color: Colors.textMuted, marginBottom: 12, lineHeight: 18 },
  btRefreshBtn: { backgroundColor: Colors.elevated, borderRadius: 10, padding: 12, alignItems: 'center', marginBottom: 16, borderWidth: 1, borderColor: Colors.border },
  btRefreshText:{ fontSize: 14, fontWeight: '600', color: Colors.textPrimary },
  btHint:       { fontSize: 12, color: Colors.textMuted },
  disabled:     { opacity: 0.5 },
});

const navStyles = StyleSheet.create({
  btn:        { flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center', backgroundColor: Colors.surface },
  active:     { backgroundColor: Colors.elevated, borderBottomWidth: 2, borderBottomColor: Colors.gold },
  text:       { fontSize: 13, color: Colors.textSecondary, fontWeight: '600' },
  activeText: { color: Colors.textPrimary },
});

const moverStyles = StyleSheet.create({
  card:    { backgroundColor: Colors.surface, borderRadius: 14, padding: 14, marginBottom: 10 },
  top:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 },
  info:    { flex: 1, marginRight: 8 },
  ticker:  { fontSize: 18, fontWeight: '800', color: Colors.textPrimary },
  name:    { fontSize: 11, color: Colors.textSecondary, marginTop: 2 },
  priceCol:{ alignItems: 'flex-end' },
  price:   { fontSize: 16, fontWeight: '700', color: Colors.textPrimary },
  change:  { fontSize: 14, fontWeight: '700', marginTop: 2 },
  metrics: { flexDirection: 'row', gap: 8, marginBottom: 12, flexWrap: 'wrap' },
  btns:    { flexDirection: 'row', gap: 8 },
  btn:     { flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center' },
  bullBtn: { backgroundColor: Colors.bullDim, borderWidth: 1, borderColor: Colors.bull },
  bearBtn: { backgroundColor: Colors.bearDim, borderWidth: 1, borderColor: Colors.bear },
  btnTxt:  { fontSize: 13, fontWeight: '700', color: Colors.textPrimary },
});

const chipStyles = StyleSheet.create({
  chip:  { backgroundColor: Colors.elevated, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 },
  label: { fontSize: 9, color: Colors.textMuted, textTransform: 'uppercase' },
  value: { fontSize: 12, fontWeight: '600' },
});

const btStyles = StyleSheet.create({
  card:      { backgroundColor: Colors.surface, borderRadius: 14, padding: 14, marginBottom: 10 },
  header:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  ticker:    { fontSize: 18, fontWeight: '800', color: Colors.textPrimary },
  badge:     { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20, borderWidth: 1 },
  badgeGood: { backgroundColor: Colors.bullDim, borderColor: Colors.bull },
  badgeBad:  { backgroundColor: Colors.bearDim, borderColor: Colors.bear },
  badgeText: { fontSize: 13, fontWeight: '700' },
  row:       { flexDirection: 'row', paddingVertical: 4 },
  last:      { fontSize: 10, color: Colors.textMuted, marginTop: 8 },
});

const wkStyles = StyleSheet.create({
  card:      { backgroundColor: Colors.surface, borderRadius: 14, padding: 14, marginBottom: 10 },
  header:    { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  badge:     { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20, borderWidth: 1 },
  buyBadge:  { backgroundColor: Colors.bullDim, borderColor: Colors.bull },
  sellBadge: { backgroundColor: Colors.bearDim, borderColor: Colors.bear },
  badgeText: { fontSize: 11, fontWeight: '700' },
  ticker:    { fontSize: 18, fontWeight: '800', color: Colors.textPrimary, flex: 1 },
  ret:       { fontSize: 15, fontWeight: '700' },
  row:       { flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 8 },
  pcrBar:    { flexDirection: 'row', height: 6, borderRadius: 3, overflow: 'hidden', marginBottom: 4 },
  pcrPut:    { backgroundColor: Colors.bear },
  pcrCall:   { backgroundColor: Colors.bull },
  pcrLabel:  { fontSize: 10, color: Colors.textMuted, textTransform: 'capitalize' },
});
