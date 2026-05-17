/**
 * Zustand auth store — manages JWT token, user info, and OAuth flows.
 *
 * Keys in AsyncStorage:
 *   oracle_auth_token  → JWT string
 *   oracle_user        → JSON-serialised user object
 */
import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Auth } from '../lib/api';
import { getOrCreateDeviceId } from '../lib/device';

export interface AuthUser {
  id:            number;
  display_name:  string;
  email:         string | null;
  coins:         number;
  avatar_url:    string | null;
  auth_provider: string | null;
}

interface AuthState {
  token:  string | null;
  user:   AuthUser | null;

  hydrateFromStorage:  () => Promise<void>;
  loginWithApple:      (identityToken: string, fullName?: string) => Promise<void>;
  loginWithGoogle:     (idToken: string) => Promise<void>;
  loginWithDevice:     () => Promise<void>;
  loginWithEmail:      (email: string, password: string) => Promise<void>;
  registerWithEmail:   (email: string, password: string, displayName?: string) => Promise<void>;
  updateUser:          (patch: Partial<AuthUser>) => void;
  logout:              () => Promise<void>;
}

const TOKEN_KEY = 'oracle_auth_token';
const USER_KEY  = 'oracle_user';

async function _persist(token: string, user: AuthUser) {
  await AsyncStorage.multiSet([
    [TOKEN_KEY, token],
    [USER_KEY,  JSON.stringify(user)],
  ]);
}

async function _clear() {
  await AsyncStorage.multiRemove([TOKEN_KEY, USER_KEY]);
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  user:  null,

  hydrateFromStorage: async () => {
    try {
      const [[, token], [, userJson]] = await AsyncStorage.multiGet([TOKEN_KEY, USER_KEY]);
      if (token && userJson) {
        set({ token, user: JSON.parse(userJson) });
      }
    } catch {
      // Ignore — will require re-login
    }
  },

  loginWithApple: async (identityToken, fullName) => {
    const res = await Auth.apple(identityToken, fullName);
    await _persist(res.access_token, res.user);
    set({ token: res.access_token, user: res.user });
  },

  loginWithGoogle: async (idToken) => {
    const res = await Auth.google(idToken);
    await _persist(res.access_token, res.user);
    set({ token: res.access_token, user: res.user });
  },

  loginWithDevice: async () => {
    const deviceId = await getOrCreateDeviceId();
    const res = await Auth.device(deviceId);
    await _persist(res.access_token, res.user);
    set({ token: res.access_token, user: res.user });
  },

  loginWithEmail: async (email, password) => {
    const res = await Auth.login(email, password);
    await _persist(res.access_token, res.user);
    set({ token: res.access_token, user: res.user });
  },

  registerWithEmail: async (email, password, displayName) => {
    const res = await Auth.register(email, password, displayName);
    await _persist(res.access_token, res.user);
    set({ token: res.access_token, user: res.user });
  },

  updateUser: (patch) => {
    const user = get().user;
    if (!user) return;
    const updated = { ...user, ...patch };
    set({ user: updated });
    AsyncStorage.setItem(USER_KEY, JSON.stringify(updated)).catch(() => {});
  },

  logout: async () => {
    await _clear();
    set({ token: null, user: null });
  },
}));
