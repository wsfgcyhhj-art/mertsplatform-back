import { create } from 'zustand';
import { setAccessToken } from '../api/authToken.js';
export const useFindUser = create(set => ({
  userInfo: null,
  accessToken: null,
  addUser: (user, token = null) => {
    if (token) setAccessToken(token);
    set({userInfo: user, accessToken: token});
  },
  removeUser: () => { setAccessToken(null); set({userInfo: null, accessToken: null}); },
}));
