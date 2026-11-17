import { getAccessToken, setAccessToken } from './authToken.js';
import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

export function resolveMediaUrl(rawUrl, fallbackPath = null) {
  const val = String(rawUrl || '').trim();
  if (!val) {
    return fallbackPath ? resolveMediaUrl(fallbackPath, null) : null;
  }
  if (val.startsWith('data:image/') || val.startsWith('http://') || val.startsWith('https://')) {
    return val;
  }
  if (val.startsWith('/api/v1/')) {
    return val;
  }
  if (val.startsWith('/')) {
    return `/api/v1${val}`;
  }
  return val;
}

export const extractAuthToken = getAccessToken;
let csrfToken = null;
let refreshPromise = null;
async function csrf() {
  if (!csrfToken) csrfToken = (await axios.get(`${API_BASE_URL}/auth/csrf`, {withCredentials: true})).data.csrfToken;
  return csrfToken;
}
export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Добавление Bearer токена к каждому запросу
api.interceptors.request.use(async (config) => {
  if (!["get", "head", "options"].includes(config.method)) config.headers["X-CSRFToken"] = await csrf();
  const token = extractAuthToken();
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Автоматическая попытка обновления токена при 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/login') &&
      !originalRequest.url?.includes('/auth/refresh') &&
      !originalRequest.url?.includes('/auth/logout')
    ) {
      originalRequest._retry = true;
      try {
        if (!refreshPromise) {
          refreshPromise = csrf().then(value => axios.post(`${API_BASE_URL}/auth/refresh`, {}, {withCredentials: true, headers: {'X-CSRFToken': value}})).finally(() => { refreshPromise = null; });
        }
        const refreshRes = await refreshPromise;
        const newAccessToken = refreshRes.data?.accessToken;
        if (newAccessToken) {
          setAccessToken(newAccessToken);
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
          return api(originalRequest);
        }
      } catch {
        console.warn('Session expired, please re-login');
      }
    }
    return Promise.reject(error);
  }
);
