import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ConfigProvider } from "./contexts/ConfigContext";
import { PDFProvider } from "./contexts/PDFContext";

// Importing the Bootstrap CSS
import "bootstrap/dist/css/bootstrap.min.css";
import "bootstrap-icons/font/bootstrap-icons.css";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <ConfigProvider>
      <PDFProvider>
        <App />
      </PDFProvider>
    </ConfigProvider>
  </React.StrictMode>
);