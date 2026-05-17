/**
 * Sign-in screen — shown when no auth token exists.
 * Apple Sign-In is required by App Store guidelines for apps using social login.
 */
import { useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Colors } from '../constants/colors';
import { useAuthStore } from '../store/auth';

export default function AuthScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState<string | null>(null);
  const [error,   setError]   = useState<string | null>(null);

  // Email form state
  const [mode,        setMode]        = useState<'signin' | 'register'>('signin');
  const [displayName, setDisplayName] = useState('');
  const [email,       setEmail]       = useState('');
  const [password,    setPassword]    = useState('');

  const emailRef    = useRef<TextInput>(null);
  const passwordRef = useRef<TextInput>(null);

  const { loginWithApple, loginWithGoogle, loginWithDevice, loginWithEmail, registerWithEmail } = useAuthStore();

  const handle = async (provider: string, fn: () => Promise<void>) => {
    setLoading(provider);
    setError(null);
    try {
      await fn();
      router.replace('/(tabs)');
    } catch (e: any) {
      const msg: string = e?.response?.data?.detail ?? e?.message ?? '登入失敗，請再試一次';
      setError(msg);
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
      await import('expo-auth-session/providers/google');
      // Google OAuth requires an Expo project configured with clientId in app.json
      throw new Error('Configure GOOGLE_CLIENT_ID in app.json extra.googleClientId');
    });

  const handleAnonymous = () =>
    handle('device', () => loginWithDevice());

  const handleEmailSubmit = () => {
    if (mode === 'signin') {
      handle('email', () => loginWithEmail(email.trim(), password));
    } else {
      handle('email', () =>
        registerWithEmail(email.trim(), password, displayName.trim() || undefined),
      );
    }
  };

  const isLoading = !!loading;

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
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
              disabled={isLoading}
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
            disabled={isLoading}
            activeOpacity={0.85}
          >
            {loading === 'google' ? (
              <ActivityIndicator color={Colors.textPrimary} />
            ) : (
              <Text style={styles.googleBtnText}>G  Continue with Google</Text>
            )}
          </TouchableOpacity>

          {/* ── Email section ── */}
          <Text style={styles.divider}>──────── or continue with email ────────</Text>

          {mode === 'register' && (
            <TextInput
              style={styles.input}
              placeholder="Display name (optional)"
              placeholderTextColor={Colors.textMuted}
              value={displayName}
              onChangeText={setDisplayName}
              autoCapitalize="words"
              returnKeyType="next"
              onSubmitEditing={() => emailRef.current?.focus()}
              editable={!isLoading}
            />
          )}

          <TextInput
            ref={emailRef}
            style={styles.input}
            placeholder="Email"
            placeholderTextColor={Colors.textMuted}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            returnKeyType="next"
            onSubmitEditing={() => passwordRef.current?.focus()}
            editable={!isLoading}
          />

          <TextInput
            ref={passwordRef}
            style={styles.input}
            placeholder="Password"
            placeholderTextColor={Colors.textMuted}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            returnKeyType="go"
            onSubmitEditing={handleEmailSubmit}
            editable={!isLoading}
          />

          <TouchableOpacity
            style={[styles.emailBtn, isLoading && styles.emailBtnDisabled]}
            onPress={handleEmailSubmit}
            disabled={isLoading}
            activeOpacity={0.85}
          >
            {loading === 'email' ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.emailBtnText}>
                {mode === 'signin' ? 'Sign In' : 'Create Account'}
              </Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => {
              setMode(m => (m === 'signin' ? 'register' : 'signin'));
              setError(null);
            }}
            disabled={isLoading}
            style={styles.toggleBtn}
          >
            <Text style={styles.toggleText}>
              {mode === 'signin'
                ? "Don't have an account? Register"
                : 'Already have one? Sign In'}
            </Text>
          </TouchableOpacity>

          {/* Anonymous fallback */}
          <TouchableOpacity
            onPress={handleAnonymous}
            disabled={isLoading}
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
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex:             { flex: 1, backgroundColor: Colors.bg },
  container:        { flexGrow: 1, justifyContent: 'space-between', padding: 32 },
  hero:             { flex: 1, justifyContent: 'center', alignItems: 'center', paddingVertical: 32 },
  logo:             { fontSize: 72, marginBottom: 12 },
  title:            { fontSize: 40, fontWeight: '900', color: Colors.textPrimary },
  subtitle:         { fontSize: 16, color: Colors.textSecondary, marginTop: 6 },
  buttons:          { gap: 12, marginBottom: 24 },
  errorBox:         { backgroundColor: Colors.bearDim, borderRadius: 10, padding: 12, marginBottom: 4 },
  errorText:        { color: Colors.bear, fontSize: 13, textAlign: 'center' },
  appleBtn:         {
    backgroundColor: '#000',
    borderRadius: 12,
    height: 52,
    justifyContent: 'center',
    alignItems: 'center',
  },
  appleBtnText:     { color: '#fff', fontSize: 16, fontWeight: '600' },
  googleBtn:        {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    height: 52,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  googleBtnText:    { color: Colors.textPrimary, fontSize: 15, fontWeight: '600' },
  divider:          { color: '#555570', textAlign: 'center', marginVertical: 16, fontSize: 13 },
  input:            {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 12,
    padding: 14,
    color: Colors.textPrimary,
    fontSize: 15,
  },
  emailBtn:         {
    backgroundColor: '#7c5cfc',
    borderRadius: 12,
    padding: 14,
    alignItems: 'center',
  },
  emailBtnDisabled: { opacity: 0.6 },
  emailBtnText:     { color: '#ffffff', fontSize: 16, fontWeight: '600' },
  toggleBtn:        { alignItems: 'center', paddingVertical: 4 },
  toggleText:       { color: Colors.blue, fontSize: 13 },
  anonBtn:          { alignItems: 'center', paddingVertical: 14 },
  anonText:         { color: Colors.textMuted, fontSize: 14 },
  legal:            { textAlign: 'center', fontSize: 11, color: Colors.textMuted, marginBottom: 8 },
});
