"""
Asynchronous DeepQuery report jobs.

The deep_query chat tool only enqueues work here and returns immediately. A
small pool of daemon worker threads runs the two phases of each job by calling
the AI SDK endpoints:

  1. Analysis (once per analysis): /deepQuery extracts the data and returns the
     deepquery_metadata, which is persisted so variants can reuse it.
  2. Report (once per language / variant): /generateDeepQueryReport renders the
     metadata into a themed HTML document, which is persisted too.

Every state change is written to the database (DeepQueryReports) so the UI can
poll it. Cancellation is cooperative and in-memory (threading.Event per report
and per analysis), so it only works within a single chatbot process. The user's
password is held in memory only while a job is queued or running.
"""

import os
import re
import uuid
import queue
import logging
import threading
from dataclasses import dataclass, field

from utils import denodo_tools
from utils.database_utils import DeepQueryReports
from utils.denodo_tools import AISDKRequestCancelled, create_basic_auth_header

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = DeepQueryReports.ACTIVE_STATUSES
MAX_LANGUAGES_PER_REQUEST = 5
DEFAULT_LANGUAGE = "English"
DEFAULT_MAX_REPORTS_PER_USER = 20
DEFAULT_MAX_QUEUE_SIZE = 1000
DEFAULT_COLOR_PALETTE = "red"
MAX_ERROR_LENGTH = 2000

# Same constraints as the AI SDK /generateDeepQueryReport `language` field.
_LANGUAGE_PATTERN = re.compile(r"^[a-zA-Z\u00C0-\u024F\s-]{1,30}$")

# Keys of the chatbot's AI SDK params that are forwarded to /generateDeepQueryReport
LLM_OVERRIDE_KEYS = (
    "llm_provider",
    "llm_model",
    "llm_temperature",
    "llm_max_tokens",
    "thinking_llm_provider",
    "thinking_llm_model",
    "thinking_llm_temperature",
    "thinking_llm_max_tokens",
    "check_ambiguity",
)

class VariantUnavailableError(Exception):
    """The stored analysis has no metadata to generate a new report from."""

class ReportNotFoundError(Exception):
    """The report does not exist or does not belong to the user."""

class ReportQueueFullError(ValueError):
    """The job queue is full; the request cannot be accepted right now."""

class ReportLimitError(ValueError):
    """The user already has the maximum number of stored reports."""

def get_max_reports_per_user():
    """Maximum number of stored reports per user (CHATBOT_MAX_REPORTS_PER_USER, default 20)."""
    try:
        return max(1, int(os.getenv("CHATBOT_MAX_REPORTS_PER_USER", str(DEFAULT_MAX_REPORTS_PER_USER))))
    except ValueError:
        return DEFAULT_MAX_REPORTS_PER_USER

def check_report_limit(user_id, needed=1):
    """Raise ReportLimitError if creating `needed` more reports would exceed the per-user limit."""
    limit = get_max_reports_per_user()
    if DeepQueryReports.count_reports(user_id) + needed > limit:
        raise ReportLimitError(
            f"Report limit reached ({limit} per user). Delete some reports in the DeepQuery Reports Manager to create new ones."
        )

@dataclass
class ReportJobContext:
    """Everything a background job needs; captured when the job is created."""
    user_id: str
    password: str = field(repr=False)
    agent_id: str
    api_host: str
    verify_ssl: bool
    timeout: int
    ai_sdk_params: dict = field(default_factory=dict)
    thread_id: str | None = None

    @classmethod
    def from_user_context(cls, context):
        """Build from the chatbot's per-request UserContext."""
        return cls(
            user_id=context.username,
            password=context.password,
            agent_id=context.agent_id,
            api_host=context.api_host,
            verify_ssl=context.verify_ssl,
            timeout=context.timeout,
            ai_sdk_params=dict(context.ai_sdk_params or {}),
            thread_id=getattr(context, "thread_id", None),
        )

    @property
    def auth(self):
        return create_basic_auth_header(self.user_id, self.password)

def normalize_languages(languages):
    """Trim, validate and de-duplicate (case-insensitive) the requested languages.

    Returns the list of valid languages (default: English). Raises ValueError if
    languages were requested but none of them is valid.
    """
    if isinstance(languages, str):
        languages = [languages]
    requested = [lang for lang in (languages or []) if isinstance(lang, str) and lang.strip()]
    if not requested:
        return [DEFAULT_LANGUAGE]

    result, seen = [], set()
    for lang in requested:
        cleaned = " ".join(lang.split())
        if not _LANGUAGE_PATTERN.match(cleaned):
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            result.append(cleaned)

    if not result:
        raise ValueError(f"Invalid language(s): {', '.join(map(str, requested))}. Use plain language names such as 'English' or 'French'.")
    return result[:MAX_LANGUAGES_PER_REQUEST]

def _truncate_error(message):
    message = str(message or "Unknown error")
    return message if len(message) <= MAX_ERROR_LENGTH else message[:MAX_ERROR_LENGTH] + "..."

def _error_detail(response):
    """Extract a human-readable error from an AI SDK response dict (or None)."""
    if not isinstance(response, dict):
        return None
    detail = response.get("detail") or response.get("error")
    return str(detail) if detail else None

class ReportJobManager:
    """Queues and runs DeepQuery analysis / report jobs on background threads."""

    def __init__(self, max_workers=None):
        if max_workers is None:
            try:
                max_workers = int(os.getenv("CHATBOT_REPORT_MAX_CONCURRENT_JOBS", "4"))
            except ValueError:
                max_workers = 4
        self._max_workers = max(1, max_workers)
        try:
            max_queue = int(os.getenv("CHATBOT_REPORT_MAX_QUEUE_SIZE", str(DEFAULT_MAX_QUEUE_SIZE)))
        except ValueError:
            max_queue = DEFAULT_MAX_QUEUE_SIZE
        self._queue = queue.Queue(maxsize=max(1, max_queue))
        self._workers = []
        self._lock = threading.RLock()
        self._report_events = {}
        self._analysis_events = {}

    # ------------------------------------------------------------------
    # Worker pool
    # ------------------------------------------------------------------

    def _ensure_workers(self):
        with self._lock:
            if self._workers:
                return
            for index in range(self._max_workers):
                worker = threading.Thread(target=self._worker_loop, name=f"dq-report-worker-{index}", daemon=True)
                worker.start()
                self._workers.append(worker)

    def _worker_loop(self):
        while True:
            func, args = self._queue.get()
            try:
                func(*args)
            except Exception:
                logger.error("Unexpected error in DeepQuery report worker", exc_info=True)
                self._discard_events(func, args)
            finally:
                self._queue.task_done()

    def _discard_events(self, func, args):
        """Drop the cancel events of a job that died with an unexpected error, so they do not leak."""
        try:
            with self._lock:
                if func == self._run_analysis:
                    self._analysis_events.pop(args[1], None)
                    for report_id in args[3]:
                        self._report_events.pop(report_id, None)
                elif func == self._run_report:
                    self._report_events.pop(args[1], None)
        except Exception:
            logger.error("Could not clean up DeepQuery job events", exc_info=True)

    def _enqueue(self, func, *args):
        """Queue a job. Raises ReportQueueFullError (without blocking) if the queue is full."""
        self._ensure_workers()
        try:
            self._queue.put_nowait((func, args))
        except queue.Full:
            raise ReportQueueFullError(
                "The report queue is full. Please try again in a few minutes."
            ) from None

    def _abort_job(self, report_ids, analysis_id=None, message="The report queue is full."):
        """Fail reports that could not be queued and release their events."""
        with self._lock:
            if analysis_id:
                self._analysis_events.pop(analysis_id, None)
            for report_id in report_ids:
                self._report_events.pop(report_id, None)
        self._fail_reports(report_ids, message)
        if analysis_id:
            DeepQueryReports.update_analysis_status(analysis_id, "FAILED", _truncate_error(message))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, ctx, analysis_request, languages):
        """Create an analysis with one PENDING report per language and queue it.

        Returns (analysis_id, [{"report_id", "language"}, ...]). Never blocks on the AI SDK.
        """
        languages = normalize_languages(languages)
        check_report_limit(ctx.user_id, len(languages))
        analysis_id = str(uuid.uuid4())

        DeepQueryReports.create_analysis(analysis_id, ctx.user_id, ctx.agent_id, ctx.thread_id, analysis_request)
        reports = []
        for language in languages:
            report_id = str(uuid.uuid4())
            DeepQueryReports.create_report(report_id, analysis_id, ctx.user_id, ctx.agent_id, language)
            reports.append({"report_id": report_id, "language": language})
        with self._lock:
            self._analysis_events[analysis_id] = threading.Event()
            for report in reports:
                self._report_events[report["report_id"]] = threading.Event()

        report_ids = [r["report_id"] for r in reports]
        try:
            self._enqueue(self._run_analysis, ctx, analysis_id, analysis_request, report_ids)
        except ReportQueueFullError as e:
            self._abort_job(report_ids, analysis_id, str(e))
            raise
        logger.info(f"Queued DeepQuery analysis {analysis_id} for user '{ctx.user_id}' ({len(reports)} report(s))")
        return analysis_id, reports

    def variant(self, ctx, report_id, language):
        """Create a new report on the analysis of report_id, reusing its stored metadata.

        Only the HTML generation phase runs. Raises ReportNotFoundError if the
        report is not the user's, VariantUnavailableError if there is no metadata.
        """
        language = normalize_languages([language])[0] if language else DEFAULT_LANGUAGE
        source = DeepQueryReports.get_report(report_id, ctx.user_id)
        if not source:
            raise ReportNotFoundError(report_id)

        analysis = DeepQueryReports.get_analysis(source["analysis_id"], ctx.user_id)
        if not analysis or not analysis.get("metadata"):
            raise VariantUnavailableError(
                "This analysis has no stored data to generate a new variant from (it failed or was cancelled)."
            )

        check_report_limit(ctx.user_id)
        new_report_id = str(uuid.uuid4())
        DeepQueryReports.create_report(new_report_id, source["analysis_id"], ctx.user_id, source["agent_id"], language)
        with self._lock:
            self._report_events[new_report_id] = threading.Event()

        try:
            self._enqueue(self._run_report, ctx, new_report_id, language, analysis["metadata"])
        except ReportQueueFullError as e:
            self._abort_job([new_report_id], message=str(e))
            raise
        return DeepQueryReports.get_report(new_report_id, ctx.user_id)

    def retry(self, ctx, report_id):
        """Re-queue a FAILED / CANCELLED report in place.

        With stored metadata only the HTML phase runs; otherwise the whole
        analysis runs again from the stored question. Returns the updated report.
        Raises ReportNotFoundError, or ValueError if the report is not retryable.
        """
        report = DeepQueryReports.get_report(report_id, ctx.user_id)
        if not report:
            raise ReportNotFoundError(report_id)
        if report["status"] not in ("FAILED", "CANCELLED"):
            raise ValueError("Only failed or cancelled reports can be retried.")

        analysis = DeepQueryReports.get_analysis(report["analysis_id"], ctx.user_id)
        if not analysis:
            raise VariantUnavailableError("The analysis behind this report no longer exists.")
        metadata = analysis.get("metadata")
        question = analysis.get("question")
        if not metadata and not question:
            raise VariantUnavailableError("There is not enough stored information to retry this report.")

        if not DeepQueryReports.reset_report(report_id, ctx.user_id):
            raise ValueError("Only failed or cancelled reports can be retried.")

        analysis_id = None if metadata else report["analysis_id"]
        with self._lock:
            self._report_events[report_id] = threading.Event()
            if analysis_id:
                self._analysis_events[analysis_id] = threading.Event()

        try:
            if metadata:
                self._enqueue(self._run_report, ctx, report_id, report["language"], metadata)
            else:
                DeepQueryReports.update_analysis_status(report["analysis_id"], "PENDING")
                self._enqueue(self._run_analysis, ctx, report["analysis_id"], question, [report_id])
        except ReportQueueFullError as e:
            self._abort_job([report_id], analysis_id, str(e))
            raise
        return DeepQueryReports.get_report(report_id, ctx.user_id)

    def submit_from_legacy(self, ctx, question, metadata, language):
        """Create a report from deepquery_metadata of an old (synchronous) chat tool call.

        Stores the metadata as a new analysis and runs only the HTML phase.
        Returns the new report.
        """
        language = normalize_languages([language])[0] if language else DEFAULT_LANGUAGE
        check_report_limit(ctx.user_id)
        analysis_id = str(uuid.uuid4())
        report_id = str(uuid.uuid4())
        title = metadata.get("analysis_title") if isinstance(metadata, dict) else None

        DeepQueryReports.create_analysis(analysis_id, ctx.user_id, ctx.agent_id, ctx.thread_id, question or "")
        DeepQueryReports.set_analysis_metadata(analysis_id, metadata, title)
        DeepQueryReports.create_report(report_id, analysis_id, ctx.user_id, ctx.agent_id, language, title)
        with self._lock:
            self._report_events[report_id] = threading.Event()

        try:
            self._enqueue(self._run_report, ctx, report_id, language, metadata)
        except ReportQueueFullError as e:
            self._abort_job([report_id], message=str(e))
            raise
        return DeepQueryReports.get_report(report_id, ctx.user_id)

    def cancel(self, report_id, user_id):
        """Cancel a PENDING/PROCESSING report. Returns True if it was cancelled."""
        report = DeepQueryReports.get_report(report_id, user_id)
        if not report:
            raise ReportNotFoundError(report_id)
        if report["status"] not in ACTIVE_STATUSES:
            return False

        changed = DeepQueryReports.update_status(
            report_id, "CANCELLED", stage="done", only_if_status=ACTIVE_STATUSES
        )
        with self._lock:
            event = self._report_events.get(report_id)
            if event:
                event.set()

            # Abort the shared data extraction only when nobody is waiting for it anymore.
            analysis_event = self._analysis_events.get(report["analysis_id"])
            if analysis_event and not analysis_event.is_set():
                siblings = DeepQueryReports.get_analysis_report_statuses(report["analysis_id"])
                if not any(status in ACTIVE_STATUSES for _, status in siblings):
                    analysis_event.set()
        return bool(changed)

    def delete(self, report_id, user_id):
        """Delete a report, cancelling it first if it is still running."""
        try:
            self.cancel(report_id, user_id)
        except ReportNotFoundError:
            return False
        deleted = DeepQueryReports.delete_report(report_id, user_id)
        with self._lock:
            self._report_events.pop(report_id, None)
        return deleted

    def delete_all(self, user_id, agent_id=None):
        """Cancel the user's running reports and delete every report. Returns the deleted count."""
        for report in DeepQueryReports.list_reports(user_id, agent_id):
            if report["status"] in ACTIVE_STATUSES:
                try:
                    self.cancel(report["report_id"], user_id)
                except ReportNotFoundError:
                    pass
        return DeepQueryReports.delete_all(user_id, agent_id)

    # ------------------------------------------------------------------
    # Phase 1: analysis (data extraction)
    # ------------------------------------------------------------------

    def _fail_reports(self, report_ids, message):
        message = _truncate_error(message)
        for report_id in report_ids:
            DeepQueryReports.update_status(
                report_id, "FAILED", stage="done", error=message, only_if_status=ACTIVE_STATUSES
            )

    def _cancel_reports(self, report_ids):
        for report_id in report_ids:
            DeepQueryReports.update_status(
                report_id, "CANCELLED", stage="done", only_if_status=ACTIVE_STATUSES
            )

    def _run_analysis(self, ctx, analysis_id, analysis_request, report_ids):
        with self._lock:
            analysis_event = self._analysis_events.get(analysis_id)

        handed_off = set()
        try:
            running = [
                report_id for report_id in report_ids
                if DeepQueryReports.update_status(
                    report_id, "PROCESSING", stage="extracting_data", only_if_status=ACTIVE_STATUSES
                )
            ]
            if not running:
                DeepQueryReports.update_analysis_status(analysis_id, "CANCELLED")
                return

            DeepQueryReports.update_analysis_status(analysis_id, "PROCESSING")
            response = denodo_tools.deep_query(
                analysis_request=analysis_request,
                api_host=ctx.api_host,
                auth=ctx.auth,
                verify_ssl=ctx.verify_ssl,
                timeout=ctx.timeout,
                cancel_event=analysis_event,
                **ctx.ai_sdk_params,
            )

            metadata = response.get("deepquery_metadata") if isinstance(response, dict) else None
            if not metadata:
                message = _error_detail(response) or "DeepQuery analysis did not return any data."
                DeepQueryReports.update_analysis_status(analysis_id, "FAILED", _truncate_error(message))
                self._fail_reports(running, message)
                return

            title = metadata.get("analysis_title") if isinstance(metadata, dict) else None
            DeepQueryReports.set_analysis_metadata(analysis_id, metadata, title)

            for report_id in running:
                queued = DeepQueryReports.update_status(
                    report_id, "PROCESSING", stage="generating_html", title=title, only_if_status=ACTIVE_STATUSES
                )
                report = DeepQueryReports.get_report(report_id, ctx.user_id) if queued else None
                if report:
                    try:
                        self._enqueue(self._run_report, ctx, report_id, report["language"], metadata)
                        handed_off.add(report_id)
                    except ReportQueueFullError as e:
                        self._fail_reports([report_id], str(e))
        except AISDKRequestCancelled:
            logger.info(f"DeepQuery analysis {analysis_id} cancelled by the user")
            DeepQueryReports.update_analysis_status(analysis_id, "CANCELLED")
            self._cancel_reports(report_ids)
        except Exception as e:
            logger.error(f"DeepQuery analysis {analysis_id} failed", exc_info=True)
            DeepQueryReports.update_analysis_status(analysis_id, "FAILED", _truncate_error(e))
            self._fail_reports(report_ids, e)
        finally:
            with self._lock:
                self._analysis_events.pop(analysis_id, None)
                # Reports that never reach the HTML phase must not leak their cancel events
                for report_id in report_ids:
                    if report_id not in handed_off:
                        self._report_events.pop(report_id, None)

    # ------------------------------------------------------------------
    # Phase 2: HTML report generation
    # ------------------------------------------------------------------

    def _run_report(self, ctx, report_id, language, metadata):
        with self._lock:
            report_event = self._report_events.get(report_id)

        try:
            started = DeepQueryReports.update_status(
                report_id, "PROCESSING", stage="generating_html", only_if_status=ACTIVE_STATUSES
            )
            if not started:
                return  # Cancelled or deleted while waiting in the queue

            llm_params = {
                key: ctx.ai_sdk_params[key]
                for key in LLM_OVERRIDE_KEYS
                if ctx.ai_sdk_params.get(key) is not None
            }
            response = denodo_tools.generate_deepquery_report(
                deepquery_metadata=metadata,
                api_host=ctx.api_host,
                auth=ctx.auth,
                color_palette=DEFAULT_COLOR_PALETTE,
                language=language,
                verify_ssl=ctx.verify_ssl,
                timeout=ctx.timeout,
                cancel_event=report_event,
                **llm_params,
            )

            html = response.get("html_report") if isinstance(response, dict) else None
            if not html:
                self._fail_reports([report_id], _error_detail(response) or "Report generation returned no content.")
                return

            DeepQueryReports.set_report_html(report_id, html, response.get("translated_title"))
        except AISDKRequestCancelled:
            logger.info(f"DeepQuery report {report_id} cancelled by the user")
            self._cancel_reports([report_id])
        except Exception as e:
            logger.error(f"DeepQuery report {report_id} failed", exc_info=True)
            self._fail_reports([report_id], e)
        finally:
            with self._lock:
                self._report_events.pop(report_id, None)

report_job_manager = ReportJobManager()
