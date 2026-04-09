import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';

const KEY = 'oracle_device_id';

export async function getOrCreateDeviceId(): Promise<string> {
  let id = await AsyncStorage.getItem(KEY);
  if (!id) {
    id = Crypto.randomUUID();
    await AsyncStorage.setItem(KEY, id);
  }
  return id;
}
