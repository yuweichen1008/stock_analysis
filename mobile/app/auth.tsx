/**
 * Sign-in screen — shown when no auth token exists.
 * Apple Sign-In is required by App Store guidelines for apps using social login.
 */
import { useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Colors } from '../constants/colors';
import { useAuthStore } from '../store/auth';

export default function AuthScreen() {
  const [loading, setLoading] = useState<string | null>(null);
  const [error,   setError]   = useState<string | null>(null);
  const { loginWithApple, loginWithGoogle, loginWithDevice } = useAuthStore();

  const handle = async (provider: string, fn: () => Promise<void>) => {
    setLoading(provider);
    setError(null);
    try {
      await fn();
      // Navigation handled by _layout.tsx token watch
    } catch (e: any) {
      setError(e?.message ?? '登入失敗，請再試一次');
    } finally {
      setLoading(null);
    }
  };

  const handleApple = async () => {
    if (Platform.OS !== 'ios') {
      setError('Apple Sign-In 僅支援 iOS 裝置');
      return;
    }
    handle('apple', async () => {
      // Lazy import — requires native module
      const AppleAuth = await import('expo-apple-authentication');
      const cred = await AppleAuth.signInAsync({
        requestedScopes: [
          AppleAuth.AppleAuthenticationScope.FULL_NAME,
          AppleAuth.AppleAuthenticationScope.EMAIL,
        ],
      });
      const fullName = cred.fullName
        ? [cred.fullName.givenName, cred.fullName.familyName].filter(Boolean).join(' ')
        : undefined;
      await loginWithApple(cred.identityToken!, fullName);
    });
  };

  const handleGoogle = () =>
    handle('google', async () => {
      const { makeRedirectUri, useAuthRequest } = await import('expo-auth-session/providers/google');
      // Google OAuth requires an Expo project configured with clientId in app.json
      throw new Error('Configure GOOGLE_CLIENT_ID in app.json extra.googleClientId');
    });

  const handleAnonymous = () =>
    handle('device', () => loginWithDevice());

  return (
    <View style={styles.container}>
      <View style={styles.hero}>
        <Text style={styles.logo}>🔮</Text>
        <Text style={styles.title}>Oracle</Text>
        <Text style={styles.subtitle}>專業選股分析平台</Text>
      </View>

      <View style={styles.buttons}>
        {error && (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {/* Apple Sign-In — required on iOS */}
        {Platform.OS === 'ios' && (
          <TouchableOpacity
            style={styles.appleBtn}
            onPress={handleApple}
            disabled={!!loading}
            activeOpacity={0.85}
          >
            {loading === 'apple' ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.appleBtnText}> Sign in with Apple</Text>
            )}
          </TouchableOpacity>
        )}

        {/* Google */}
        <TouchableOpacity
          style={styles.googleBtn}
          onPress={handleGoogle}
          disabled={!!loading}
          activeOpacity={0.85}
        >
          {loading === 'google' ? (
            <ActivityIndicator color={Colors.textPrimary} />
          ) : (
            <Text style={styles.googleBtnText}>G  Continue with Google</Text>
          )}
        </TouchableOpacity>

        {/* Anonymous fallback */}
        <TouchableOpacity
          onPress={handleAnonymous}
          disabled={!!loading}
          style={styles.anonBtn}
        >
          {loading === 'device' ? (
            <ActivityIndicator color={Colors.textMuted} size="small" />
          ) : (
            <Text style={styles.anonText}>以訪客身份繼續</Text>
          )}
        </TouchableOpacity>
      </View>

      <Text style={styles.legal}>
        繼續即表示同意服務條款與隱私政策
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: Colors.bg, justifyContent: 'space-between', padding: 32 },
  hero:         { flex: 1, justifyContent: 'center', alignItems: 'center' },
  logo:         { fontSize: 72, marginBottom: 12 },
  title:        { fontSize: 40, fontWeight: '900', color: Colors.textPrimary },
  subtitle:     { fontSize: 16, color: Colors.textSecondary, marginTop: 6 },
  buttons:      { gap: 12, marginBottom: 24 },
  errorBox:     { backgroundColor: Colors.bearDim, borderRadius: 10, padding: 12, marginBottom: 4 },
  errorText:    { color: Colors.bear, fontSize: 13, textAlign: 'center' },
  appleBtn:     {
    backgroundColor: '#000',
    borderRadius: 12,
    height: 52,
    justifyContent: 'center',
    alignItems: 'center',
  },
  appleBtnText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  googleBtn:    {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    height: 52,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  googleBtnText:{ color: Colors.textPrimary, fontSize: 15, fontWeight: '600' },
  anonBtn:      { alignItems: 'center', paddingVertical: 14 },
  anonText:     { color: Colors.textMuted, fontSize: 14 },
  legal:        { textAlign: 'center', fontSize: 11, color: Colors.textMuted, marginBottom: 8 },
});
