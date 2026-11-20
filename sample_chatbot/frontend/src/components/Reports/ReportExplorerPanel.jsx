import React, { useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import Badge from "react-bootstrap/Badge";
import Spinner from "react-bootstrap/Spinner";
import Alert from "react-bootstrap/Alert";
import { useReport } from "../../contexts/ReportContext";
import { SqlBlock } from "../Chat/Modals/AdditionalInformationModal";
import { TableView } from "../Chat/Modals/TableModal";
import { GraphView } from "../Chat/Modals/GraphModal";
import ReportPanelShell from "./ReportPanelShell";

// execution_result is stored either as a {full, llm} bundle or as plain rows
const getFullRows = (executionResult) => {
  if (!executionResult || typeof executionResult !== "object") return null;
  if (executionResult.full && Object.keys(executionResult.full).length > 0) return executionResult.full;
  if (executionResult.llm && Object.keys(executionResult.llm).length > 0) return executionResult.llm;
  if ("full" in executionResult || "llm" in executionResult) return null;
  return Object.keys(executionResult).length > 0 ? executionResult : null;
};

// Turns the stored deepquery_metadata into the list of data sources used by the analysis
export const extractDataSources = (metadata) => {
  const toolCalls = Array.isArray(metadata?.tool_calls) ? metadata.tool_calls : [];
  return toolCalls
    .map((toolCall, index) => {
      const output = toolCall?.output || {};
      const rows = getFullRows(output.execution_result);
      const graph =
        typeof output.raw_graph === "string" && output.raw_graph.startsWith("data:image")
          ? output.raw_graph
          : null;
      return {
        key: toolCall?.tool_id || `tool-${index}`,
        toolId: toolCall?.tool_id,
        toolName: toolCall?.tool_name,
        description: toolCall?.input?.action_description || toolCall?.input?.action || null,
        explanation: output.query_explanation || null,
        vql: output.sql_query || null,
        rows,
        rowCount: rows ? Object.keys(rows).length : 0,
        graph,
        failed: Boolean(toolCall?.error),
      };
    })
    .filter((source) => source.vql || source.rows || source.graph);
};

// Provider/model that produced the analysis, from the stored deepquery_metadata
export const extractModelLabel = (metadata) => {
  const join = (provider, model) => [provider, model].filter(Boolean).join("/");
  return (
    join(metadata?.actual_executing_provider, metadata?.actual_executing_model) ||
    join(metadata?.executing_provider, metadata?.executing_model) ||
    join(metadata?.llm_provider, metadata?.llm_model) ||
    null
  );
};

// Additional Information view. `detail` ({kind: 'table'|'graph', index}) is controlled by the manager so
// that Back / Esc step out of the drill-down before leaving the view.
const ReportExplorerPanel = ({ report, detail, onDetail, onBack, onBackToList }) => {
  const { fetchAnalysis } = useReport();
  const [state, setState] = useState({ loading: true, error: null, data: null });

  const reportId = report?.id;

  useEffect(() => {
    if (!reportId) return undefined;
    let cancelled = false;
    setState({ loading: true, error: null, data: null });
    fetchAnalysis(reportId)
      .then((data) => {
        if (!cancelled) setState({ loading: false, error: null, data });
      })
      .catch((error) => {
        if (cancelled) return;
        const message =
          error?.response?.data?.error || error?.message || "The analysis data could not be loaded.";
        setState({ loading: false, error: message, data: null });
      });
    return () => {
      cancelled = true;
    };
  }, [reportId, fetchAnalysis]);

  const sources = useMemo(() => extractDataSources(state.data?.deepquery_metadata), [state.data]);
  const modelLabel = useMemo(() => extractModelLabel(state.data?.deepquery_metadata), [state.data]);
  const title = state.data?.title || report?.title || report?.question || "DeepQuery analysis";

  const crumbs = [
    { label: "Reports", onClick: onBackToList },
    { label: title, onClick: detail ? () => onDetail(null) : undefined },
    { label: "Additional Information", onClick: detail ? () => onDetail(null) : undefined },
  ];
  const detailSource = detail ? sources[detail.index] : null;
  if (detailSource) {
    crumbs.push({
      label: `${detail.kind === "graph" ? "Graph" : "Table"} #${detail.index + 1}`,
    });
  }
  // The "Additional Information" crumb is the current one while no drill-down is open
  const shellCrumbs = crumbs.map((crumb, index) => ({
    ...crumb,
    onClick: index === 0 || detailSource ? crumb.onClick : undefined,
  }));

  return (
    <ReportPanelShell crumbs={shellCrumbs} onBack={onBack} scroll>
      {state.loading && (
        <div className="text-center py-5">
          <Spinner animation="border" size="sm" className="me-2" />
          Loading additional information...
        </div>
      )}

      {state.error && <Alert variant="warning">{state.error}</Alert>}

      {state.data && detailSource && (
        <div className="rcx-detail">
          <div className="rcx-detail-head">
            <span className="rcx-source-index">{detail.index + 1}</span>
            <span className="fw-semibold">{detailSource.toolName || "Query"}</span>
            {detail.kind === "table" && (
              <Badge bg="light" text="dark" className="border ms-2">
                {detailSource.rowCount} row{detailSource.rowCount === 1 ? "" : "s"}
              </Badge>
            )}
          </div>
          {detailSource.description && <div className="text-muted small mb-3">{detailSource.description}</div>}
          {detail.kind === "graph" ? (
            <GraphView graph={detailSource.graph} />
          ) : (
            <TableView executionResult={detailSource.rows} />
          )}
        </div>
      )}

      {state.data && !detailSource && (
        <>
          <div className="rcx-summary">
            <div className="fw-semibold">{title}</div>
            {state.data.question && <div className="text-muted small mt-1">{state.data.question}</div>}
            <div className="small mt-2">
              <Badge bg="secondary" className="me-2">
                {sources.length} data source{sources.length === 1 ? "" : "s"}
              </Badge>
              {report?.language && <Badge bg="light" text="dark" className="border me-2">{report.language}</Badge>}
            </div>
            {modelLabel && (
              <div className="small mt-2">
                <span className="text-muted">Model:</span> <code>{modelLabel}</code>
              </div>
            )}
          </div>

          {sources.length === 0 ? (
            <div className="text-center text-muted py-4">
              The analysis did not store any queries, tables or graphs.
            </div>
          ) : (
            sources.map((source, index) => (
              <div className="rcx-source" key={source.key}>
                <div className="d-flex align-items-center justify-content-between flex-wrap gap-2">
                  <div className="fw-semibold">
                    <span className="rcx-source-index">{index + 1}</span>
                    {source.toolName || "Query"}
                    {source.toolId && <code className="ms-2 small">{source.toolId}</code>}
                    {source.failed && <Badge bg="danger" className="ms-2">Failed</Badge>}
                  </div>
                  <div className="d-flex gap-2">
                    {source.rows && (
                      <button type="button" className="rcc-chip-btn" onClick={() => onDetail({ kind: "table", index })}>
                        <i className="bi bi-table me-1" />
                        Table ({source.rowCount} row{source.rowCount === 1 ? "" : "s"})
                      </button>
                    )}
                    {source.graph && (
                      <button type="button" className="rcc-chip-btn" onClick={() => onDetail({ kind: "graph", index })}>
                        <i className="bi bi-bar-chart-line me-1" />
                        Graph
                      </button>
                    )}
                  </div>
                </div>
                {source.description && <div className="text-muted small mt-1">{source.description}</div>}
                {source.explanation && <div className="small mt-2">{source.explanation}</div>}
                {source.vql && <SqlBlock sql={source.vql} />}
              </div>
            ))
          )}
        </>
      )}
    </ReportPanelShell>
  );
};

ReportExplorerPanel.propTypes = {
  report: PropTypes.shape({
    id: PropTypes.string,
    title: PropTypes.string,
    question: PropTypes.string,
    language: PropTypes.string,
  }).isRequired,
  detail: PropTypes.shape({ kind: PropTypes.string, index: PropTypes.number }),
  onDetail: PropTypes.func.isRequired,
  onBack: PropTypes.func.isRequired,
  onBackToList: PropTypes.func.isRequired,
};

export default ReportExplorerPanel;
