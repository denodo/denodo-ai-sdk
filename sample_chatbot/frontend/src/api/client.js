import axios from "axios";

export const buildApiUrl = (path = "") => {
  const normalizedPath = path.replace(/^\/+/, "");
  return `api/${normalizedPath}`;
};

const api = axios.create({
  baseURL: "api",
});

export const AUTH_EXPIRED_EVENT = "chatbot:auth-expired";

// An expired/invalid session answers 401 on any API call except the login itself:
// tell the app so it can go back to the login screen and stop background polling.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error?.config?.url || "";
    if (error?.response?.status === 401 && !/^\/?login\/?$/.test(url)) {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    return Promise.reject(error);
  }
);

export default api;
