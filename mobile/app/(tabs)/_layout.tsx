import { Tabs } from 'expo-router';
import { Colors } from '../../constants/colors';
import { Text } from 'react-native';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: Colors.surface,
          borderTopColor: Colors.border,
          borderTopWidth: 1,
          height: 60,
          paddingBottom: 8,
          paddingTop: 6,
        },
        tabBarActiveTintColor:   Colors.tabActive,
        tabBarInactiveTintColor: Colors.tabInactive,
        tabBarLabelStyle: { fontSize: 10, fontWeight: '600' },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: '訊號', tabBarIcon: ({ color }) => <TabIcon label="📊" color={color} /> }}
      />
      <Tabs.Screen
        name="oracle"
        options={{ title: 'Oracle', tabBarIcon: ({ color }) => <TabIcon label="🔮" color={color} /> }}
      />
      <Tabs.Screen
        name="news"
        options={{ title: '新聞', tabBarIcon: ({ color }) => <TabIcon label="📰" color={color} /> }}
      />
      <Tabs.Screen
        name="community"
        options={{ title: '社群', tabBarIcon: ({ color }) => <TabIcon label="👥" color={color} /> }}
      />
      <Tabs.Screen
        name="watchlist"
        options={{ title: '自選股', tabBarIcon: ({ color }) => <TabIcon label="⭐" color={color} /> }}
      />
      <Tabs.Screen
        name="portfolio"
        options={{ title: '持倉', tabBarIcon: ({ color }) => <TabIcon label="💼" color={color} /> }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: '我的', tabBarIcon: ({ color }) => <TabIcon label="👤" color={color} /> }}
      />
    </Tabs>
  );
}

function TabIcon({ label, color }: { label: string; color: string }) {
  return (
    <Text style={{ fontSize: 20, opacity: color === Colors.tabActive ? 1 : 0.5 }}>
      {label}
    </Text>
  );
}
