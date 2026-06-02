import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;
export const ASSET_BASE = BACKEND_URL;

const api = axios.create({
  baseURL: API_BASE,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("elite_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401) {
      // Soft logout
      if (window.location.pathname !== "/login" && window.location.pathname !== "/signup" && window.location.pathname !== "/") {
        localStorage.removeItem("elite_token");
        localStorage.removeItem("elite_user");
      }
    }
    return Promise.reject(err);
  }
);

export default api;
