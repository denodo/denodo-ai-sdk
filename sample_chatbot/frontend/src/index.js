import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ConfigProvider } from "./contexts/ConfigContext";
import { ReportProvider } from "./contexts/ReportContext";

// Importing the Bootstrap CSS
import "bootstrap/dist/css/bootstrap.min.css";
import "bootstrap-icons/font/bootstrap-icons.css";
import "./index.css";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <ConfigProvider>
      <ReportProvider>
        <App />
      </ReportProvider>
    </ConfigProvider>
  </React.StrictMode>
);