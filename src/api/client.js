import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api/v1';

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Добавление Bearer токена из localStorage к каждому запросу
api.interceptors.request.use((config) => {
  try {
    const rawData = localStorage.getItem('user-merts-chat');
    if (rawData) {
      const parsed = JSON.parse(rawData);
      const token = parsed?.state?.accessToken || parsed?.state?.userInfo?.accessToken;
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
  } catch (err) {
    console.error('Failed to parse user session for api client', err);
  }
  return config;
});

// Автоматическая попытка обновления токена при 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry && !originalRequest.url?.includes('/auth/login') && !originalRequest.url?.includes('/auth/refresh')) {
      originalRequest._retry = true;
      try {
        const refreshRes = await axios.post(
          `${API_BASE_URL}/auth/refresh`,
          {},
          { withCredentials: true }
        );
        const newAccessToken = refreshRes.data?.accessToken;
        if (newAccessToken) {
          const rawData = localStorage.getItem('user-merts-chat');
          if (rawData) {
            const parsed = JSON.parse(rawData);
            if (parsed.state) {
              parsed.state.accessToken = newAccessToken;
              if (parsed.state.userInfo) {
                parsed.state.userInfo.accessToken = newAccessToken;
              }
              localStorage.setItem('user-merts-chat', JSON.stringify(parsed));
            }
          }
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
          return api(originalRequest);
        }
      } catch (refreshErr) {
        // Если refresh не удался — перенаправление на логин
        console.warn('Session expired, please re-login');
      }
    }
    return Promise.reject(error);
  }
);
