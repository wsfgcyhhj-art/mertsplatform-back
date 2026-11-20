import { create } from 'zustand';
import { setAccessToken } from '../api/authToken.js';
export const useFindUser = create(set => ({
  userInfo: null,
  accessToken: null,
  addUser: (user, token) => {
    if (token) setAccessToken(token);
    set((state) => ({ userInfo: user, accessToken: token ?? state.accessToken }));
  },
  removeUser: () => { setAccessToken(null); set({userInfo: null, accessToken: null}); },
}));
