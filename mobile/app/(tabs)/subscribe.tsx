import { useState } from 'react';
import {
  ActivityIndicator, Linking, ScrollView,
  StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { Colors } from '../../constants/colors';
import { API_BASE } from '../../lib/api';
import axios from 'axios';

export default function SubscribeScreen() {
  const [telegramId, setTelegramId] = useState('');
  const [label, setLabel]           = useState('');
  const [loading, setLoading]       = useState(false);
  const [msg, setMsg]               = useState<{ text: string; ok: boolean } | null>(null);

  const doSubscribe = async () => {
    const tid = telegramId.trim();
    if (!tid) { setMsg({ text: '請輸入 Telegram Chat ID', ok: false }); return; }
    setLoading(true);
    setMsg(null);
    try {
      await axios.post(`${API_BASE}/api/subscribe`, {
        telegram_id: tid,
        label: label.trim() || undefined,
      });
      setMsg({ text: '✅ 訂閱成功！請查看你的 Telegram。', ok: true });
    } catch (e: any) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail ?? '訂閱失敗';
      if (status === 409) {
        setMsg({ text: 'ℹ️ 此 Chat ID 已訂閱。', ok: true });
      } else {
        setMsg({ text: `❌ ${detail}`, ok: false });
      }
    } finally {
      setLoading(false);
    }
  };

  const doUnsubscribe = async () => {
    const tid = telegramId.trim();
    if (!tid) { setMsg({ text: '請輸入 Telegram Chat ID', ok: false }); return; }
    setLoading(true);
    setMsg(null);
    try {
      await axios.delete(`${API_BASE}/api/subscribe/${encodeURIComponent(tid)}`);
      setMsg({ text: '已取消訂閱。', ok: true });
    } catch {
      setMsg({ text: '❌ 找不到此訂閱。', ok: false });
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text style={styles.title}>🔔 通知訂閱</Text>
        <Text style={styles.sub}>透過 Telegram 接收每日 Oracle 預測</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>Telegram Chat ID</Text>
        <TextInput
          style={styles.input}
          value={telegramId}
          onChangeText={setTelegramId}
          placeholder="例：123456789"
          placeholderTextColor={Colors.textMuted}
          keyboardType="numeric"
          autoCapitalize="none"
        />
        <Text style={styles.hint}>
          不知道你的 Chat ID？
          <Text
            style={styles.link}
            onPress={() => Linking.openURL('https://t.me/userinfobot')}
          >
            {' '}開啟 @userinfobot
          </Text>
        </Text>

        <Text style={styles.label}>顯示名稱（選填）</Text>
        <TextInput
          style={[styles.input, { marginBottom: 20 }]}
          value={label}
          onChangeText={setLabel}
          placeholder="例：Sami"
          placeholderTextColor={Colors.textMuted}
          autoCapitalize="words"
        />

        {msg && (
          <View style={[styles.msgBox, msg.ok ? styles.msgOk : styles.msgErr]}>
            <Text style={[styles.msgText, { color: msg.ok ? Colors.bull : Colors.bear }]}>
              {msg.text}
            </Text>
          </View>
        )}

        <TouchableOpacity
          style={[styles.btn, styles.btnPrimary, loading && styles.disabled]}
          onPress={doSubscribe}
          disabled={loading}
        >
          {loading
            ? <ActivityIndicator color="#fff" size="small" />
            : <Text style={styles.btnText}>📬 訂閱</Text>
          }
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, styles.btnSecondary, loading && styles.disabled]}
          onPress={doUnsubscribe}
          disabled={loading}
        >
          <Text style={[styles.btnText, { color: Colors.textSecondary }]}>🔕 取消訂閱</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.infoCard}>
        <Text style={styles.infoTitle}>📅 每日通知時程</Text>
        <InfoRow time="08:00 TST" desc="🔮 今日多空預測 + 信心指數" />
        <InfoRow time="14:05 TST" desc="📊 結算 + 大盤變動 + 積分" />
      </View>
    </ScrollView>
  );
}

function InfoRow({ time, desc }: { time: string; desc: string }) {
  return (
    <View style={infoStyles.row}>
      <Text style={infoStyles.time}>{time}</Text>
      <Text style={infoStyles.desc}>{desc}</Text>
    </View>
  );
}

const infoStyles = StyleSheet.create({
  row:  { flexDirection: 'row', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: Colors.border },
  time: { width: 90, fontSize: 12, color: Colors.gold, fontWeight: '600' },
  desc: { flex: 1, fontSize: 13, color: Colors.textSecondary },
});

const styles = StyleSheet.create({
  container:  { flex: 1, backgroundColor: Colors.bg },
  content:    { padding: 16, paddingBottom: 40 },
  header:     { marginTop: 12, marginBottom: 20 },
  title:      { fontSize: 26, fontWeight: '800', color: Colors.textPrimary },
  sub:        { fontSize: 13, color: Colors.textSecondary, marginTop: 4 },
  card:       { backgroundColor: Colors.surface, borderRadius: 16, padding: 18, marginBottom: 14 },
  label:      { fontSize: 11, color: Colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 },
  input:      {
    backgroundColor: Colors.elevated, borderWidth: 1, borderColor: Colors.border,
    borderRadius: 10, color: Colors.textPrimary, fontSize: 15,
    paddingHorizontal: 14, paddingVertical: 12, marginBottom: 8,
  },
  hint:       { fontSize: 12, color: Colors.textMuted, marginBottom: 18, lineHeight: 18 },
  link:       { color: Colors.blue },
  msgBox:     { borderRadius: 10, padding: 12, marginBottom: 14, borderWidth: 1 },
  msgOk:      { backgroundColor: Colors.bullDim, borderColor: Colors.bull },
  msgErr:     { backgroundColor: Colors.bearDim, borderColor: Colors.bear },
  msgText:    { fontSize: 13, fontWeight: '600' },
  btn:        { borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginBottom: 10 },
  btnPrimary: { backgroundColor: Colors.blue },
  btnSecondary:{ backgroundColor: Colors.elevated, borderWidth: 1, borderColor: Colors.border },
  btnText:    { fontSize: 15, fontWeight: '700', color: Colors.textPrimary },
  disabled:   { opacity: 0.5 },
  infoCard:   { backgroundColor: Colors.surface, borderRadius: 16, padding: 18 },
  infoTitle:  { fontSize: 14, fontWeight: '700', color: Colors.textPrimary, marginBottom: 12 },
});
