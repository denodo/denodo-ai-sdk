import React from "react";
import ReactDOM from "react-dom/client";

// Importing the Bootstrap CSS before App so component styles take precedence
import "bootstrap/dist/css/bootstrap.min.css";
import "bootstrap-icons/font/bootstrap-icons.css";
import "./index.css";

import App from "./App";
import { ConfigProvider } from "./contexts/ConfigContext";
import { ReportProvider } from "./contexts/ReportContext";

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