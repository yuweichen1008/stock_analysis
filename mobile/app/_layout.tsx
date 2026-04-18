import { useEffect, useRef } from 'react';
import { Stack, useRouter, useSegments } from 'expo-router';
import * as Notifications from 'expo-notifications';
import { useAuthStore } from '../store/auth';
import { useWatchlistStore } from '../store/watchlist';
import { Notify } from '../lib/api';
import { registerForPushNotifications } from '../lib/notifications';

export default function RootLayout() {
  const { token, user, hydrateFromStorage } = useAuthStore();
  const { load: loadWatchlist }             = useWatchlistStore();
  const router   = useRouter();
  const segments = useSegments();
  const notifListener  = useRef<Notifications.EventSubscription | null>(null);
  const responseListener = useRef<Notifications.EventSubscription | null>(null);

  // Hydrate token from AsyncStorage on first mount
  useEffect(() => {
    hydrateFromStorage();
  }, []);

  // Navigate to auth when token disappears, or away from auth when token arrives
  useEffect(() => {
    const inAuthGroup = segments[0] === 'auth';
    if (!token && !inAuthGroup) {
      router.replace('/auth');
    } else if (token && inAuthGroup) {
      router.replace('/(tabs)');
    }
  }, [token, segments]);

  // After successful auth: load watchlist + register push token
  useEffect(() => {
    if (!token || !user) return;

    loadWatchlist();

    async function setupPush() {
      try {
        const pushToken = await registerForPushNotifications();
        if (pushToken && user?.id) {
          // Register push token — falls back gracefully if endpoint not ready
          await Notify.register(user.id.toString(), pushToken).catch(() => {});
        }
      } catch {
        // non-fatal
      }
    }
    setupPush();

    notifListener.current = Notifications.addNotificationReceivedListener(n => {
      console.log('[Notification received]', n.request.content.title);
    });
    responseListener.current = Notifications.addNotificationResponseReceivedListener(r => {
      console.log('[Notification tapped]', r.notification.request.content.data);
    });

    return () => {
      notifListener.current?.remove();
      responseListener.current?.remove();
    };
  }, [token]);

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="(tabs)"          options={{ headerShown: false }} />
      <Stack.Screen name="auth"            options={{ headerShown: false }} />
      <Stack.Screen name="stock/[ticker]"  options={{ headerShown: false, presentation: 'card' }} />
      <Stack.Screen name="create-post"     options={{ headerShown: false, presentation: 'modal' }} />
    </Stack>
  );
}
