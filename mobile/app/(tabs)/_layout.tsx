import { Tabs } from 'expo-router';
import { Colors } from '../../constants/colors';

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
        options={{ title: '預測', tabBarIcon: ({ color }) => <TabIcon label="🔮" color={color} /> }}
      />
      <Tabs.Screen
        name="bet"
        options={{ title: '下注', tabBarIcon: ({ color }) => <TabIcon label="🎯" color={color} /> }}
      />
      <Tabs.Screen
        name="history"
        options={{ title: '紀錄', tabBarIcon: ({ color }) => <TabIcon label="📅" color={color} /> }}
      />
      <Tabs.Screen
        name="leaderboard"
        options={{ title: '排行', tabBarIcon: ({ color }) => <TabIcon label="🏆" color={color} /> }}
      />
      <Tabs.Screen
        name="market"
        options={{ title: '訊號', tabBarIcon: ({ color }) => <TabIcon label="📊" color={color} /> }}
      />
      <Tabs.Screen
        name="subscribe"
        options={{ title: '通知', tabBarIcon: ({ color }) => <TabIcon label="🔔" color={color} /> }}
      />
    </Tabs>
  );
}

function TabIcon({ label, color }: { label: string; color: string }) {
  const { Text } = require('react-native');
  return <Text style={{ fontSize: 20, opacity: color === Colors.tabActive ? 1 : 0.5 }}>{label}</Text>;
}
