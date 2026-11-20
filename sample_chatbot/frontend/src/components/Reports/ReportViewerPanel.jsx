import React, { useCallback, useEffect, useRef, useState } from "react";
import PropTypes from "prop-types";
import Button from "react-bootstrap/Button";
import Dropdown from "react-bootstrap/Dropdown";
import Spinner from "react-bootstrap/Spinner";
import Alert from "react-bootstrap/Alert";
import { useReport } from "../../contexts/ReportContext";
import { downloadHtmlFile } from "../../utils/reportFiles";
import ReportPanelShell from "./ReportPanelShell";

// Themes defined by the generated report (html[data-theme="..."] CSS variable blocks)
export const REPORT_THEMES = [
  { id: "red", label: "Red", color: "#c53030" },
  { id: "blue", label: "Blue", color: "#3182ce" },
  { id: "green", label: "Green", color: "#38a169" },
  { id: "black", label: "Black", color: "#2d3748" },
  { id: "dark", label: "Dark", color: "#121826" },
  { id: "light", label: "Light", color: "#ffffff" },
];

const DEFAULT_THEME = "red";

// The app's Content-Security-Policy (style-src 'self') is inherited by the srcdoc iframe and blocks
// the report's inline <style> tags, which left reports unstyled. The CSS is taken out of the HTML
// and applied to the iframe through a constructable stylesheet, which the policy does not restrict.
const splitReportStyles = (html) => {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const styles = Array.from(doc.querySelectorAll("style"));
  const css = styles.map((style) => style.textContent).join("\n");
  styles.forEach((style) => style.remove());
  return { css, frameHtml: `<!DOCTYPE html>\n${doc.documentElement.outerHTML}` };
};

const withTheme = (html, themeId) => {
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.documentElement.setAttribute("data-theme", themeId);
  return `<!DOCTYPE html>\n${doc.documentElement.outerHTML}`;
};

const ReportViewerPanel = ({ report, onBack, onBackToList }) => {
  const { fetchHtml } = useReport();
  const iframeRef = useRef(null);
  const themeRef = useRef(DEFAULT_THEME);
  const [state, setState] = useState({ loading: true, error: null, html: null, frameHtml: null, css: "", title: "" });
  const [theme, setTheme] = useState(DEFAULT_THEME);
  // The iframe stays hidden until styles and theme are applied, avoiding a flash of unstyled content
  const [frameReady, setFrameReady] = useState(false);

  const reportId = report?.id;

  useEffect(() => {
    if (!reportId) return undefined;
    let cancelled = false;
    setState({ loading: true, error: null, html: null, frameHtml: null, css: "", title: report?.title || "" });
    setTheme(DEFAULT_THEME);
    setFrameReady(false);
    themeRef.current = DEFAULT_THEME;
    fetchHtml(reportId)
      .then((data) => {
        if (!cancelled) {
          const { css, frameHtml } = splitReportStyles(data.html_report);
          setState({
            loading: false,
            error: null,
            html: data.html_report,
            frameHtml,
            css,
            title: data.title || report?.title || "",
          });
        }
      })
      .catch((error) => {
        if (cancelled) return;
        const message = error?.response?.data?.error || error?.message || "The report could not be loaded.";
        setState({ loading: false, error: message, html: null, frameHtml: null, css: "", title: report?.title || "" });
      });
    return () => {
      cancelled = true;
    };
  }, [reportId, fetchHtml]); // eslint-disable-line react-hooks/exhaustive-deps

  // Applying a theme only flips data-theme on the iframe's <html>: the report CSS reacts instantly
  const applyTheme = useCallback((themeId) => {
    const doc = iframeRef.current?.contentDocument;
    if (doc?.documentElement) doc.documentElement.setAttribute("data-theme", themeId);
  }, []);

  const handleThemeChange = (themeId) => {
    themeRef.current = themeId;
    setTheme(themeId);
    applyTheme(themeId);
  };

  // On (re)load keep the chosen theme; the first load adopts the theme the report was generated with
  const handleIframeLoad = () => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc?.documentElement) {
      setFrameReady(true);
      return;
    }
    const FrameStyleSheet = doc.defaultView?.CSSStyleSheet;
    if (state.css && FrameStyleSheet) {
      try {
        const sheet = new FrameStyleSheet();
        sheet.replaceSync(state.css);
        doc.adoptedStyleSheets = [sheet];
      } catch (error) {
        console.debug("Could not apply the report styles:", error?.message);
      }
    }
    const generated = doc.documentElement.getAttribute("data-theme");
    if (generated && themeRef.current === DEFAULT_THEME && REPORT_THEMES.some((t) => t.id === generated)) {
      themeRef.current = generated;
      setTheme(generated);
    } else {
      applyTheme(themeRef.current);
    }
    setFrameReady(true);
  };

  // Download exactly what is on screen so the selected theme is baked into the file
  const handleDownload = () => {
    if (!state.html) return;
    downloadHtmlFile(withTheme(state.html, themeRef.current), state.title || report?.title, reportId);
  };

  const currentTheme = REPORT_THEMES.find((t) => t.id === theme) || REPORT_THEMES[0];
  const title = state.title || report?.title || report?.question || "Report";

  const actions = (
    <>
      <Dropdown align="end">
        <Dropdown.Toggle variant="light" size="sm" className="rcc-soft-btn" id="rcv-theme-dropdown" disabled={!state.html}>
          <span className="rcv-swatch" style={{ background: currentTheme.color }} />
          Theme: {currentTheme.label}
        </Dropdown.Toggle>
        <Dropdown.Menu popperConfig={{ strategy: "fixed" }} renderOnMount>
          {REPORT_THEMES.map((option) => (
            <Dropdown.Item key={option.id} active={option.id === theme} onClick={() => handleThemeChange(option.id)}>
              <span className="rcv-swatch" style={{ background: option.color }} />
              {option.label}
            </Dropdown.Item>
          ))}
        </Dropdown.Menu>
      </Dropdown>
      <Button variant="dark" size="sm" className="rcc-solid-btn" onClick={handleDownload} disabled={!state.html}>
        <i className="bi bi-download me-1" />
        Download HTML
      </Button>
    </>
  );

  return (
    <ReportPanelShell
      crumbs={[{ label: "Reports", onClick: onBackToList }, { label: title }]}
      onBack={onBack}
      actions={actions}
    >
      {state.loading && (
        <div className="rcv-center">
          <Spinner animation="border" size="sm" className="me-2" />
          Loading report...
        </div>
      )}
      {state.error && (
        <div className="rcv-center">
          <Alert variant="warning" className="mb-0">{state.error}</Alert>
        </div>
      )}
      {state.frameHtml && (
        <iframe
          ref={iframeRef}
          title={title}
          className="rcv-frame"
          // No scripts: LLM generated HTML must never execute. allow-same-origin lets us switch the theme.
          sandbox="allow-same-origin"
          srcDoc={state.frameHtml}
          style={{ visibility: frameReady ? "visible" : "hidden" }}
          onLoad={handleIframeLoad}
        />
      )}
    </ReportPanelShell>
  );
};

ReportViewerPanel.propTypes = {
  report: PropTypes.shape({
    id: PropTypes.string,
    title: PropTypes.string,
    question: PropTypes.string,
  }).isRequired,
  onBack: PropTypes.func.isRequired,
  onBackToList: PropTypes.func.isRequired,
};

export default ReportViewerPanel;
