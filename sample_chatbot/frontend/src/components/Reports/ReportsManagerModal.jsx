import React, { useMemo, useRef, useState } from "react";
import { BaseModal, ConfirmationModal } from "../Common/Modal";
import Overlay from "react-bootstrap/Overlay";
import Popover from "react-bootstrap/Popover";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";
import { useReport, REPORT_STATUS, isActiveStatus } from "../../contexts/ReportContext";
import { downloadHtmlFile } from "../../utils/reportFiles";
import ReportExplorerPanel from "./ReportExplorerPanel";
import ReportViewerPanel from "./ReportViewerPanel";
import "./ReportsManagerModal.css";
import "./ReportViewerModal.css";

const assetBaseUrl = import.meta.env.BASE_URL;

const STATUS_META = {
  [REPORT_STATUS.PENDING]: { label: "Pending", className: "rcc-st-pending" },
  [REPORT_STATUS.PROCESSING]: { label: "Processing", className: "rcc-st-processing" },
  [REPORT_STATUS.COMPLETED]: { label: "Completed", className: "rcc-st-completed" },
  [REPORT_STATUS.FAILED]: { label: "Failed", className: "rcc-st-failed" },
  [REPORT_STATUS.CANCELLED]: { label: "Cancelled", className: "rcc-st-cancelled" },
};

const STAGE_LABELS = {
  queued: "Waiting in queue",
  extracting_data: "Extracting data",
  generating_html: "Generating HTML",
};

const FILTERS = [
  { id: "all", label: "All", match: () => true },
  { id: "running", label: "Running", match: (report) => isActiveStatus(report.status) },
  { id: "completed", label: "Completed", match: (report) => report.status === REPORT_STATUS.COMPLETED },
  {
    id: "failed",
    label: "Failed",
    match: (report) => report.status === REPORT_STATUS.FAILED || report.status === REPORT_STATUS.CANCELLED,
  },
];

const SUGGESTED_LANGUAGES = ["English", "Spanish", "French", "German", "Italian", "Portuguese"];
const LANGUAGE_PATTERN = /^[a-zA-Z\u00C0-\u024F\s-]*$/;
const LIST_VIEW = { type: "list" };

// Every floating element is mounted on <body> with a fixed strategy so that the
// modal body (overflow) never clips it and it always stays above the modal.
const OVERLAY_PROPS = { container: () => document.body, popperConfig: { strategy: "fixed" } };

const formatRelative = (iso) => {
  if (!iso) return "-";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "-";
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "numeric",
    minute: "2-digit",
  });
};

const formatExact = (iso) => (iso ? new Date(iso).toLocaleString() : "");

const IconAction = ({ tooltip, onClick, disabled, tone = "", active = false, children }) => (
  <OverlayTrigger placement="top" overlay={<Tooltip id={`rcc-tip-${tooltip}`}>{tooltip}</Tooltip>} {...OVERLAY_PROPS}>
    <button
      type="button"
      className={`rcc-icon-btn ${tone ? `rcc-icon-btn-${tone}` : ""} ${active ? "is-active" : ""}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={tooltip}
    >
      {children}
    </button>
  </OverlayTrigger>
);

const HoverTitle = ({ text }) => {
  const [show, setShow] = useState(false);
  const targetRef = useRef(null);
  const timerRef = useRef(null);

  const open = () => {
    clearTimeout(timerRef.current);
    setShow(true);
  };
  const close = () => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setShow(false), 150);
  };

  return (
    <>
      <div ref={targetRef} className="rcc-row-title" onMouseEnter={open} onMouseLeave={close}>
        {text}
      </div>
      <Overlay target={targetRef.current} show={show} placement="bottom-start" {...OVERLAY_PROPS}>
        <Popover id="rcc-title-popover" className="rcc-title-popover" onMouseEnter={open} onMouseLeave={close}>
          <Popover.Body>{text}</Popover.Body>
        </Popover>
      </Overlay>
    </>
  );
};

const VariantForm = ({ onCreate, onClose }) => {
  const [language, setLanguage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const trimmed = language.trim();

  const submit = async (event) => {
    event.preventDefault();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    const created = await onCreate(trimmed);
    setSubmitting(false);
    if (created) onClose();
  };

  return (
    <form className="rcc-variant-form" onSubmit={submit}>
      <div className="rcc-variant-label">
        <i className="bi bi-translate me-1" />
        New variant in another language
        <span className="text-muted ms-2">Reuses the extracted data, so it only takes the report generation time.</span>
      </div>
      <div className="rcc-variant-controls">
        <input
          type="text"
          className="rcc-input"
          autoFocus
          placeholder="e.g. French"
          value={language}
          maxLength={30}
          onChange={(e) => {
            if (LANGUAGE_PATTERN.test(e.target.value)) setLanguage(e.target.value);
          }}
        />
        <button type="submit" className="rcc-primary-btn" disabled={!trimmed || submitting}>
          {submitting ? "Creating..." : "Create"}
        </button>
        <button type="button" className="rcc-ghost-btn" onClick={onClose}>
          Cancel
        </button>
      </div>
      <div className="rcc-language-chips">
        {SUGGESTED_LANGUAGES.map((option) => (
          <button type="button" key={option} className="rcc-chip" onClick={() => setLanguage(option)}>
            {option}
          </button>
        ))}
      </div>
    </form>
  );
};

const ReportRow = ({ report, actions }) => {
  const [variantOpen, setVariantOpen] = useState(false);
  const meta = STATUS_META[report.status] || { label: report.status, className: "rcc-st-cancelled" };
  const active = isActiveStatus(report.status);
  const completed = report.status === REPORT_STATUS.COMPLETED;
  const retryable = report.status === REPORT_STATUS.FAILED || report.status === REPORT_STATUS.CANCELLED;
  const hasAnalysisData =
    completed || (report.status === REPORT_STATUS.PROCESSING && report.stage === "generating_html");
  const displayTitle = report.title || report.question || "Untitled report";
  const showQuestion = report.title && report.question && report.title !== report.question;

  return (
    <div className={`rcc-row ${meta.className}`}>
      <div className="rcc-row-main">
        <span className="rcc-dot" aria-hidden="true" />
        <div className="rcc-row-text">
          <HoverTitle text={displayTitle} />
          {showQuestion && <div className="rcc-row-sub">{report.question}</div>}

          {active && (
            <div className="rcc-progress" aria-live="polite">
              <div className="rcc-progress-bar" />
              <span className="rcc-stage">{STAGE_LABELS[report.stage] || "Working"}</span>
            </div>
          )}
          {report.status === REPORT_STATUS.FAILED && (
            <div className="rcc-error" role="alert">
              <i className="bi bi-exclamation-triangle-fill me-1" />
              {report.error || "The report could not be generated."}
            </div>
          )}
        </div>

        <div className="rcc-row-meta">
          <span className="rcc-lang" title="Report language">
            <i className="bi bi-translate me-1" />
            {report.language}
          </span>
          <div className="rcc-status-wrapper">
            <span className={`rcc-status ${meta.className}`}>{meta.label}</span>
          </div>
          <span className="rcc-time" title={formatExact(report.completedAt || report.createdAt)}>
            {formatRelative(report.completedAt && !active ? report.completedAt : report.createdAt)}
          </span>
        </div>

        <div className="rcc-row-actions">
          {active && (
            <IconAction tooltip="Cancel" tone="danger" onClick={() => actions.onCancel(report)}>
              <i className="bi bi-stop-circle" />
            </IconAction>
          )}
          {retryable && (
            <IconAction tooltip="Retry" tone="accent" onClick={() => actions.onRetry(report)}>
              <i className="bi bi-arrow-clockwise" />
            </IconAction>
          )}
          {completed && (
            <IconAction tooltip="View report" tone="accent" onClick={() => actions.onView(report)}>
              <i className="bi bi-eye" />
            </IconAction>
          )}
          {completed && (
            <IconAction tooltip="New variant (another language)" active={variantOpen} onClick={() => setVariantOpen((prev) => !prev)}>
              <i className="bi bi-plus-circle" />
            </IconAction>
          )}
          {hasAnalysisData && (
            <IconAction tooltip="Additional information (model, VQL, tables, graphs)" onClick={() => actions.onExplore(report)}>
              <img src={`${assetBaseUrl}tools/deep_query/denodo_icon_black.svg`} alt="" width="16" height="16" />
            </IconAction>
          )}
          {completed && (
            <IconAction tooltip="Download HTML" onClick={() => actions.onDownload(report)}>
              <i className="bi bi-download" />
            </IconAction>
          )}
          <IconAction tooltip={active ? "Cancel and delete" : "Delete"} tone="danger" onClick={() => actions.onDelete(report)}>
            <i className="bi bi-trash" />
          </IconAction>
        </div>
      </div>

      {variantOpen && (
        <VariantForm
          onCreate={(language) => actions.onVariant(report, language)}
          onClose={() => setVariantOpen(false)}
        />
      )}
    </div>
  );
};

const ReportsManagerModal = () => {
  const {
    reports,
    reportLimit,
    activeCount,
    isModalOpen,
    setIsModalOpen,
    cancelReport,
    createVariant,
    retryReport,
    deleteReport,
    clearAllReports,
    fetchHtml,
    showToast,
  } = useReport();
  
  const [view, setView] = useState(LIST_VIEW);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [confirmDelete, setConfirmDelete] = useState({ show: false, type: null, report: null });

  const handleClose = () => setIsModalOpen(false);

  const remainingSlots = Math.max(0, reportLimit - reports.length);
  const quotaTone = remainingSlots === 0 ? "is-full" : remainingSlots <= 3 ? "is-warn" : "";
  const quotaTitle = remainingSlots === 0
    ? `Report limit reached (${reportLimit}). Delete some reports to create new ones.`
    : `You can store up to ${reportLimit} reports (${remainingSlots} left).`;

  const goBack = () => {
    if (view.type === "explore" && view.detail) setView({ ...view, detail: null });
    else setView(LIST_VIEW);
  };
  const handleHide = () => (view.type === "list" ? handleClose() : goBack());

  const handleDownload = async (report) => {
    try {
      const { html_report: html, title } = await fetchHtml(report.id);
      downloadHtmlFile(html, title || report.title, report.id);
    } catch (error) {
      showToast("Download failed", error?.response?.data?.error || error?.message || "The report could not be downloaded.", "danger");
    }
  };
  
  const executeDelete = () => {
    if (confirmDelete.type === "single" && confirmDelete.report) {
      deleteReport(confirmDelete.report.id);
    } else if (confirmDelete.type === "all") {
      clearAllReports();
    }
    setConfirmDelete((prev) => ({ ...prev, show: false }));
  };

  const actions = {
    onView: (report) => setView({ type: "viewer", report }),
    onExplore: (report) => setView({ type: "explore", report, detail: null }),
    onDownload: handleDownload,
    onCancel: (report) => cancelReport(report.id),
    onRetry: (report) => retryReport(report.id),
    onDelete: (report) => setConfirmDelete({ show: true, type: "single", report }),
    onVariant: (report, language) => createVariant(report.id, language),
  };

  const counts = useMemo(() => {
    const result = {};
    FILTERS.forEach((option) => {
      result[option.id] = reports.filter(option.match).length;
    });
    return result;
  }, [reports]);

  const filteredReports = useMemo(() => {
    const activeFilter = FILTERS.find((option) => option.id === filter) || FILTERS[0];
    const needle = search.trim().toLowerCase();
    
    return reports.filter((report) => {
      if (!activeFilter.match(report)) return false;
      if (needle && !`${report.title} ${report.question} ${report.language}`.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [reports, filter, search]);

  const renderList = () => (
    <div className="rcc-list-view">
      {reports.length === 0 ? (
        <div className="rcc-empty">
          <i className="bi bi-inbox" />
          <p className="mb-1 fw-semibold">No reports yet</p>
          <p className="text-muted mb-0">
            Ask the chatbot for a DeepQuery analysis and it will appear here while it runs in the background.
          </p>
        </div>
      ) : (
        <>
          <div className="rcc-tabs-bar">
            <ul className="nav nav-tabs rcc-report-tabs" role="tablist" aria-label="Filter reports">
              {FILTERS.map((option) => (
                <li className="nav-item" role="presentation" key={option.id}>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={filter === option.id}
                    className={`nav-link rcc-tab-link ${filter === option.id ? "active" : ""}`}
                    onClick={() => setFilter(option.id)}
                  >
                    {option.label}
                    <span className="rcc-filter-count">{counts[option.id]}</span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="rcc-toolbar-right">
              <div className="rcc-search">
                <i className="bi bi-search" />
                <input
                  type="search"
                  placeholder="Search reports"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  aria-label="Search reports"
                />
              </div>
              <button 
                type="button" 
                className="rcc-ghost-btn rcc-ghost-danger" 
                onClick={() => setConfirmDelete({ show: true, type: "all", report: null })}
              >
                <i className="bi bi-trash me-1" />
                Clear all
              </button>
            </div>
          </div>

          <div className="rcc-list-scroll">
            {filteredReports.length === 0 ? (
              <div className="rcc-empty rcc-empty-small">
                <p className="text-muted mb-0">No reports match the current filter.</p>
              </div>
            ) : (
              <div className="rcc-flat-list">
                {filteredReports.map((report) => (
                  <ReportRow key={report.id} report={report} actions={actions} />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );

  return (
    <>
      <BaseModal
        show={isModalOpen}
        onHide={handleHide}
        onExited={() => setView(LIST_VIEW)}
        title="DeepQuery Reports Manager"
        headerBadges={
          <>
            <span className={`rcc-quota ${quotaTone}`} title={quotaTitle}>
              {reports.length} / {reportLimit} reports
            </span>
            {activeCount > 0 && (
              <span className="rcc-live" title="Reports are being generated in the background">
                <span className="rcc-live-dot" />
                {activeCount} running
              </span>
            )}
          </>
        }
        size="xl"
        fixedHeight
        backdrop="static"
      >
          {view.type === "list" && renderList()}
          {view.type === "explore" && (
            <ReportExplorerPanel
              report={view.report}
              detail={view.detail}
              onDetail={(detail) => setView({ ...view, detail })}
              onBack={goBack}
              onBackToList={() => setView(LIST_VIEW)}
            />
          )}
          {view.type === "viewer" && (
            <ReportViewerPanel report={view.report} onBack={goBack} onBackToList={() => setView(LIST_VIEW)} />
          )}
      </BaseModal>

      <ConfirmationModal
        show={confirmDelete.show}
        onHide={() => setConfirmDelete((prev) => ({ ...prev, show: false }))}
        onConfirm={executeDelete}
        nested
        title={confirmDelete.type === 'all' ? 'Clear All Reports' : 'Delete Report'}
        message={
          confirmDelete.type === 'all'
            ? "Are you sure you want to permanently delete ALL reports? This action cannot be undone."
            : "Are you sure you want to permanently delete this report? This action cannot be undone."
        }
        confirmLabel="Yes, delete"
      />
    </>
  );
};

export default ReportsManagerModal;
