/**
 * Oracle tab — 3 sub-views: Prediction | Bet | History
 * Merges former index.tsx, bet.tsx, and history.tsx.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, Alert, FlatList, RefreshControl,
  ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { Colors } from '../../constants/colors';
import {
  Oracle, OracleRow, OracleStats, LiveData,
  Sandbox, UserData, BetRow, Stocks, MoverRow,
} from '../../lib/api';
import { getOrCreateDeviceId } from '../../lib/device';
import OracleCard from '../../components/OracleCard';
import BetSlider from '../../components/BetSlider';

type SubTab = 'prediction' | 'bet' | 'history';

const MIN_BET       = 100;
const MAX_BET       = 2000;
const STOCK_BET_AMT = 200;

export default function OracleScreen() {
  const [subTab, setSubTab] = useState<SubTab>('prediction');

  return (
    <View style={styles.root}>
      {/* Sub-nav pills */}
      <View style={styles.pills}>
        {(['prediction', 'bet', 'history'] as SubTab[]).map(t => (
          <TouchableOpacity
            key={t}
            style={[styles.pill, subTab === t && styles.pillActive]}
            onPress={() => setSubTab(t)}
          >
            <Text style={[styles.pillText, subTab === t && styles.pillTextActive]}>
              {t === 'prediction' ? '🔮 預測' : t === 'bet' ? '🎯 下注' : '📅 紀錄'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {subTab === 'prediction' && <PredictionView />}
      {subTab === 'bet'        && <BetView />}
      {subTab === 'history'    && <HistoryView />}
    </View>
  );
}

// ── Prediction sub-view ───────────────────────────────────────────────────────

function PredictionView() {
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [oracle, setOracle]       = useState<OracleRow | null>(null);
  const [stats,  setStats]        = useState<OracleStats | null>(null);
  const [live,   setLive]         = useState<LiveData | null>(null);
  const liveTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const [o, s, l] = await Promise.all([Oracle.today(), Oracle.stats(), Oracle.live()]);
      setOracle(o); setStats(s); setLive(l);
    } catch (e) { console.warn('[Oracle] Fetch error:', e); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => {
    load();
    liveTimer.current = setInterval(() => Oracle.live().then(setLive).catch(() => {}), 5 * 60 * 1000);
    return () => { if (liveTimer.current) clearInterval(liveTimer.current); };
  }, [load]);

  if (loading) return <Spinner />;

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={Colors.gold} />}
    >
      <View style={styles.header}>
        <Text style={styles.headerTitle}>🔮 Oracle</Text>
        <Text style={styles.headerSub}>TAIEX 大盤多空預測</Text>
      </View>
      <OracleCard oracle={oracle} live={live} />
      {stats && stats.resolved > 0 && (
        <View style={styles.statsRow}>
          <StatPill label="勝率"  value={`${stats.win_rate_pct.toFixed(0)}%`} color={Colors.gold} />
          <StatPill label="連勝"  value={`${stats.streak}`} color={stats.streak >= 2 ? Colors.bull : Colors.textSecondary} />
          <StatPill label="積分"  value={`${stats.cumulative_score > 0 ? '+' : ''}${stats.cumulative_score}`} color={Colors.blue} />
          <StatPill label="戰績"  value={`${stats.wins}/${stats.resolved}`} color={Colors.textSecondary} />
        </View>
      )}
      {oracle?.factors && Object.keys(oracle.factors).length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📐 因子分析</Text>
          {Object.entries(oracle.factors).map(([key, val]) => (
            <FactorRow key={key} name={key} value={val as number} />
          ))}
        </View>
      )}
      {live?.last_updated && (
        <Text style={styles.liveNote}>台指 {live.current_level?.toLocaleString() ?? '—'}  ·  更新 {live.last_updated}</Text>
      )}
    </ScrollView>
  );
}

// ── Bet sub-view ─────────────────────────────────────────────────────────────

function BetView() {
  const [loading, setLoading]         = useState(true);
  const [refreshing, setRefreshing]   = useState(false);
  const [oracle, setOracle]           = useState<OracleRow | null>(null);
  const [me, setMe]                   = useState<UserData | null>(null);
  const [amount, setAmount]           = useState(500);
  const [submitting, setSubmitting]   = useState(false);
  const [error, setError]             = useState<string | null>(null);
  const [success, setSuccess]         = useState(false);
  const [movers, setMovers]           = useState<MoverRow[]>([]);
  const [stockBetting, setStockBetting] = useState<string | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    setError(null);
    try {
      const deviceId = await getOrCreateDeviceId();
      const [o, m, mv] = await Promise.all([
        Oracle.today(),
        Sandbox.meByDevice(deviceId).catch(() => null),
        Stocks.movers().catch(() => null),
      ]);
      setOracle(o); setMe(m); setMovers(mv?.all_movers?.slice(0, 6) ?? []);
    } catch (e: any) { setError(e?.response?.data?.detail ?? '載入失敗'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const placeBet = async (direction: 'Bull' | 'Bear') => {
    if (!me) return;
    setSubmitting(true); setError(null);
    try {
      const deviceId = await getOrCreateDeviceId();
      await Sandbox.bet(deviceId, direction, amount);
      setSuccess(true); await load();
    } catch (e: any) {
      const s = e?.response?.status;
      if (s === 423) setError('市場已開盤，今日截止 09:00 TST');
      else if (s === 409) { setError('今日已下注'); await load(); }
      else setError(e?.response?.data?.detail ?? '下注失敗');
    } finally { setSubmitting(false); }
  };

  const placeStockBet = async (mover: MoverRow, direction: 'Bull' | 'Bear') => {
    setStockBetting(mover.ticker);
    try {
      const deviceId = await getOrCreateDeviceId();
      await Stocks.bet(deviceId, mover.ticker, direction, STOCK_BET_AMT, mover.category);
      Alert.alert('✅ 已押注', `${direction === 'Bull' ? '🟢 多方' : '🔴 空方'} ${mover.ticker}  ${STOCK_BET_AMT} coins`);
      await load();
    } catch (e: any) {
      const s = e?.response?.status;
      if (s === 409) Alert.alert('ℹ️', `今日已押注 ${mover.ticker}`);
      else Alert.alert('❌ 失敗', e?.response?.data?.detail ?? '下注失敗');
    } finally { setStockBetting(null); }
  };

  if (loading) return <Spinner />;
  const todayBet = me?.today_bet ?? null;
  const coins    = me?.coins ?? 0;
  const maxBet   = Math.min(MAX_BET, Math.max(MIN_BET, coins - 100));
  const noPred   = !oracle || oracle.status === 'no_prediction';

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={Colors.gold} />}
    >
      <View style={styles.headerRow}>
        <Text style={styles.headerTitle}>🎯 下注</Text>
        <View style={{ alignItems: 'flex-end' }}>
          <Text style={styles.coinsLabel}>餘額</Text>
          <Text style={styles.coinsValue}>{coins.toLocaleString()} coins</Text>
        </View>
      </View>

      <Text style={styles.sectionLabel}>🔮 大盤預測 Oracle</Text>
      {noPred && (
        <View style={styles.card}><Text style={styles.placeholder}>🌙 今日預測尚未生成</Text></View>
      )}
      {!noPred && todayBet && (
        <View style={[styles.card, styles.lockedCard]}>
          <Text style={styles.lockedTitle}>✅ 今日已押注</Text>
          <BetStat label="方向" value={todayBet.direction === 'Bull' ? '🟢 多方 BULL' : '🔴 空方 BEAR'} />
          <BetStat label="金額" value={`${todayBet.amount.toLocaleString()} coins`} />
          <BetStat label="狀態" value={todayBet.status === 'settled' ? '已結算' : '待結算'} />
          {todayBet.payout != null && (
            <BetStat label="結果" value={`${todayBet.payout >= 0 ? '+' : ''}${todayBet.payout.toLocaleString()} coins`}
              color={todayBet.payout >= 0 ? Colors.bull : Colors.bear} />
          )}
        </View>
      )}
      {!noPred && !todayBet && (
        <View style={styles.card}>
          {oracle && (
            <View style={styles.predHint}>
              <Text style={styles.predText}>
                Oracle 今日預測：{oracle.direction === 'Bull' ? '🟢 多方' : '🔴 空方'}{'  '}{(oracle.confidence_pct ?? 0).toFixed(0)}% 信心
              </Text>
            </View>
          )}
          <BetSlider value={amount} min={MIN_BET} max={maxBet} onChange={setAmount} />
          {error   && <Text style={styles.error}>{error}</Text>}
          {success && <Text style={styles.success}>✅ 已下注！</Text>}
          <View style={styles.btnRow}>
            <TouchableOpacity style={[styles.betBtn, styles.bullBtn, submitting && styles.disabled]} onPress={() => placeBet('Bull')} disabled={submitting}>
              <Text style={styles.betBtnText}>🟢 多方 BULL</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.betBtn, styles.bearBtn, submitting && styles.disabled]} onPress={() => placeBet('Bear')} disabled={submitting}>
              <Text style={styles.betBtnText}>🔴 空方 BEAR</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.lockNote}>下注截止時間：09:00 TST</Text>
        </View>
      )}

      {movers.length > 0 && (
        <>
          <Text style={[styles.sectionLabel, { marginTop: 8 }]}>🔥 個股押注 (Finviz Top Movers)</Text>
          {movers.map(m => (
            <StockPickRow key={m.ticker} mover={m} bettingOn={stockBetting} onBet={placeStockBet} />
          ))}
        </>
      )}
    </ScrollView>
  );
}

// ── History sub-view ──────────────────────────────────────────────────────────

function HistoryView() {
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [bets, setBets]             = useState<BetRow[]>([]);
  const [me, setMe]                 = useState<UserData | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const deviceId = await getOrCreateDeviceId();
      const [history, user] = await Promise.all([Sandbox.history(deviceId), Sandbox.meByDevice(deviceId)]);
      setBets(history); setMe(user);
    } catch (e) { console.warn('[History]', e); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <Spinner />;

  return (
    <View style={styles.root}>
      {me && (
        <View style={styles.coinsHeader}>
          <View>
            <Text style={styles.coinsLabel}>虛擬幣餘額</Text>
            <Text style={styles.coinsValue}>{me.coins.toLocaleString()} coins</Text>
          </View>
          <View style={{ flexDirection: 'row' }}>
            <StatPill label="勝"   value={String(me.wins)}  color={Colors.bull} />
            <StatPill label="敗"   value={String(me.losses)} color={Colors.bear} />
            <StatPill label="勝率" value={`${me.win_rate_pct.toFixed(0)}%`} color={Colors.gold} />
          </View>
        </View>
      )}
      {bets.length === 0 ? (
        <View style={[styles.root, styles.center]}><Text style={styles.empty}>尚無下注紀錄</Text></View>
      ) : (
        <FlatList
          data={bets}
          keyExtractor={(_, i) => String(i)}
          renderItem={({ item }) => <BetItem bet={item} />}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={Colors.gold} />}
          contentContainerStyle={{ padding: 12, paddingBottom: 32 }}
        />
      )}
    </View>
  );
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function Spinner() {
  return (
    <View style={[styles.root, styles.center]}>
      <ActivityIndicator color={Colors.gold} size="large" />
    </View>
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

function FactorRow({ name, value }: { name: string; value: number }) {
  const pos = value > 0;
  return (
    <View style={styles.factorRow}>
      <Text style={styles.factorName}>{name.replace(/_/g, ' ')}</Text>
      <Text style={[styles.factorVal, { color: pos ? Colors.bull : Colors.bear }]}>
        {pos ? '▲' : '▼'} {Math.abs(value).toFixed(2)}
      </Text>
    </View>
  );
}

function BetStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.betStatRow}>
      <Text style={styles.betStatLabel}>{label}</Text>
      <Text style={[styles.betStatValue, color ? { color } : {}]}>{value}</Text>
    </View>
  );
}

function BetItem({ bet }: { bet: BetRow }) {
  const isBull = bet.direction === 'Bull';
  const settled = bet.status === 'settled';
  const won = settled && bet.is_correct;
  return (
    <View style={styles.betRow}>
      <View style={{ flex: 2 }}>
        <Text style={styles.betDate}>{bet.date}</Text>
        <View style={[styles.dirPill, isBull ? styles.bullPill : styles.bearPill]}>
          <Text style={styles.dirText}>{isBull ? '🟢 多方' : '🔴 空方'}</Text>
        </View>
      </View>
      <View style={{ flex: 1, alignItems: 'center' }}>
        <Text style={styles.betAmount}>{bet.amount.toLocaleString()}</Text>
        <Text style={{ fontSize: 10, color: Colors.textMuted }}>coins</Text>
      </View>
      <View style={{ flex: 1, alignItems: 'flex-end' }}>
        {settled ? (
          <>
            <Text style={[styles.betPayout, { color: (bet.payout ?? 0) >= 0 ? Colors.bull : Colors.bear }]}>
              {bet.payout != null ? `${bet.payout >= 0 ? '+' : ''}${bet.payout.toLocaleString()}` : '—'}
            </Text>
            <Text style={{ fontSize: 11, color: won ? Colors.bull : Colors.bear, fontWeight: '600' }}>
              {won ? '✅ 命中' : '❌ 失準'}
            </Text>
          </>
        ) : (
          <Text style={{ fontSize: 12, color: Colors.textMuted }}>待結算</Text>
        )}
      </View>
    </View>
  );
}

function StockPickRow({ mover, bettingOn, onBet }: {
  mover: MoverRow; bettingOn: string | null; onBet: (m: MoverRow, d: 'Bull' | 'Bear') => void;
}) {
  const busy = bettingOn === mover.ticker;
  const up   = mover.change >= 0;
  return (
    <View style={styles.stockRow}>
      <View style={{ flex: 2 }}>
        <Text style={styles.stockTicker}>{mover.ticker}</Text>
        <Text style={styles.stockName} numberOfLines={1}>{mover.name}</Text>
      </View>
      <View style={{ flex: 1, alignItems: 'flex-end', marginRight: 10 }}>
        {mover.price != null && <Text style={styles.stockPrice}>${mover.price.toFixed(2)}</Text>}
        <Text style={[styles.stockChange, { color: up ? Colors.bull : Colors.bear }]}>
          {up ? '+' : ''}{mover.change.toFixed(2)}%
        </Text>
      </View>
      <View style={{ flexDirection: 'row', gap: 6 }}>
        <TouchableOpacity style={[styles.stockBtn, styles.bullStockBtn, busy && styles.disabled]} onPress={() => onBet(mover, 'Bull')} disabled={busy}>
          <Text style={{ fontSize: 16 }}>{busy ? '…' : '🟢'}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.stockBtn, styles.bearStockBtn, busy && styles.disabled]} onPress={() => onBet(mover, 'Bear')} disabled={busy}>
          <Text style={{ fontSize: 16 }}>{busy ? '…' : '🔴'}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  root:         { flex: 1, backgroundColor: Colors.bg },
  center:       { justifyContent: 'center', alignItems: 'center' },
  scroll:       { flex: 1, backgroundColor: Colors.bg },
  content:      { padding: 16, paddingBottom: 40 },
  // Sub-nav pills
  pills:        { flexDirection: 'row', backgroundColor: Colors.surface, paddingHorizontal: 16, paddingVertical: 10, gap: 8 },
  pill:         { flex: 1, paddingVertical: 8, borderRadius: 10, alignItems: 'center', backgroundColor: Colors.elevated },
  pillActive:   { backgroundColor: Colors.tabActive },
  pillText:     { fontSize: 12, fontWeight: '600', color: Colors.textSecondary },
  pillTextActive:{ color: Colors.bg },
  // Headers
  header:       { marginBottom: 20, marginTop: 12 },
  headerRow:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 14, marginTop: 12 },
  headerTitle:  { fontSize: 26, fontWeight: '800', color: Colors.textPrimary },
  headerSub:    { fontSize: 13, color: Colors.textSecondary, marginTop: 2 },
  coinsLabel:   { fontSize: 11, color: Colors.textMuted },
  coinsValue:   { fontSize: 16, fontWeight: '700', color: Colors.gold },
  coinsHeader:  {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    backgroundColor: Colors.surface, padding: 18, borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  // Stats
  statsRow:     { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 },
  statPill:     { flex: 1, backgroundColor: Colors.surface, borderRadius: 12, alignItems: 'center', paddingVertical: 10, marginHorizontal: 3 },
  pillValue:    { fontSize: 16, fontWeight: '700' },
  pillLabel:    { fontSize: 10, color: Colors.textMuted, marginTop: 2 },
  // Cards
  card:         { backgroundColor: Colors.surface, borderRadius: 16, padding: 18, marginBottom: 14 },
  lockedCard:   { borderWidth: 1, borderColor: Colors.border },
  lockedTitle:  { fontSize: 16, fontWeight: '700', color: Colors.textPrimary, marginBottom: 12 },
  predHint:     { backgroundColor: Colors.elevated, borderRadius: 10, padding: 12, marginBottom: 16 },
  predText:     { fontSize: 13, color: Colors.textSecondary },
  placeholder:  { fontSize: 16, fontWeight: '700', color: Colors.textSecondary, textAlign: 'center', marginVertical: 16 },
  // Bet buttons
  btnRow:       { flexDirection: 'row', gap: 10, marginTop: 16, marginBottom: 10 },
  betBtn:       { flex: 1, borderRadius: 12, padding: 15, alignItems: 'center' },
  bullBtn:      { backgroundColor: Colors.bullDim, borderWidth: 1.5, borderColor: Colors.bull },
  bearBtn:      { backgroundColor: Colors.bearDim, borderWidth: 1.5, borderColor: Colors.bear },
  betBtnText:   { fontSize: 15, fontWeight: '800', color: Colors.textPrimary },
  lockNote:     { fontSize: 11, color: Colors.textMuted, textAlign: 'center' },
  disabled:     { opacity: 0.5 },
  error:        { color: Colors.bear,  fontSize: 13, marginBottom: 10, textAlign: 'center' },
  success:      { color: Colors.bull,  fontSize: 13, marginBottom: 10, textAlign: 'center', fontWeight: '600' },
  // Bet stat rows
  betStatRow:   { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  betStatLabel: { fontSize: 13, color: Colors.textSecondary },
  betStatValue: { fontSize: 13, fontWeight: '600', color: Colors.textPrimary },
  // Bet history rows
  betRow:       { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: 12, padding: 14, marginBottom: 8 },
  betDate:      { fontSize: 12, color: Colors.textMuted, marginBottom: 4 },
  dirPill:      { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, alignSelf: 'flex-start' },
  bullPill:     { backgroundColor: Colors.bullDim },
  bearPill:     { backgroundColor: Colors.bearDim },
  dirText:      { fontSize: 12, fontWeight: '600', color: Colors.textPrimary },
  betAmount:    { fontSize: 16, fontWeight: '700', color: Colors.textPrimary },
  betPayout:    { fontSize: 16, fontWeight: '700' },
  // Section
  sectionLabel: { fontSize: 13, fontWeight: '700', color: Colors.textSecondary, marginBottom: 8 },
  // Stock picks
  stockRow:     { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: 12, padding: 12, marginBottom: 8 },
  stockTicker:  { fontSize: 15, fontWeight: '800', color: Colors.textPrimary },
  stockName:    { fontSize: 11, color: Colors.textMuted, marginTop: 1 },
  stockPrice:   { fontSize: 13, fontWeight: '600', color: Colors.textPrimary },
  stockChange:  { fontSize: 12, fontWeight: '700' },
  stockBtn:     { width: 38, height: 38, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  bullStockBtn: { backgroundColor: Colors.bullDim, borderWidth: 1, borderColor: Colors.bull },
  bearStockBtn: { backgroundColor: Colors.bearDim, borderWidth: 1, borderColor: Colors.bear },
  // Factor
  factorRow:    { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5 },
  factorName:   { fontSize: 13, color: Colors.textSecondary, textTransform: 'capitalize' },
  factorVal:    { fontSize: 13, fontWeight: '600' },
  liveNote:     { textAlign: 'center', fontSize: 11, color: Colors.textMuted, marginTop: 8 },
  empty:        { color: Colors.textMuted, fontSize: 15 },
});
