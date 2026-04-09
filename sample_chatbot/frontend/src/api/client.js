import axios from "axios";

export const buildApiUrl = (path = "") => {
  const normalizedPath = path.replace(/^\/+/, "");
  return `api/${normalizedPath}`;
};

const api = axios.create({
  baseURL: "api",
});

export default api;
