import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, Alert, RefreshControl, ScrollView,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { Colors } from '../../constants/colors';
import { Oracle, OracleRow, Sandbox, Stocks, UserData, MoverRow } from '../../lib/api';
import { getOrCreateDeviceId } from '../../lib/device';
import BetSlider from '../../components/BetSlider';

const MIN_BET       = 100;
const MAX_BET       = 2000;
const STOCK_BET_AMT = 200;   // fixed amount for stock picks

export default function BetScreen() {
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
        Sandbox.me(deviceId),
        Stocks.movers().catch(() => null),
      ]);
      setOracle(o);
      setMe(m);
      setMovers(mv?.all_movers?.slice(0, 6) ?? []);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? '載入失敗');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Oracle Bull/Bear bet
  const placeBet = async (direction: 'Bull' | 'Bear') => {
    if (!me) return;
    setSubmitting(true);
    setError(null);
    try {
      const deviceId = await getOrCreateDeviceId();
      await Sandbox.bet(deviceId, direction, amount);
      setSuccess(true);
      await load();
    } catch (e: any) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail ?? '下注失敗';
      if (status === 423) {
        setError('市場已開盤，今日截止 09:00 TST');
      } else if (status === 409) {
        setError('今日已下注');
        await load();
      } else {
        setError(detail);
      }
    } finally {
      setSubmitting(false);
    }
  };

  // Individual stock bet
  const placeStockBet = async (mover: MoverRow, direction: 'Bull' | 'Bear') => {
    setStockBetting(mover.ticker);
    try {
      const deviceId = await getOrCreateDeviceId();
      await Stocks.bet(deviceId, mover.ticker, direction, STOCK_BET_AMT, mover.category);
      Alert.alert(
        '✅ 已押注',
        `${direction === 'Bull' ? '🟢 多方' : '🔴 空方'} ${mover.ticker}  ${STOCK_BET_AMT} coins\n結算：下個交易日收盤`,
      );
      await load();
    } catch (e: any) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail ?? '下注失敗';
      if (status === 409) {
        Alert.alert('ℹ️', `今日已押注 ${mover.ticker}`);
      } else {
        Alert.alert('❌ 失敗', detail);
      }
    } finally {
      setStockBetting(null);
    }
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={Colors.gold} size="large" />
      </View>
    );
  }

  const todayBet = me?.today_bet ?? null;
  const hasBet   = !!todayBet;
  const coins    = me?.coins ?? 0;
  const maxBet   = Math.min(MAX_BET, Math.max(MIN_BET, coins - 100));
  const noPred   = !oracle || oracle.status === 'no_prediction';

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={Colors.gold} />}
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>🎯 下注</Text>
        <View style={styles.coinsRow}>
          <Text style={styles.coinsLabel}>餘額</Text>
          <Text style={styles.coinsValue}>{coins.toLocaleString()} coins</Text>
        </View>
      </View>

      {/* ── ORACLE BET SECTION ── */}
      <Text style={styles.sectionLabel}>🔮 大盤預測 Oracle</Text>

      {noPred && (
        <View style={styles.card}>
          <Text style={styles.placeholder}>🌙 今日預測尚未生成</Text>
          <Text style={styles.placeholderHint}>08:00 TST 後開放下注</Text>
        </View>
      )}

      {!noPred && hasBet && (
        <View style={[styles.card, styles.lockedCard]}>
          <Text style={styles.lockedTitle}>✅ 今日已押注</Text>
          <View style={styles.betSummary}>
            <BetStat label="方向" value={todayBet!.direction === 'Bull' ? '🟢 多方 BULL' : '🔴 空方 BEAR'} />
            <BetStat label="金額" value={`${todayBet!.amount.toLocaleString()} coins`} />
            <BetStat label="狀態" value={todayBet!.status === 'settled' ? '已結算' : '待結算'} />
            {todayBet!.payout != null && (
              <BetStat
                label="結果"
                value={`${todayBet!.payout >= 0 ? '+' : ''}${todayBet!.payout.toLocaleString()} coins`}
                color={todayBet!.payout >= 0 ? Colors.bull : Colors.bear}
              />
            )}
          </View>
          <Text style={styles.lockedHint}>截止後於 14:05 TST 自動結算</Text>
        </View>
      )}

      {!noPred && !hasBet && (
        <View style={styles.card}>
          {oracle && (
            <View style={styles.predHint}>
              <Text style={styles.predText}>
                Oracle 今日預測：{oracle.direction === 'Bull' ? '🟢 多方' : '🔴 空方'}
                {'  '}{(oracle.confidence_pct ?? 0).toFixed(0)}% 信心
              </Text>
            </View>
          )}

          <BetSlider value={amount} min={MIN_BET} max={maxBet} onChange={setAmount} />

          {error && <Text style={styles.error}>{error}</Text>}
          {success && <Text style={styles.successMsg}>✅ 已下注！</Text>}

          <View style={styles.btnRow}>
            <TouchableOpacity
              style={[styles.betBtn, styles.bullBtn, submitting && styles.disabled]}
              onPress={() => placeBet('Bull')}
              disabled={submitting}
            >
              <Text style={styles.betBtnText}>🟢 多方 BULL</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.betBtn, styles.bearBtn, submitting && styles.disabled]}
              onPress={() => placeBet('Bear')}
              disabled={submitting}
            >
              <Text style={styles.betBtnText}>🔴 空方 BEAR</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.lockNote}>下注截止時間：09:00 TST</Text>
        </View>
      )}

      {/* ── STOCK PICKS SECTION ── */}
      {movers.length > 0 && (
        <>
          <View style={styles.sectionRow}>
            <Text style={styles.sectionLabel}>🔥 個股押注 (Finviz Top Movers)</Text>
            <Text style={styles.sectionHint}>固定 {STOCK_BET_AMT} coins · 最多 3 筆/日</Text>
          </View>

          {movers.map(mover => (
            <StockPickRow
              key={mover.ticker}
              mover={mover}
              bettingOn={stockBetting}
              onBet={placeStockBet}
            />
          ))}
        </>
      )}

      {/* Stats */}
      {me && me.total_bets > 0 && (
        <View style={styles.statsCard}>
          <Text style={styles.statsTitle}>大盤押注戰績</Text>
          <View style={styles.statsRow}>
            <StatPill label="勝" value={String(me.wins)} color={Colors.bull} />
            <StatPill label="敗" value={String(me.losses)} color={Colors.bear} />
            <StatPill label="勝率" value={`${me.win_rate_pct.toFixed(0)}%`} color={Colors.gold} />
          </View>
        </View>
      )}
    </ScrollView>
  );
}

// ── Stock pick row ────────────────────────────────────────────────────────────

function StockPickRow({ mover, bettingOn, onBet }: {
  mover:     MoverRow;
  bettingOn: string | null;
  onBet:     (m: MoverRow, d: 'Bull' | 'Bear') => void;
}) {
  const loading = bettingOn === mover.ticker;
  const up = mover.change >= 0;
  return (
    <View style={pickStyles.row}>
      <View style={pickStyles.left}>
        <Text style={pickStyles.ticker}>{mover.ticker}</Text>
        <Text style={pickStyles.name} numberOfLines={1}>{mover.name}</Text>
      </View>
      <View style={pickStyles.mid}>
        {mover.price != null && (
          <Text style={pickStyles.price}>${mover.price.toFixed(2)}</Text>
        )}
        <Text style={[pickStyles.change, { color: up ? Colors.bull : Colors.bear }]}>
          {up ? '+' : ''}{mover.change.toFixed(2)}%
        </Text>
      </View>
      <View style={pickStyles.btns}>
        <TouchableOpacity
          style={[pickStyles.btn, pickStyles.bull, loading && styles.disabled]}
          onPress={() => onBet(mover, 'Bull')}
          disabled={loading}
        >
          <Text style={pickStyles.btnTxt}>{loading ? '…' : '🟢'}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[pickStyles.btn, pickStyles.bear, loading && styles.disabled]}
          onPress={() => onBet(mover, 'Bear')}
          disabled={loading}
        >
          <Text style={pickStyles.btnTxt}>{loading ? '…' : '🔴'}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function BetStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={betStyles.row}>
      <Text style={betStyles.label}>{label}</Text>
      <Text style={[betStyles.value, color ? { color } : {}]}>{value}</Text>
    </View>
  );
}

function StatPill({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={betStyles.pill}>
      <Text style={[betStyles.pillValue, { color }]}>{value}</Text>
      <Text style={betStyles.pillLabel}>{label}</Text>
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const pickStyles = StyleSheet.create({
  row:    {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.surface, borderRadius: 12,
    padding: 12, marginBottom: 8,
  },
  left:   { flex: 2 },
  ticker: { fontSize: 15, fontWeight: '800', color: Colors.textPrimary },
  name:   { fontSize: 11, color: Colors.textMuted, marginTop: 1 },
  mid:    { flex: 1, alignItems: 'flex-end', marginRight: 10 },
  price:  { fontSize: 13, fontWeight: '600', color: Colors.textPrimary },
  change: { fontSize: 12, fontWeight: '700' },
  btns:   { flexDirection: 'row', gap: 6 },
  btn:    { width: 38, height: 38, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  bull:   { backgroundColor: Colors.bullDim, borderWidth: 1, borderColor: Colors.bull },
  bear:   { backgroundColor: Colors.bearDim, borderWidth: 1, borderColor: Colors.bear },
  btnTxt: { fontSize: 16 },
});

const betStyles = StyleSheet.create({
  row:       { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5 },
  label:     { fontSize: 13, color: Colors.textSecondary },
  value:     { fontSize: 13, fontWeight: '600', color: Colors.textPrimary },
  pill:      { flex: 1, alignItems: 'center', paddingVertical: 10 },
  pillValue: { fontSize: 18, fontWeight: '700' },
  pillLabel: { fontSize: 11, color: Colors.textMuted, marginTop: 2 },
});

const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: Colors.bg },
  center:          { justifyContent: 'center', alignItems: 'center' },
  content:         { padding: 16, paddingBottom: 40 },
  header:          { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 14, marginTop: 12 },
  headerTitle:     { fontSize: 28, fontWeight: '800', color: Colors.textPrimary },
  coinsRow:        { alignItems: 'flex-end' },
  coinsLabel:      { fontSize: 11, color: Colors.textMuted },
  coinsValue:      { fontSize: 16, fontWeight: '700', color: Colors.gold },
  sectionRow:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 },
  sectionLabel:    { fontSize: 13, fontWeight: '700', color: Colors.textSecondary, marginBottom: 8 },
  sectionHint:     { fontSize: 11, color: Colors.textMuted },
  card:            { backgroundColor: Colors.surface, borderRadius: 16, padding: 18, marginBottom: 14 },
  lockedCard:      { borderWidth: 1, borderColor: Colors.border },
  lockedTitle:     { fontSize: 16, fontWeight: '700', color: Colors.textPrimary, marginBottom: 14 },
  betSummary:      { marginBottom: 12 },
  lockedHint:      { fontSize: 11, color: Colors.textMuted, textAlign: 'center' },
  predHint:        { backgroundColor: Colors.elevated, borderRadius: 10, padding: 12, marginBottom: 16 },
  predText:        { fontSize: 13, color: Colors.textSecondary },
  placeholder:     { fontSize: 16, fontWeight: '700', color: Colors.textSecondary, textAlign: 'center', marginVertical: 16 },
  placeholderHint: { fontSize: 12, color: Colors.textMuted, textAlign: 'center' },
  error:           { color: Colors.bear, fontSize: 13, marginBottom: 10, textAlign: 'center' },
  successMsg:      { color: Colors.bull, fontSize: 13, marginBottom: 10, textAlign: 'center', fontWeight: '600' },
  btnRow:          { flexDirection: 'row', gap: 10, marginTop: 16, marginBottom: 10 },
  betBtn:          { flex: 1, borderRadius: 12, padding: 15, alignItems: 'center' },
  bullBtn:         { backgroundColor: Colors.bullDim, borderWidth: 1.5, borderColor: Colors.bull },
  bearBtn:         { backgroundColor: Colors.bearDim, borderWidth: 1.5, borderColor: Colors.bear },
  betBtnText:      { fontSize: 15, fontWeight: '800', color: Colors.textPrimary },
  disabled:        { opacity: 0.5 },
  lockNote:        { fontSize: 11, color: Colors.textMuted, textAlign: 'center' },
  statsCard:       { backgroundColor: Colors.surface, borderRadius: 16, padding: 16, marginTop: 8 },
  statsTitle:      { fontSize: 14, fontWeight: '700', color: Colors.textPrimary, marginBottom: 10 },
  statsRow:        { flexDirection: 'row' },
});
