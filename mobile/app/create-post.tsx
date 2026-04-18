/**
 * Create Post screen — modal stack screen.
 * Can be pre-filled from stock detail: /create-post?ticker=AAPL&market=US
 */
import { useEffect, useState } from 'react';
import {
  ActivityIndicator, KeyboardAvoidingView, Platform,
  StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Colors } from '../constants/colors';
import { Feed } from '../lib/api';

type SignalType = 'bull' | 'bear' | 'neutral';

const SIGNAL_OPTIONS: { key: SignalType; label: string; color: string }[] = [
  { key: 'bull',    label: '🐂 多方', color: Colors.bull },
  { key: 'bear',    label: '🐻 空方', color: Colors.bear },
  { key: 'neutral', label: '⚖️ 中立', color: Colors.textSecondary },
];

const MAX_CHARS = 280;

export default function CreatePostScreen() {
  const router = useRouter();
  const { ticker: prefilledTicker, market: prefilledMarket } = useLocalSearchParams<{
    ticker?: string; market?: string;
  }>();

  const [ticker,      setTicker]     = useState(prefilledTicker ?? '');
  const [content,     setContent]    = useState('');
  const [signalType,  setSignalType] = useState<SignalType | null>(null);
  const [submitting,  setSubmitting] = useState(false);
  const [error,       setError]      = useState<string | null>(null);

  const market = prefilledMarket ?? 'US';
  const remaining = MAX_CHARS - content.length;

  const handlePost = async () => {
    if (!content.trim()) { setError('請填寫內容'); return; }
    setSubmitting(true); setError(null);
    try {
      await Feed.create(
        content.trim(),
        ticker.trim().toUpperCase() || undefined,
        market || undefined,
        signalType ?? undefined,
      );
      router.back();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? '發文失敗');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.cancelBtn}>
          <Text style={styles.cancelText}>取消</Text>
        </TouchableOpacity>
        <Text style={styles.title}>新增貼文</Text>
        <TouchableOpacity
          style={[styles.postBtn, (submitting || !content.trim()) && styles.disabled]}
          onPress={handlePost}
          disabled={submitting || !content.trim()}
        >
          {submitting ? (
            <ActivityIndicator color={Colors.bg} size="small" />
          ) : (
            <Text style={styles.postBtnText}>發文</Text>
          )}
        </TouchableOpacity>
      </View>

      <View style={styles.body}>
        {/* Optional ticker */}
        <View style={styles.tickerRow}>
          <Text style={styles.label}>股票代號 (選填)</Text>
          <TextInput
            style={styles.tickerInput}
            placeholder="如 AAPL, 2330"
            placeholderTextColor={Colors.textMuted}
            value={ticker}
            onChangeText={t => setTicker(t.toUpperCase())}
            autoCapitalize="characters"
            maxLength={10}
          />
        </View>

        {/* Content */}
        <TextInput
          style={styles.contentInput}
          placeholder="分享你的市場洞察…"
          placeholderTextColor={Colors.textMuted}
          value={content}
          onChangeText={setContent}
          multiline
          maxLength={MAX_CHARS}
          autoFocus
        />
        <Text style={[styles.charCount, remaining < 40 && { color: remaining < 10 ? Colors.bear : Colors.gold }]}>
          {remaining}
        </Text>

        {/* Signal type */}
        <View style={styles.signalRow}>
          {SIGNAL_OPTIONS.map(opt => (
            <TouchableOpacity
              key={opt.key}
              style={[styles.signalPill, signalType === opt.key && { borderColor: opt.color, backgroundColor: opt.color + '22' }]}
              onPress={() => setSignalType(prev => prev === opt.key ? null : opt.key)}
            >
              <Text style={[styles.signalPillText, signalType === opt.key && { color: opt.color }]}>
                {opt.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {error && <Text style={styles.error}>{error}</Text>}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container:     { flex: 1, backgroundColor: Colors.bg },
  header:        { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, paddingTop: 56, backgroundColor: Colors.surface, borderBottomWidth: 1, borderBottomColor: Colors.border },
  cancelBtn:     { padding: 4 },
  cancelText:    { fontSize: 16, color: Colors.textSecondary },
  title:         { fontSize: 16, fontWeight: '700', color: Colors.textPrimary },
  postBtn:       { backgroundColor: Colors.tabActive, borderRadius: 10, paddingHorizontal: 16, paddingVertical: 8 },
  postBtnText:   { fontSize: 14, fontWeight: '700', color: Colors.bg },
  disabled:      { opacity: 0.5 },
  body:          { flex: 1, padding: 16 },
  tickerRow:     { flexDirection: 'row', alignItems: 'center', marginBottom: 16, gap: 12 },
  label:         { fontSize: 13, color: Colors.textSecondary },
  tickerInput:   { flex: 1, backgroundColor: Colors.surface, borderRadius: 10, padding: 10, fontSize: 14, color: Colors.textPrimary, borderWidth: 1, borderColor: Colors.border },
  contentInput:  { backgroundColor: Colors.surface, borderRadius: 12, padding: 14, fontSize: 15, color: Colors.textPrimary, minHeight: 120, textAlignVertical: 'top', borderWidth: 1, borderColor: Colors.border, marginBottom: 8 },
  charCount:     { textAlign: 'right', fontSize: 12, color: Colors.textMuted, marginBottom: 16 },
  signalRow:     { flexDirection: 'row', gap: 10 },
  signalPill:    { flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center', backgroundColor: Colors.surface, borderWidth: 1.5, borderColor: Colors.border },
  signalPillText:{ fontSize: 13, fontWeight: '600', color: Colors.textSecondary },
  error:         { color: Colors.bear, fontSize: 13, marginTop: 12, textAlign: 'center' },
});
