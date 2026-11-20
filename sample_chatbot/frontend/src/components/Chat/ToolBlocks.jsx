import React, { useEffect, useMemo, useState } from "react";
import { useConfig, useNumberFormat } from "../../contexts/ConfigContext";
import { useReport, REPORT_STATUS } from "../../contexts/ReportContext";
import Card from "react-bootstrap/Card";
import Badge from "react-bootstrap/Badge";
import Spinner from "react-bootstrap/Spinner";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CSVLink } from "react-csv";
import ExcelJS from "exceljs";
import "./ToolBlocks.css";
import { markdownComponents } from "./markdownComponents";
import { isInlineGraphSource, replaceGraphFences } from "./inlineGraphs";
import CopyButton from "../CopyButton/CopyButton";

const assetBaseUrl = import.meta.env.BASE_URL;

const formatToolDuration = (seconds, formatNumber) => {
  if (seconds === undefined || seconds === null || seconds === "") return null;
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return null;
  return formatNumber(value, 2);
};

const hasLegacyMetadata = (artifact) =>
  Boolean(artifact?.deepquery_metadata) &&
  typeof artifact.deepquery_metadata === "object" &&
  Object.keys(artifact.deepquery_metadata).length > 0;

// Reports regenerated from legacy tool calls are remembered per tool call (browser only)
const REGENERATED_STORAGE_KEY = "deepquery-regenerated-reports";
const loadRegenerated = () => {
  try {
    return JSON.parse(localStorage.getItem(REGENERATED_STORAGE_KEY) || "{}") || {};
  } catch {
    return {};
  }
};

const LEGACY_LANGUAGES = ["English", "Spanish", "French", "German", "Italian", "Portuguese"];

// Summarises the background reports launched by a deep_query call for the tool block
const summarizeDeepQuery = (artifact, reports, reportsLoaded, regeneratedIds = []) => {
  if (artifact?.status === "rejected") {
    return { icon: "bi-x-circle", className: "deepquery-status-failed", text: artifact.error || "The analysis could not be started." };
  }
  // A regenerated analysis replaces the reports launched by the original tool call
  const ids = regeneratedIds.length > 0
    ? regeneratedIds
    : Array.isArray(artifact?.report_ids) ? artifact.report_ids : [];
  const missing = { missing: true, icon: "bi-arrow-repeat", className: "deepquery-status-muted", text: "" };
  const matched = reports.filter((report) => ids.includes(report.id));
  const running = { icon: "bi-stars", className: "deepquery-status-active deepquery-magic", text: "Analysis running in background..." };

  // Tool calls stored before background reports existed carry the old synchronous artifact
  if (ids.length === 0 && artifact && typeof artifact === "object" && !Array.isArray(artifact.report_ids)) {
    if (!hasLegacyMetadata(artifact)) return missing;
    return {
      legacy: true,
      hasMetadata: true,
      icon: "bi-clock-history",
      className: "deepquery-status-muted",
      text: "Legacy analysis (not run in background).",
    };
  }

  if (matched.length === 0) {
    if (reportsLoaded && ids.length > 0) return missing;
    return running;
  }

  const count = (status) => matched.filter((report) => report.status === status).length;
  if (matched.some((report) => report.status === REPORT_STATUS.PENDING || report.status === REPORT_STATUS.PROCESSING)) {
    const generating = matched.some((report) => report.stage === "generating_html");
    return { ...running, caption: generating ? "Generating report..." : "Extracting data..." };
  }
  const completed = count(REPORT_STATUS.COMPLETED);
  if (completed > 0) {
    const failed = count(REPORT_STATUS.FAILED);
    const cancelled = matched.length - completed - failed;
    if (failed + cancelled > 0) {
      // Partial success: some languages were generated and others did not finish
      const notReady = [
        failed > 0 ? `${failed} failed` : null,
        cancelled > 0 ? `${cancelled} cancelled` : null,
      ].filter(Boolean).join(", ");
      return {
        regenerable: true,
        icon: "bi-exclamation-triangle",
        className: failed > 0 ? "deepquery-status-failed" : "deepquery-status-muted",
        text: `${completed} of ${matched.length} reports ready (${notReady}).`,
      };
    }
    return {
      regenerable: true,
      icon: "bi-check-circle",
      className: "deepquery-status-completed",
      text: completed === 1 ? "Report ready." : `${completed} reports ready.`,
    };
  }
  if (count(REPORT_STATUS.FAILED) > 0) {
    return { regenerable: true, icon: "bi-x-circle", className: "deepquery-status-failed", text: "Analysis failed." };
  }
  return { regenerable: true, icon: "bi-slash-circle", className: "deepquery-status-muted", text: "Analysis cancelled." };
};

// deep_query report ids that already triggered a status refresh (one fetch per new launch)
const refreshedReportLaunches = new Set();

const ToolBlocks = ({
  blocks,
  resultsContainerRef,
  onOpenGraph,
  onOpenTable,
  onToolIconClick,
  receivedToolOutputs,
  onClipboardError,
}) => {
  const { config } = useConfig();
  const formatNumber = useNumberFormat();
  const { reports, reportsLoaded, setIsModalOpen, refreshReports, regenerateLegacy, regenerateFromQuestion } = useReport();

  // A new deep_query result: fetch the report status once so the badge and block update right away
  useEffect(() => {
    if (!Array.isArray(blocks)) return;
    blocks.forEach((toolCall) => {
      const ids = toolCall?.type === "tool" && toolCall.toolName === "deep_query" && Array.isArray(toolCall.artifact?.report_ids)
        ? toolCall.artifact.report_ids
        : [];
      if (ids.length === 0) return;
      const key = ids.join(",");
      if (refreshedReportLaunches.has(key) || ids.every((id) => reports.some((report) => report.id === id))) return;
      refreshedReportLaunches.add(key);
      refreshReports();
    });
  }, [blocks, reports, refreshReports]);
  const toolPublicTextKeys = useMemo(() => {
    const map = {};
    const tools = Array.isArray(config?.chatbot_tools) ? config.chatbot_tools : [];
    for (const tool of tools) {
      if (tool.name && tool.tool_public_text_key) {
        map[tool.name] = tool.tool_public_text_key;
      }
    }
    return map;
  }, [config?.chatbot_tools]);

  const [expandedTools, setExpandedTools] = useState({});
  const [regenerated, setRegenerated] = useState(loadRegenerated); // toolCallId -> [report ids]
  const [legacyPicker, setLegacyPicker] = useState(null); // toolCallId with the language picker open
  const [legacyLanguage, setLegacyLanguage] = useState("");
  const [legacyBusy, setLegacyBusy] = useState(false);

  const rememberRegenerated = (toolCallId, reportIds) => {
    setRegenerated((prev) => {
      const next = { ...prev, [toolCallId]: reportIds };
      try {
        localStorage.setItem(REGENERATED_STORAGE_KEY, JSON.stringify(next));
      } catch {
        // Storage full or unavailable: the mapping just lasts for this page view
      }
      return next;
    });
  };

  // The report of this tool call is gone: run its analysis again from the original question
  const handleRegenerateMissing = async (toolCall) => {
    const question = toolCall.args?.analysis_request;
    if (!question || legacyBusy) return;
    const languages = Array.isArray(toolCall.artifact?.languages) ? toolCall.artifact.languages : undefined;
    setLegacyBusy(true);
    const reportIds = await regenerateFromQuestion({ question, languages });
    setLegacyBusy(false);
    if (reportIds.length > 0) rememberRegenerated(toolCall.toolCallId, reportIds);
  };

  const handleRegenerate = async (toolCall, language) => {
    const metadata = toolCall.artifact?.deepquery_metadata;
    const cleaned = language.trim();
    if (!metadata || !cleaned || legacyBusy) return;
    setLegacyBusy(true);
    const reportId = await regenerateLegacy({
      question: toolCall.args?.analysis_request || "",
      deepqueryMetadata: metadata,
      language: cleaned,
    });
    setLegacyBusy(false);
    if (!reportId) return;
    rememberRegenerated(toolCall.toolCallId, [...(regenerated[toolCall.toolCallId] || []), reportId]);
    setLegacyPicker(null);
    setLegacyLanguage("");
  };

  const toggleToolExpand = (toolCallId) => {
    setExpandedTools((prev) => ({ ...prev, [toolCallId]: !prev[toolCallId] }));
  };

  const renderTooltip = (props, content) => (
    <Tooltip id="button-tooltip" {...props}>
      {content}
    </Tooltip>
  );

  const parseApiResponseToCsv = (apiResponse) => {
    if (
      !apiResponse ||
      typeof apiResponse === "string" ||
      Object.keys(apiResponse).length === 0
    )
      return [];

    const rows = Object.values(apiResponse);
    const headers = rows[0].map((item) => item.columnName);
    const dataRows = rows.map((row) => row.map((item) => item.value));

    return [headers, ...dataRows];
  };

  // function to download response as excel
  const handleDownloadExcel = async (apiResponse) => {
    const data = parseApiResponseToCsv(apiResponse);
    if (!data || data.length === 0) return;

    // new workbook & worksheet
    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet("Data");

    worksheet.addRows(data);
    const buffer = await workbook.xlsx.writeBuffer();

    // create a Blob; trigger download
    const blob = new Blob([buffer], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "denodo_data.xlsx";

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  };

  const renderToolIcons = (toolCall) => {
    if (toolCall.status !== "finished" && toolCall.status !== "error") return null;
    const artifact = toolCall.artifact || {};
    const fullExecutionResult = artifact.execution_result?.full;
    const icons = [];

    const handleToolClick = (extra = {}) => {
      onToolIconClick({
        modalTool: toolCall.toolName || "",
        modalToolCallId: toolCall.toolCallId,
        modalArtifact: artifact || {},
        error: artifact.error,
        error_message: artifact.error_message || (typeof artifact.error === "string" ? artifact.error : null),
        traceback: artifact.traceback,
        ...extra,
      });
    };

    // data_agent: backwards compatibility for chats saved before it was split into generate_vql / execute_vql / generate_graph
    const isVqlTool = ["generate_vql", "execute_vql", "generate_graph", "data_agent"].includes(toolCall.toolName);
    if (isVqlTool) {
      icons.push(
        <OverlayTrigger
          key="denodo"
          placement="left"
          delay={{ show: 250, hide: 400 }}
          overlay={(props) => renderTooltip(props, "Denodo")}
          container={resultsContainerRef?.current}
        >
          <img
            src={`${assetBaseUrl}tools/data_agent/denodo_icon_black.svg`}
            alt="Denodo Icon"
            width="20"
            height="20"
            className="cursor-pointer"
            onClick={() =>
              handleToolClick({
                vql: artifact.vql,
                query_explanation: artifact.query_explanation,
                tokens: artifact.tokens,
                total_tokens: artifact.total_tokens,
                input_tokens: artifact.input_tokens,
                output_tokens: artifact.output_tokens,
                ai_sdk_time: artifact.ai_sdk_time,
                llm_provider: artifact.llm_provider,
                llm_model: artifact.llm_model,
              })
            }
          />
        </OverlayTrigger>
      );
      if (fullExecutionResult) {
        icons.push(
          <OverlayTrigger
            key="table"
            placement="left"
            delay={{ show: 250, hide: 400 }}
            overlay={(props) => renderTooltip(props, "View execution result")}
            container={resultsContainerRef?.current}
          >
            <button
              type="button"
              className="ms-2 p-0 border-0 bg-transparent"
              onClick={() => onOpenTable(fullExecutionResult)}
              aria-label="View execution result"
            >
              <img
                src={`${assetBaseUrl}tools/data_agent/table.png`}
                alt="View execution result"
                width="20"
                height="20"
                className="cursor-pointer"
              />
            </button>
          </OverlayTrigger>
        );
        icons.push(
          <OverlayTrigger
            key="csv"
            placement="left"
            delay={{ show: 250, hide: 400 }}
            overlay={(props) => renderTooltip(props, "Download execution result as CSV")}
            container={resultsContainerRef?.current}
          >
            <CSVLink
              data={parseApiResponseToCsv(fullExecutionResult)}
              filename={"denodo_data.csv"}
              className="csv-link"
              target="_blank"
            >
              <img src={`${assetBaseUrl}tools/data_agent/csv_export.png`} alt="Export CSV" width="20" height="20" className="ms-2" />
            </CSVLink>
          </OverlayTrigger>
        );
        icons.push(
        <OverlayTrigger
          key="xlsx"
          placement="left"
          delay={{ show: 250, hide: 400 }}
          overlay={(props) => renderTooltip(props, "Download execution result as XLSX")}
          container={resultsContainerRef?.current}
        >
          <button
            type="button"
            className="ms-2 p-0 border-0 bg-transparent"
            onClick={() => handleDownloadExcel(fullExecutionResult)}
            aria-label="Download Excel"
          >
            <img
              src={`${assetBaseUrl}tools/data_agent/xlsx_export.png`}
              alt="Export XLSX"
              width="20"
              height="20"
              className="cursor-pointer"
            />
          </button>
        </OverlayTrigger>
      );
      }
      if (
        // data_agent: backwards compatibility — old chats stored the graph on the data_agent artifact
        (toolCall.toolName === "generate_graph" || toolCall.toolName === "data_agent") &&
        isInlineGraphSource(artifact.raw_graph)
      ) {
        icons.push(
          <OverlayTrigger
            key="graph"
            placement="left"
            delay={{ show: 250, hide: 400 }}
            overlay={(props) => renderTooltip(props, "View graph")}
            container={resultsContainerRef?.current}
          >
            <img
              src={`${assetBaseUrl}tools/data_agent/graph.png`}
              alt="View Graph"
              width="20"
              height="20"
              className="ms-2 cursor-pointer"
              onClick={() => onOpenGraph({ src: artifact.raw_graph, vql: artifact.vql || toolCall.args?.vql || "" })}
            />
          </OverlayTrigger>
        );
      }
    }

    if (toolCall.toolName === "metadata_search") {
      icons.push(
        <OverlayTrigger
          key="denodo-metadata"
          placement="left"
          delay={{ show: 250, hide: 400 }}
          overlay={(props) => renderTooltip(props, "Denodo")}
          container={resultsContainerRef?.current}
        >
          <img
            src={`${assetBaseUrl}tools/metadata_agent/denodo_icon_black.svg`}
            alt="Denodo Icon"
            width="20"
            height="20"
            className="cursor-pointer"
            onClick={() => handleToolClick({})}
          />
        </OverlayTrigger>
      );
    }

    if (toolCall.toolName === "deep_query") {
      icons.push(
        <OverlayTrigger
          key="denodo-deep"
          placement="left"
          delay={{ show: 250, hide: 400 }}
          overlay={(props) => renderTooltip(props, "Denodo")}
          container={resultsContainerRef?.current}
        >
          <img
            src={`${assetBaseUrl}tools/deep_query/denodo_icon_black.svg`}
            alt="Denodo Icon"
            width="20"
            height="20"
            className="cursor-pointer"
            onClick={() => handleToolClick({})}
          />
        </OverlayTrigger>
      );
    }

    if (toolCall.toolName === "knowledge_query") {
      icons.push(
        <OverlayTrigger
          key="knowledge"
          placement="left"
          delay={{ show: 250, hide: 400 }}
          overlay={(props) => renderTooltip(props, "Knowledge Base")}
          container={resultsContainerRef?.current}
        >
          <img
            src={`${assetBaseUrl}tools/knowledge_query/book.png`}
            alt="Knowledge Base"
            width="20"
            height="20"
            className="cursor-pointer"
            onClick={() =>
              handleToolClick({
                data_sources: artifact.data_sources,
              })
            }
          />
        </OverlayTrigger>
      );
    }

    return (
      <div className="d-flex flex-row align-items-center" style={{ gap: "8px" }}>
        {icons}
      </div>
    );
  };

  const getToolArgPreview = (toolCall) => {
    let argKey = toolPublicTextKeys[toolCall.toolName];

    // Fallback for data_agent
    if (!argKey) {
      if (toolCall.toolName === "data_agent") {
        argKey = "request"; 
      }
    }

    if (!argKey || !toolCall.args) return null;
    const value = toolCall.args[argKey];
    if (value === undefined || value === null) return null;
    const text = String(value).trim();
    return text || null;
  };

  const renderToolBox = (toolCall) => {
    const isExpanded = !!expandedTools[toolCall.toolCallId];
    const argPreview = getToolArgPreview(toolCall);
    const receivedContent = receivedToolOutputs?.[toolCall.toolCallId];
    const toolOutput = receivedContent != null ? receivedContent : toolCall.contentToLLM;
    const outputString = toolOutput 
      ? (typeof toolOutput === 'object' ? JSON.stringify(toolOutput, null, 2) : String(toolOutput))
      : "";
    const formattedDuration = formatToolDuration(toolCall.artifact?.tool_duration, formatNumber);
    const isDeepQuery = toolCall.toolName === "deep_query";
    const deepQueryStatus = isDeepQuery && toolCall.status !== "error"
      ? summarizeDeepQuery(toolCall.artifact, reports, reportsLoaded, regenerated[toolCall.toolCallId])
      : null;

    return (
      <div
        key={toolCall.toolCallId}
        className={`toolbox-container ${
          toolCall.status === "error" ? "toolbox-container-error" : ""
        }`}
      >
        <div className="d-flex align-items-center justify-content-between">
          <div className="d-flex align-items-center toolbox-header-main">
            {toolCall.status === "running" && !isDeepQuery && <Spinner size="sm" animation="border" />}
            <Badge bg="secondary" className="flex-shrink-0">{toolCall.toolName}</Badge>
            {argPreview && (
              <span className="toolbox-arg-preview" title={argPreview}>
                {argPreview}
              </span>
            )}
          </div>
          <div className="d-flex align-items-center" style={{ gap: "8px" }}>
            {renderToolIcons(toolCall)}
            <i
              className={`bi bi-chevron-${isExpanded ? 'up' : 'down'} carousel-arrow-inner`}
              onClick={(e) => {
                e.stopPropagation();
                toggleToolExpand(toolCall.toolCallId);
              }}
              style={{ cursor: "pointer" }}
            />
          </div>
        </div>
        {deepQueryStatus && (
          <>
            <div className={`deepquery-status ${deepQueryStatus.className}`}>
              {!deepQueryStatus.missing && <i className={`bi ${deepQueryStatus.icon}`} />}
              {deepQueryStatus.text && <span>{deepQueryStatus.text}</span>}
              {deepQueryStatus.caption && <span className="deepquery-caption">{deepQueryStatus.caption}</span>}
              {deepQueryStatus.legacy && deepQueryStatus.hasMetadata && (
                <button
                  type="button"
                  className="deepquery-legacy-btn"
                  onClick={() => setLegacyPicker(legacyPicker === toolCall.toolCallId ? null : toolCall.toolCallId)}
                >
                  <i className="bi bi-arrow-repeat me-1" />
                  Generate report
                </button>
              )}
              {(deepQueryStatus.missing || deepQueryStatus.regenerable) && toolCall.args?.analysis_request && (
                <button
                  type="button"
                  className="deepquery-regenerate-btn"
                  disabled={legacyBusy}
                  title={deepQueryStatus.regenerable ? "Run the analysis again from the original question" : undefined}
                  onClick={() => handleRegenerateMissing(toolCall)}
                >
                  <i className="bi bi-arrow-repeat me-1" />
                  {legacyBusy ? "Regenerating..." : "Regenerate"}
                </button>
              )}
              {!deepQueryStatus.legacy && !deepQueryStatus.missing && (
                <button
                  type="button"
                  className="deepquery-status-link"
                  onClick={() => setIsModalOpen(true)}
                >
                  Open DeepQuery Reports Manager
                </button>
              )}
            </div>
            {deepQueryStatus.legacy && legacyPicker === toolCall.toolCallId && (
              <form
                className="deepquery-legacy-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleRegenerate(toolCall, legacyLanguage);
                }}
              >
                <input
                  type="text"
                  className="deepquery-legacy-input"
                  placeholder="Language, e.g. English"
                  value={legacyLanguage}
                  maxLength={30}
                  autoFocus
                  onChange={(e) => {
                    if (/^[a-zA-Z\u00C0-\u024F\s-]*$/.test(e.target.value)) setLegacyLanguage(e.target.value);
                  }}
                />
                {LEGACY_LANGUAGES.map((option) => (
                  <button type="button" key={option} className="deepquery-legacy-chip" onClick={() => setLegacyLanguage(option)}>
                    {option}
                  </button>
                ))}
                <button type="submit" className="deepquery-legacy-go" disabled={!legacyLanguage.trim() || legacyBusy}>
                  {legacyBusy ? "Queuing..." : "Generate"}
                </button>
              </form>
            )}
          </>
        )}
        {isExpanded && (
          <div className="mt-2 border-top pt-2">
            <div className="mb-3">
              <div className="small fw-bold mb-1 text-muted">Input</div>
              {toolCall.args ? (
                <div className="args-container">
                  <div className="args-list">
                    {Object.entries(toolCall.args).map(([k, v]) => (
                      <React.Fragment key={k}>
                        <span className="arg-key">{k}</span>
                        <span className="arg-value">{String(v)}</span>
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              ) : <div className="text-muted small">No input arguments</div>}
            </div>

            {(toolCall.status === "finished" || toolCall.status === "error") && (
              <div>
                <div className="toolbox-output-header">
                  <span className="small fw-bold text-muted">Output</span>
                  {formattedDuration && (
                    <span className="toolbox-run-time">(ran in {formattedDuration}s)</span>
                  )}
                </div>
                <div className="args-container" style={{ maxHeight: '300px' }}>
                  <div className="d-flex justify-content-between align-items-start mb-1">
                    <span className="arg-key">result</span>
                    {outputString && (
                      <CopyButton
                        text={outputString}
                        tooltipText="Copy to clipboard"
                        placement="top"
                        className="ms-2"
                        onError={onClipboardError}
                      />
                    )}
                  </div>
                  <div className="arg-value w-100">
                    <pre className="mb-0" style={{ font: 'inherit', whiteSpace: 'pre-wrap' }}>
                      {outputString || "No output data found"}
                    </pre>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  if (!blocks || !blocks.length) return null;

  return (
    <div className="tool-blocks-container">
      {blocks.map((b, idx) => {
        if (b.type === "tool") {
          return renderToolBox(b);
        }
        return (
          <div key={`msg-${idx}`} className="intermediate-message">
            <div className="markdown-container">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={markdownComponents}
              >
                {replaceGraphFences(b.content)}
              </ReactMarkdown>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default ToolBlocks;
