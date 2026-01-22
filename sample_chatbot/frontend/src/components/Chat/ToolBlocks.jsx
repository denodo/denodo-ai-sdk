import React, { useState } from "react";
import Card from "react-bootstrap/Card";
import Badge from "react-bootstrap/Badge";
import Spinner from "react-bootstrap/Spinner";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";
import Button from "react-bootstrap/Button";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CSVLink } from "react-csv";
import "./ToolBlocks.css";

const ToolBlocks = ({
  blocks,
  result,
  isGeneratingReport,
  onGenerateReport,
  resultsContainerRef,
  onOpenGraph,
  onOpenTable,
  onToolIconClick,
}) => {
  const [expandedTools, setExpandedTools] = useState({});
  const [paletteSelectorOpenId, setPaletteSelectorOpenId] = useState(null);
  const [selectedPalette, setSelectedPalette] = useState("");

  const paletteOptions = ["red", "blue", "green", "black"];

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

  const renderToolIcons = (toolCall) => {
    if (toolCall.status !== "finished" && toolCall.status !== "error") return null;
    const artifact = toolCall.artifact || {};
    const icons = [];

    const handleToolClick = (extra = {}) => {
      onToolIconClick({
        modalTool: toolCall.toolName || "",
        modalArtifact: artifact || {},
        error: artifact.error,
        error_message: artifact.error_message || (typeof artifact.error === "string" ? artifact.error : null),
        traceback: artifact.traceback,
        ...extra,
      });
    };

    if (toolCall.toolName === "data_query") {
      icons.push(
        <OverlayTrigger
          key="denodo"
          placement="left"
          delay={{ show: 250, hide: 400 }}
          overlay={(props) => renderTooltip(props, "Denodo")}
          container={resultsContainerRef?.current}
        >
          <img
            src="favicon.ico"
            alt="Denodo Icon"
            width="20"
            height="20"
            className="cursor-pointer"
            onClick={() =>
              handleToolClick({
                vql: artifact.vql,
                query_explanation: artifact.query_explanation,
                tokens: artifact.tokens,
                ai_sdk_time: artifact.ai_sdk_time,
                llm_provider: artifact.llm_provider,
                llm_model: artifact.llm_model,
              })
            }
          />
        </OverlayTrigger>
      );
      if (artifact.execution_result) {
        icons.push(
          <OverlayTrigger
            key="table"
            placement="left"
            delay={{ show: 250, hide: 400 }}
            overlay={(props) => renderTooltip(props, "View execution result")}
            container={resultsContainerRef?.current}
          >
            <img
              src="table.png"
              alt="View execution result"
              width="20"
              height="20"
              className="ms-2 cursor-pointer"
              onClick={() => onOpenTable(artifact.execution_result)}
            />
          </OverlayTrigger>
        );
        icons.push(
          <OverlayTrigger
            key="csv"
            placement="left"
            delay={{ show: 250, hide: 400 }}
            overlay={(props) => renderTooltip(props, "Download execution result")}
            container={resultsContainerRef?.current}
          >
            <CSVLink
              data={parseApiResponseToCsv(artifact.execution_result)}
              filename={"denodo_data.csv"}
              className="csv-link"
              target="_blank"
            >
              <img src="export.png" alt="Export CSV" width="20" height="20" className="ms-2" />
            </CSVLink>
          </OverlayTrigger>
        );
      }
      if (
        artifact.raw_graph &&
        artifact.raw_graph.startsWith("data:image") &&
        artifact.raw_graph.length > 300
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
              src="graph.png"
              alt="View Graph"
              width="20"
              height="20"
              className="ms-2 cursor-pointer"
              onClick={() => onOpenGraph(artifact.raw_graph)}
            />
          </OverlayTrigger>
        );
      }
    }

    if (toolCall.toolName === "metadata_query") {
      icons.push(
        <OverlayTrigger
          key="denodo-metadata"
          placement="left"
          delay={{ show: 250, hide: 400 }}
          overlay={(props) => renderTooltip(props, "Denodo")}
          container={resultsContainerRef?.current}
        >
          <img
            src="favicon.ico"
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
            src="favicon.ico"
            alt="Denodo Icon"
            width="20"
            height="20"
            className="cursor-pointer"
            onClick={() =>
              handleToolClick({
                deepquery_metadata: artifact.deepquery_metadata,
                total_execution_time: artifact.total_execution_time,
              })
            }
          />
        </OverlayTrigger>
      );

      if (artifact.deepquery_metadata) {
        const deepQueryResult = { ...result, deepquery_metadata: artifact.deepquery_metadata };
        const isGenerating = isGeneratingReport && result.uuid === deepQueryResult.uuid;
        const isPaletteOpen = paletteSelectorOpenId === toolCall.toolCallId;

        icons.push(
          <div key="pdf-wrapper" className="position-relative d-flex align-items-center">
            <OverlayTrigger
              placement="left"
              delay={{ show: 250, hide: 400 }}
              overlay={(props) =>
                renderTooltip(props, isGenerating ? "Generating PDF..." : "Generate PDF Report")
              }
              container={resultsContainerRef?.current}
            >
              <img
                src="pdf.svg"
                alt="Generate PDF Report"
                width="20"
                height="20"
                className={`ms-2 ${isGenerating ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
                onClick={() => {
                  if (isGenerating) return;
                  setPaletteSelectorOpenId((prev) => (prev === toolCall.toolCallId ? null : toolCall.toolCallId));
                }}
              />
            </OverlayTrigger>
            {isPaletteOpen && (
              <div className="report-palette-popup">
                <span className="report-palette-label">Color palette:</span>
                <select
                  className="form-select form-select-sm report-palette-select"
                  value={selectedPalette}
                  onChange={(e) => setSelectedPalette(e.target.value)}
                >
                  <option value="" disabled>
                    Select...
                  </option>
                  {paletteOptions.map((palette) => (
                    <option key={palette} value={palette}>
                      {palette.charAt(0).toUpperCase() + palette.slice(1)}
                    </option>
                  ))}
                </select>
                <Button
                  variant="dark"
                  size="sm"
                  className="mt-2 w-100"
                  disabled={isGeneratingReport || !selectedPalette}
                  onClick={() => {
                    if (!selectedPalette || isGeneratingReport) return;
                    setPaletteSelectorOpenId(null);
                    onGenerateReport(deepQueryResult, selectedPalette);
                  }}
                >
                  Generate
                </Button>
              </div>
            )}
          </div>
        );
      }
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
            src="book.png"
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

  const renderToolBox = (toolCall) => {
    const isExpanded = !!expandedTools[toolCall.toolCallId];
    return (
      <div
        key={toolCall.toolCallId}
        className={`toolbox-container ${
          toolCall.status === "error" ? "toolbox-container-error" : ""
        }`}
      >
        <div className="d-flex align-items-center justify-content-between">
          <div className="d-flex align-items-center" style={{ gap: "8px" }}>
            {toolCall.status === "running" && <Spinner size="sm" animation="border" />}
            <Badge bg="secondary">{toolCall.toolName}</Badge>
          </div>
          <div className="d-flex align-items-center" style={{ gap: "8px" }}>
            {renderToolIcons(toolCall)}
            <i
              className="bi bi-chevron-down carousel-arrow-inner"
              onClick={(e) => {
                e.stopPropagation();
                toggleToolExpand(toolCall.toolCallId);
              }}
              style={{ cursor: "pointer" }}
            />
          </div>
        </div>
        {isExpanded && (
          <div className="mt-2">
            {toolCall.args && (
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
            )}
          </div>
        )}
      </div>
    );
  };

  if (!blocks || !blocks.length) return null;

  return (
    <div className="mt-2">
      {blocks.map((b, idx) =>
        b.type === "tool" ? (
          renderToolBox(b)
        ) : (
          <Card.Text key={`msg-${idx}`}>
            <div className="markdown-container">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{b.content}</ReactMarkdown>
            </div>
          </Card.Text>
        )
      )}
    </div>
  );
};

export default ToolBlocks;
