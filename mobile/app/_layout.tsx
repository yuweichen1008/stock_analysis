import { useEffect, useRef } from 'react';
import { Stack } from 'expo-router';
import * as Notifications from 'expo-notifications';
import { getOrCreateDeviceId } from '../lib/device';
import { registerForPushNotifications } from '../lib/notifications';
import { Sandbox, Notify } from '../lib/api';

export default function RootLayout() {
  const notifListener = useRef<Notifications.EventSubscription | null>(null);
  const responseListener = useRef<Notifications.EventSubscription | null>(null);

  useEffect(() => {
    async function init() {
      try {
        const deviceId = await getOrCreateDeviceId();

        // Register device (idempotent)
        await Sandbox.register(deviceId);

        // Push notification setup
        const token = await registerForPushNotifications();
        if (token) {
          await Notify.register(deviceId, token);
        }
      } catch (e) {
        console.warn('[Init] Setup error (non-fatal):', e);
      }
    }

    init();

    // Notification listeners
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
  }, []);

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
    </Stack>
  );
}
