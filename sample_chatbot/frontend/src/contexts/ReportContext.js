import React, {
  createContext,
  useState,
  useContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
} from 'react';
import api from '../api/client';
import NotificationToast from '../components/NotificationToast/NotificationToast';

// Create the context
const ReportContext = createContext();

// Report status constants (same values as the /api/reports/status endpoint)
export const REPORT_STATUS = {
  PENDING: 'PENDING',
  PROCESSING: 'PROCESSING',
  COMPLETED: 'COMPLETED',
  FAILED: 'FAILED',
  CANCELLED: 'CANCELLED',
};

export const isActiveStatus = (status) =>
  status === REPORT_STATUS.PENDING || status === REPORT_STATUS.PROCESSING;

// No idle polling: the server is only queried while jobs are running or the manager is open
const POLL_FAST_MS = 3000; // first minute of an active job
const POLL_MEDIUM_MS = 5000; // up to 5 minutes
const POLL_SLOW_MS = 10000; // up to 15 minutes, and while the manager is open without active jobs
const POLL_IDLE_MS = 30000; // very long jobs
const POLL_MAX_BACKOFF_MS = 60000; // ceiling when the server keeps failing
const STALE_ON_VISIBLE_MS = 30000;

// Delay grows with the age of the current burst of active jobs and doubles on every consecutive error
const nextPollDelay = (activeSince, failures = 0) => {
  let delay = POLL_SLOW_MS;
  if (activeSince) {
    const elapsed = Date.now() - activeSince;
    if (elapsed < 60000) delay = POLL_FAST_MS;
    else if (elapsed < 300000) delay = POLL_MEDIUM_MS;
    else if (elapsed < 900000) delay = POLL_SLOW_MS;
    else delay = POLL_IDLE_MS;
  }
  return Math.min(delay * 2 ** Math.min(failures, 5), Math.max(delay, POLL_MAX_BACKOFF_MS));
};

// Default when the server does not report a limit (same as the backend default)
const DEFAULT_REPORT_LIMIT = 20;

const normalizeReport = (raw) => ({
  id: raw.report_id,
  analysisId: raw.analysis_id,
  title: raw.title || '',
  question: raw.question || '',
  language: raw.language || 'English',
  status: raw.status,
  stage: raw.stage,
  error: raw.error || null,
  createdAt: raw.created_at,
  startedAt: raw.started_at,
  completedAt: raw.completed_at,
});

const errorMessage = (error, fallback) =>
  error?.response?.data?.error || error?.response?.data?.message || error?.message || fallback;

// Create a provider component
export const ReportProvider = ({ children }) => {
  const [reports, setReports] = useState([]); // Newest first, mirrors the server
  const [reportsLoaded, setReportsLoaded] = useState(false);
  const [reportLimit, setReportLimit] = useState(DEFAULT_REPORT_LIMIT); // max stored reports per user
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [toast, setToast] = useState({ show: false, message: '', variant: 'info', title: '' });

  const previousStatusesRef = useRef(null); // report id -> last seen status (null until first load)
  const inFlightRef = useRef(false);
  const lastFetchRef = useRef(0);
  const activeSinceRef = useRef(null); // when the current burst of active jobs started
  const failuresRef = useRef(0); // consecutive failed status requests (drives the backoff)
  const prevCountRef = useRef(null); // report count of the previous refresh (null until first load)

  const showToast = useCallback((title, message, variant = 'info') => {
    setToast({ show: true, title, message, variant });
  }, []);

  const applyServerReports = useCallback((serverReports) => {
    const previous = previousStatusesRef.current;
    const next = {};
    serverReports.forEach((report) => {
      next[report.id] = report.status;
      if (previous && isActiveStatus(previous[report.id])) {
        const label = report.title || report.question || 'DeepQuery report';
        if (report.status === REPORT_STATUS.COMPLETED) {
          setToast({
            show: true,
            title: 'Report ready',
            message: `${label} (${report.language}) is ready in the DeepQuery Reports Manager.`,
            variant: 'success',
          });
        } else if (report.status === REPORT_STATUS.FAILED) {
          setToast({
            show: true,
            title: 'Report failed',
            message: `${label} (${report.language}) failed${report.error ? `: ${report.error}` : '.'}`,
            variant: 'danger',
          });
        }
      }
    });
    previousStatusesRef.current = next;
    setReports(serverReports);
    setReportsLoaded(true);
  }, []);

  // Fetch the current state of all reports (never contains HTML or metadata)
  const refreshReports = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    lastFetchRef.current = Date.now();
    try {
      const response = await api.get('reports/status');
      failuresRef.current = 0;
      if (Array.isArray(response.data?.reports)) {
        if (Number.isFinite(response.data.limit)) setReportLimit(response.data.limit);
        applyServerReports(response.data.reports.map(normalizeReport));
      }
    } catch (error) {
      failuresRef.current += 1;
      if (error?.response?.status === 401) {
        // Session expired (or opened elsewhere): stop polling until the user logs in again
        setPollingEnabled(false);
      } else {
        console.debug('Could not refresh reports:', error?.message);
      }
    } finally {
      inFlightRef.current = false;
    }
  }, [applyServerReports]);

  const activeCount = useMemo(
    () => reports.filter((report) => isActiveStatus(report.status)).length,
    [reports]
  );
  const hasActive = activeCount > 0;

  const hasActiveRef = useRef(false);
  hasActiveRef.current = hasActive;
  if (hasActive && !activeSinceRef.current) activeSinceRef.current = Date.now();
  if (!hasActive) activeSinceRef.current = null;

  // Seed the state once on login and clear it on logout / expired session
  useEffect(() => {
    if (!pollingEnabled) {
      previousStatusesRef.current = null;
      setReports([]);
      setReportsLoaded(false);
      return;
    }
    refreshReports();
  }, [pollingEnabled, refreshReports]);

  // Refresh once whenever the manager is opened
  useEffect(() => {
    if (pollingEnabled && isModalOpen) refreshReports();
  }, [pollingEnabled, isModalOpen, refreshReports]);

  // Poll only while jobs are active or the manager is open. A single timeout chain
  // (delay recomputed on every tick) avoids refetching when the state flips.
  const shouldPoll = pollingEnabled && (hasActive || isModalOpen);
  useEffect(() => {
    if (!shouldPoll) return undefined;
    let timer;
    const tick = async () => {
      if (!document.hidden) await refreshReports();
      timer = setTimeout(tick, nextDelay());
    };
    const nextDelay = () =>
      nextPollDelay(hasActiveRef.current ? activeSinceRef.current : null, failuresRef.current);
    timer = setTimeout(tick, nextDelay());
    return () => clearTimeout(timer);
  }, [shouldPoll, refreshReports]);

  // Coming back to a tab that has not been refreshed for a while
  useEffect(() => {
    if (!pollingEnabled) return undefined;
    const handleVisibility = () => {
      if (!document.hidden && Date.now() - lastFetchRef.current > STALE_ON_VISIBLE_MS) refreshReports();
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [pollingEnabled, refreshReports]);

  // Cancel a pending / running report
  const cancelReport = useCallback(async (reportId) => {
    try {
      await api.post(`reports/${reportId}/cancel`);
    } catch (error) {
      showToast('Could not cancel', errorMessage(error, 'The report could not be cancelled.'), 'danger');
    }
    await refreshReports();
  }, [refreshReports, showToast]);

  // Warn when a new report brings the user close to (or at) the stored reports limit.
  // The first load stays silent: only growth afterwards triggers a warning.
  useEffect(() => {
    if (!reportsLoaded) {
      prevCountRef.current = null;
      return;
    }
    const previous = prevCountRef.current;
    prevCountRef.current = reports.length;
    if (previous === null || reports.length <= previous) return;
    const remaining = reportLimit - reports.length;
    if (remaining > 3) return;
    showToast(
      remaining <= 0 ? 'Report limit reached' : 'Report limit almost reached',
      remaining <= 0
        ? `You have ${reports.length} of ${reportLimit} reports. Delete some in the DeepQuery Reports Manager to create new ones.`
        : `You have ${reports.length} of ${reportLimit} reports. ${remaining} left before you need to delete some.`,
      'warning'
    );
  }, [reports.length, reportLimit, reportsLoaded, showToast]);

  // Generate the same analysis in another language, reusing the extracted data
  const createVariant = useCallback(async (reportId, language) => {
    try {
      await api.post(`reports/${reportId}/variant`, { language });
      showToast('Variant queued', `A ${language} version of the report is being generated.`, 'info');
      await refreshReports();
      return true;
    } catch (error) {
      showToast('Could not create variant', errorMessage(error, 'The variant could not be created.'), 'danger');
      return false;
    }
  }, [refreshReports, showToast]);

  // Run an analysis again from its original question (used when the report of a chat message is gone).
  // Returns the new report ids (empty on failure).
  const regenerateFromQuestion = useCallback(async ({ question, languages }) => {
    try {
      const response = await api.post('reports', { question, languages });
      await refreshReports();
      return (response.data?.reports || []).map((report) => report.report_id);
    } catch (error) {
      showToast('Could not regenerate report', errorMessage(error, 'The report could not be regenerated.'), 'danger');
      return [];
    }
  }, [refreshReports, showToast]);

  // Re-queue a failed / cancelled report in place
  const retryReport = useCallback(async (reportId) => {
    try {
      await api.post(`reports/${reportId}/retry`);
      showToast('Retrying report', 'The report has been queued again.', 'info');
      await refreshReports();
      return true;
    } catch (error) {
      showToast('Could not retry', errorMessage(error, 'The report could not be retried.'), 'danger');
      return false;
    }
  }, [refreshReports, showToast]);

  // Build a report from the metadata of a chat message created before async reports existed.
  // Returns the new report id (or null on failure).
  const regenerateLegacy = useCallback(async ({ question, deepqueryMetadata, language }) => {
    try {
      const response = await api.post('reports/from-legacy', {
        question,
        deepquery_metadata: deepqueryMetadata,
        language,
      });
      await refreshReports();
      return response.data?.report?.report_id || null;
    } catch (error) {
      showToast('Could not generate report', errorMessage(error, 'The report could not be generated.'), 'danger');
      return null;
    }
  }, [refreshReports, showToast]);

  // Delete one report from the server
  const deleteReport = useCallback(async (reportId) => {
    try {
      await api.delete(`reports/${reportId}`);
      if (previousStatusesRef.current) delete previousStatusesRef.current[reportId];
      setReports((prev) => prev.filter((report) => report.id !== reportId));
    } catch (error) {
      showToast('Could not delete', errorMessage(error, 'The report could not be deleted.'), 'danger');
      await refreshReports();
    }
  }, [refreshReports, showToast]);

  // Delete every report (running ones are cancelled first)
  const clearAllReports = useCallback(async () => {
    try {
      await api.delete('reports');
      previousStatusesRef.current = {};
      setReports([]);
    } catch (error) {
      showToast('Could not clear reports', errorMessage(error, 'The reports could not be deleted.'), 'danger');
      await refreshReports();
    }
  }, [refreshReports, showToast]);

  // Heavy payloads are fetched on demand only
  const fetchHtml = useCallback(async (reportId) => {
    const response = await api.get(`reports/${reportId}/html`);
    return response.data; // { html_report, title }
  }, []);

  const fetchAnalysis = useCallback(async (reportId) => {
    const response = await api.get(`reports/${reportId}/analysis`);
    return response.data; // { question, title, deepquery_metadata }
  }, []);

  // Get counts by status
  const getStatusCounts = useCallback(() => {
    return reports.reduce((counts, report) => {
      counts[report.status] = (counts[report.status] || 0) + 1;
      return counts;
    }, {});
  }, [reports]);

  const value = useMemo(() => ({
    reports,
    reportsLoaded,
    reportLimit,
    activeCount,
    isModalOpen,
    setIsModalOpen,
    setPollingEnabled,
    refreshReports,
    cancelReport,
    createVariant,
    retryReport,
    regenerateLegacy,
    regenerateFromQuestion,
    deleteReport,
    removeReport: deleteReport,
    clearAllReports,
    fetchHtml,
    fetchAnalysis,
    getStatusCounts,
    showToast,
  }), [
    reports, reportsLoaded, reportLimit, activeCount, isModalOpen, refreshReports, cancelReport,
    createVariant, retryReport, regenerateLegacy, regenerateFromQuestion, deleteReport, clearAllReports, fetchHtml, fetchAnalysis, getStatusCounts, showToast,
  ]);

  return (
    <ReportContext.Provider value={value}>
      {children}
      <NotificationToast
        show={toast.show}
        message={toast.message}
        variant={toast.variant}
        title={toast.title}
        onClose={() => setToast((prev) => ({ ...prev, show: false }))}
      />
    </ReportContext.Provider>
  );
};

// Create a custom hook to use the report context
export const useReport = () => {
  const context = useContext(ReportContext);
  if (context === undefined) {
    throw new Error('useReport must be used within a ReportProvider');
  }
  return context;
};

export default ReportContext;
