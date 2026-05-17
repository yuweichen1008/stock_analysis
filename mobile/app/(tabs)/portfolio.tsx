/**
 * Portfolio tab — Robinhood-style CTBC portfolio view.
 * Shows total value, daily P&L, asset history chart (bar approximation),
 * period selector pills, buying power, and holdings list.
 *
 * Auth states:
 *   - Not logged in  → lock + Sign In CTA
 *   - Logged in, no CTBC creds (has_ctbc === false) → Connect CTBC prompt
 *   - Logged in + CTBC configured → full portfolio view
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { router } from 'expo-router';
import { Colors } from '../../constants/colors';
import {
  Broker,
  AccountSnapshot,
  BrokerBalance,
  BrokerPosition,
} from '../../lib/api';
import { useAuthStore } from '../../store/auth';

// ── Formatting helpers ────────────────────────────────────────────────────────

const NT = (n: number) =>
  `NT$${Math.round(n).toLocaleString('zh-TW', { maximumFractionDigits: 0 })}`;

const pnlStr = (n: number) => (n >= 0 ? '+' : '') + NT(n);

const pct = (n: number) => (n >= 0 ? '+' : '') + n.toFixed(2) + '%';

// ── Period config ─────────────────────────────────────────────────────────────

type Period = '1D' | '1W' | '1M' | '3M' | 'YTD' | '1Y';

const ytdDays = () => {
  const now = new Date();
  const jan1 = new Date(now.getFullYear(), 0, 1);
  return Math.ceil((now.getTime() - jan1.getTime()) / 86_400_000);
};

const PERIOD_DAYS: Record<Period, number> = {
  '1D':  1,
  '1W':  7,
  '1M':  30,
  '3M':  90,
  'YTD': ytdDays(),
  '1Y':  365,
};

const PERIODS: Period[] = ['1D', '1W', '1M', '3M', 'YTD', '1Y'];

function cutoffDate(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().split('T')[0];
}

function filterByPeriod(data: AccountSnapshot[], period: Period): AccountSnapshot[] {
  const cutoff = cutoffDate(PERIOD_DAYS[period]);
  return data.filter(s => s.date >= cutoff);
}

// ── Bar-chart approximation (no external SVG dependency) ─────────────────────

interface MiniChartProps {
  data: AccountSnapshot[];
  color: string;
}

function MiniChart({ data, color }: MiniChartProps) {
  if (data.length === 0) {
    return <View style={styles.chartPlaceholder} />;
  }

  const values = data.map(d => d.total_value ?? 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  return (
    <View style={styles.chart}>
      {data.map((d, i) => {
        const val = d.total_value ?? 0;
        const heightPct = ((val - min) / range) * 100;
        const barH = Math.max(4, (heightPct / 100) * 96);
        return (
          <View key={i} style={styles.barWrapper}>
            <View style={[styles.bar, { height: barH, backgroundColor: color }]} />
          </View>
        );
      })}
    </View>
  );
}

// ── Skeleton components ───────────────────────────────────────────────────────

function SkeletonRect({ width, height }: { width: number | string; height: number }) {
  return (
    <View
      style={{
        width: width as number,
        height,
        borderRadius: 8,
        backgroundColor: Colors.border,
        marginVertical: 4,
      }}
    />
  );
}

// ── Auth CTA screens ──────────────────────────────────────────────────────────

function NotLoggedIn() {
  return (
    <View style={styles.ctaContainer}>
      <Text style={styles.ctaIcon}>🔒</Text>
      <Text style={styles.ctaTitle}>Connect your broker</Text>
      <Text style={styles.ctaBody}>
        Login and add CTBC or Moomoo credentials to see your portfolio here.
      </Text>
      <TouchableOpacity style={styles.ctaBtn} onPress={() => router.push('/auth')}>
        <Text style={styles.ctaBtnText}>Sign In</Text>
      </TouchableOpacity>
    </View>
  );
}

function NoCtbcCreds() {
  return (
    <View style={styles.ctaContainer}>
      <Text style={styles.ctaIcon}>🏦</Text>
      <Text style={styles.ctaTitle}>Connect CTBC</Text>
      <Text style={styles.ctaBody}>
        You're signed in, but no CTBC credentials are saved yet.
        Go to Profile → Settings to add them.
      </Text>
      <TouchableOpacity style={styles.ctaBtn} onPress={() => router.push('/profile')}>
        <Text style={styles.ctaBtnText}>Go to Profile</Text>
      </TouchableOpacity>
    </View>
  );
}

// ── Main screen ───────────────────────────────────────────────────────────────

export default function PortfolioScreen() {
  const { token, user } = useAuthStore();
  const isLoggedIn = !!token;
  const hasCtbc = user?.has_ctbc === true;

  const [balance,      setBalance]     = useState<BrokerBalance | null>(null);
  const [positions,    setPositions]   = useState<BrokerPosition[]>([]);
  const [history,      setHistory]     = useState<AccountSnapshot[]>([]);
  const [period,       setPeriod]      = useState<Period>('1M');
  const [loading,      setLoading]     = useState(false);
  const [refreshing,   setRefreshing]  = useState(false);
  const [brokerError,  setBrokerError] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (!isLoggedIn) return;
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setBrokerError(false);

    const [bal, pos, hist] = await Promise.allSettled([
      Broker.balance('TW'),
      Broker.positions('TW'),
      Broker.assetHistory('TW', 365),
    ]);

    if (bal.status  === 'fulfilled') setBalance(bal.value);
    if (pos.status  === 'fulfilled') setPositions(pos.value);
    if (hist.status === 'fulfilled') setHistory(hist.value);

    const anyFailed =
      bal.status  === 'rejected' ||
      pos.status  === 'rejected' ||
      hist.status === 'rejected';
    if (anyFailed) setBrokerError(true);

    setLoading(false);
    setRefreshing(false);
  }, [isLoggedIn]);

  useEffect(() => {
    if (isLoggedIn && hasCtbc) load();
  }, [isLoggedIn, hasCtbc, load]);

  // ── Not logged in ──────────────────────────────────────────────────────────
  if (!isLoggedIn) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>💼 Portfolio</Text>
        </View>
        <NotLoggedIn />
      </View>
    );
  }

  // ── Logged in but no CTBC ──────────────────────────────────────────────────
  if (!hasCtbc) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>💼 Portfolio</Text>
        </View>
        <NoCtbcCreds />
      </View>
    );
  }

  // ── Full portfolio view ────────────────────────────────────────────────────
  const filteredHistory = filterByPeriod(history, period);

  const firstVal    = filteredHistory.length > 0 ? (filteredHistory[0].total_value  ?? 0) : null;
  const currentVal  = balance?.total_value ?? null;
  const dailyPnl    = balance?.unrealized_pnl ?? null;
  const chartColor  =
    currentVal !== null && firstVal !== null
      ? (currentVal >= firstVal ? Colors.bull : Colors.bear)
      : Colors.bull;

  const dailyPnlPct =
    currentVal && firstVal && firstVal !== 0
      ? ((currentVal - firstVal) / firstVal) * 100
      : null;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => load(true)}
          tintColor={Colors.bull}
        />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>💼 Portfolio</Text>
      </View>

      {/* Broker error banner */}
      {brokerError && (
        <View style={styles.errorBanner}>
          <Text style={styles.errorBannerText}>
            ⚠️ CTBC unavailable — showing last known data
          </Text>
        </View>
      )}

      {/* Total value + P&L */}
      <View style={styles.heroCard}>
        {loading ? (
          <>
            <SkeletonRect width={180} height={36} />
            <SkeletonRect width={130} height={20} />
          </>
        ) : (
          <>
            <Text style={styles.totalValue}>
              {currentVal !== null ? NT(currentVal) : '—'}
            </Text>
            {dailyPnl !== null && (
              <View style={styles.pnlRow}>
                <Text style={[styles.pnlText, { color: dailyPnl >= 0 ? Colors.bull : Colors.bear }]}>
                  {dailyPnl >= 0 ? '▲' : '▼'} {pnlStr(dailyPnl)}
                  {dailyPnlPct !== null ? ` (${pct(dailyPnlPct)})` : ''}
                  {'  Today'}
                </Text>
              </View>
            )}
          </>
        )}
      </View>

      {/* Asset history chart */}
      <View style={styles.chartCard}>
        {loading ? (
          <View style={[styles.chartPlaceholder, { backgroundColor: Colors.border }]} />
        ) : (
          <MiniChart data={filteredHistory} color={chartColor} />
        )}
      </View>

      {/* Period pills */}
      <View style={styles.pillRow}>
        {PERIODS.map(p => (
          <TouchableOpacity
            key={p}
            style={[styles.pill, period === p && styles.pillActive]}
            onPress={() => setPeriod(p)}
          >
            <Text style={[styles.pillText, period === p && styles.pillTextActive]}>
              {p}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Buying power */}
      <View style={styles.rowCard}>
        <Text style={styles.rowLabel}>Buying Power</Text>
        {loading ? (
          <SkeletonRect width={100} height={18} />
        ) : (
          <Text style={styles.rowValue}>
            {balance ? NT(balance.cash) : '—'}
          </Text>
        )}
      </View>

      {/* Holdings */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Holdings</Text>

        {loading && (
          <>
            <SkeletonRect width="100%" height={60} />
            <SkeletonRect width="100%" height={60} />
            <SkeletonRect width="100%" height={60} />
          </>
        )}

        {!loading && positions.length === 0 && (
          <Text style={styles.emptyText}>No holdings found.</Text>
        )}

        {!loading && positions.map((pos, i) => {
          const pnlColor = pos.pnl >= 0 ? Colors.bull : Colors.bear;
          const pnlPct   =
            pos.avg_cost > 0
              ? ((pos.pnl / (pos.avg_cost * pos.qty)) * 100)
              : 0;
          return (
            <View key={`${pos.ticker}-${i}`} style={styles.holdingCard}>
              <View style={styles.holdingLeft}>
                <Text style={styles.holdingTicker}>{pos.ticker}</Text>
                <Text style={styles.holdingMeta}>
                  {pos.qty.toLocaleString()} shares · NT${pos.avg_cost.toFixed(1)}
                </Text>
              </View>
              <View style={styles.holdingRight}>
                <Text style={styles.holdingValue}>{NT(pos.mkt_value)}</Text>
                <Text style={[styles.holdingPnl, { color: pnlColor }]}>
                  {pnlStr(pos.pnl)} ({pct(pnlPct)})
                </Text>
              </View>
            </View>
          );
        })}
      </View>
    </ScrollView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: Colors.bg },
  content:         { paddingBottom: 40 },

  header:          {
    paddingTop: 56,
    paddingBottom: 16,
    paddingHorizontal: 20,
    backgroundColor: Colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  headerTitle:     { fontSize: 22, fontWeight: '800', color: Colors.textPrimary },

  errorBanner:     {
    backgroundColor: Colors.elevated,
    borderLeftWidth: 3,
    borderLeftColor: Colors.gold,
    marginHorizontal: 16,
    marginTop: 12,
    padding: 10,
    borderRadius: 8,
  },
  errorBannerText: { fontSize: 12, color: Colors.gold },

  heroCard:        {
    alignItems: 'center',
    paddingVertical: 28,
    paddingHorizontal: 20,
  },
  totalValue:      {
    fontSize: 40,
    fontWeight: '800',
    color: Colors.textPrimary,
    letterSpacing: -1,
  },
  pnlRow:          { marginTop: 6 },
  pnlText:         { fontSize: 15, fontWeight: '600' },

  chartCard:       {
    marginHorizontal: 16,
    backgroundColor: Colors.surface,
    borderRadius: 16,
    padding: 12,
    height: 120,
    overflow: 'hidden',
  },
  chart:           {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 1,
  },
  barWrapper:      { flex: 1, justifyContent: 'flex-end' },
  bar:             { borderRadius: 2, minHeight: 4 },
  chartPlaceholder:{ flex: 1, backgroundColor: Colors.border, borderRadius: 8 },

  pillRow:         {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 14,
    marginHorizontal: 16,
    gap: 6,
  },
  pill:            {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    backgroundColor: Colors.surface,
  },
  pillActive:      { backgroundColor: Colors.textPrimary },
  pillText:        { fontSize: 12, fontWeight: '600', color: Colors.textSecondary },
  pillTextActive:  { color: Colors.bg },

  rowCard:         {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginHorizontal: 16,
    marginTop: 16,
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 16,
  },
  rowLabel:        { fontSize: 14, color: Colors.textSecondary, fontWeight: '600' },
  rowValue:        { fontSize: 15, fontWeight: '700', color: Colors.textPrimary },

  section:         { marginHorizontal: 16, marginTop: 16 },
  sectionTitle:    {
    fontSize: 13,
    fontWeight: '700',
    color: Colors.textSecondary,
    marginBottom: 10,
  },

  holdingCard:     {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
  },
  holdingLeft:     { flex: 1 },
  holdingTicker:   { fontSize: 16, fontWeight: '800', color: Colors.textPrimary },
  holdingMeta:     { fontSize: 12, color: Colors.textMuted, marginTop: 3 },
  holdingRight:    { alignItems: 'flex-end' },
  holdingValue:    { fontSize: 15, fontWeight: '700', color: Colors.textPrimary },
  holdingPnl:      { fontSize: 12, fontWeight: '600', marginTop: 3 },

  emptyText:       { color: Colors.textMuted, fontSize: 14, textAlign: 'center', paddingVertical: 24 },

  // CTA screens
  ctaContainer:    {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 40,
    paddingTop: 80,
  },
  ctaIcon:         { fontSize: 48, marginBottom: 20 },
  ctaTitle:        {
    fontSize: 22,
    fontWeight: '800',
    color: Colors.textPrimary,
    textAlign: 'center',
    marginBottom: 12,
  },
  ctaBody:         {
    fontSize: 14,
    color: Colors.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 28,
  },
  ctaBtn:          {
    backgroundColor: Colors.textPrimary,
    paddingHorizontal: 40,
    paddingVertical: 14,
    borderRadius: 28,
  },
  ctaBtnText:      { fontSize: 16, fontWeight: '700', color: Colors.bg },
});
