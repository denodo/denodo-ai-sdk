import React, { useState } from "react";
import Button from "react-bootstrap/Button";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";
import { CSVLink } from "react-csv";

const renderTooltip = (content) => (
  <Tooltip id="result-action-tooltip">{content}</Tooltip>
);

const parseApiResponseToCsv = (apiResponse) => {
  if (
    !apiResponse ||
    typeof apiResponse === "string" ||
    Object.keys(apiResponse).length === 0
  ) {
    return [];
  }

  const rows = Object.values(apiResponse);
  const headers = rows[0].map((item) => item.columnName);
  const dataRows = rows.map((row) => row.map((item) => item.value));

  return [headers, ...dataRows];
};

const ResultActions = ({
  result,
  config,
  isGeneratingReport,
  onOpenInfo,
  onOpenTable,
  onOpenGraph,
  onGenerateReport,
  onFeedback,
  resultsContainerRef,
}) => {
  const [showPaletteSelector, setShowPaletteSelector] = useState(false);
  const [selectedPalette, setSelectedPalette] = useState("");

  const feedbackIcon = config.chatbotFeedback ? (
    <OverlayTrigger
      placement="left"
      delay={{ show: 250, hide: 400 }}
      overlay={renderTooltip("Provide feedback")}
      container={resultsContainerRef && resultsContainerRef.current}
    >
      <img
        src="feedback.svg"
        alt="Feedback"
        width="20"
        height="20"
        className="ms-2 cursor-pointer"
        onClick={onFeedback}
      />
    </OverlayTrigger>
  ) : null;

  const paletteOptions = ["red", "blue", "green", "black"];

  const renderBaseIcon = () => {
    const type = result.questionType?.toLowerCase();

    if (type === "data" || type === "metadata" || type === "deep_query") {
      return (
        <OverlayTrigger
          placement="left"
          delay={{ show: 250, hide: 400 }}
          overlay={renderTooltip(
            type === "deep_query" ? "DeepQuery" : "Denodo"
          )}
          container={resultsContainerRef && resultsContainerRef.current}
        >
          <img
            src="favicon.ico"
            alt={type === "deep_query" ? "DeepQuery Icon" : "Denodo Icon"}
            width="20"
            height="20"
            className="cursor-pointer"
            onClick={onOpenInfo}
          />
        </OverlayTrigger>
      );
    }

    if (type === "kb") {
      return (
        <OverlayTrigger
          placement="left"
          delay={{ show: 250, hide: 400 }}
          overlay={renderTooltip("Knowledge Base")}
          container={resultsContainerRef && resultsContainerRef.current}
        >
          <img
            src="book.png"
            alt="Knowledge Base Icon"
            width="20"
            height="20"
            className="cursor-pointer"
            onClick={onOpenInfo}
          />
        </OverlayTrigger>
      );
    }

    return (
      <OverlayTrigger
        placement="left"
        delay={{ show: 250, hide: 400 }}
        overlay={renderTooltip("AI")}
        container={resultsContainerRef && resultsContainerRef.current}
      >
        <img
          src="ai.png"
          alt="AI Icon"
          width="20"
          height="20"
          className="cursor-pointer"
          onClick={onOpenInfo}
        />
      </OverlayTrigger>
    );
  };

  const type = result.questionType?.toLowerCase();

  const showTableActions = !!result.execution_result;
  const showGraph =
    result.graph &&
    result.graph.startsWith("data:image") &&
    result.graph.length > 300;

  const showDeepQueryReport =
    type === "deep_query" && result.deepquery_metadata;

  return (
    <div className="d-flex flex-row align-items-center position-relative">
      {renderBaseIcon()}
      {showTableActions && (
        <>
          <OverlayTrigger
            placement="left"
            delay={{ show: 250, hide: 400 }}
            overlay={renderTooltip("View execution result")}
            container={resultsContainerRef && resultsContainerRef.current}
          >
            <img
              src="table.png"
              alt="View execution result"
              width="20"
              height="20"
              className="ms-2 cursor-pointer"
              onClick={onOpenTable}
            />
          </OverlayTrigger>
          <OverlayTrigger
            placement="left"
            delay={{ show: 250, hide: 400 }}
            overlay={renderTooltip("Download execution result")}
            container={resultsContainerRef && resultsContainerRef.current}
          >
            <CSVLink
              data={parseApiResponseToCsv(result.execution_result)}
              filename="denodo_data.csv"
              className="csv-link"
              target="_blank"
            >
              <img
                src="export.png"
                alt="Export CSV"
                width="20"
                height="20"
                className="ms-2"
              />
            </CSVLink>
          </OverlayTrigger>
        </>
      )}

      {showGraph && (
        <OverlayTrigger
          placement="left"
          delay={{ show: 250, hide: 400 }}
          overlay={renderTooltip("View graph")}
          container={resultsContainerRef && resultsContainerRef.current}
        >
          <img
            src="graph.png"
            alt="View Graph"
            width="20"
            height="20"
            className="ms-2 cursor-pointer"
            onClick={onOpenGraph}
          />
        </OverlayTrigger>
      )}

      {showDeepQueryReport && (
        <>
          <OverlayTrigger
            placement="left"
            delay={{ show: 250, hide: 400 }}
            overlay={renderTooltip(
              isGeneratingReport ? "Generating report..." : "Generate Report"
            )}
            container={resultsContainerRef && resultsContainerRef.current}
          >
            <img
              src="pdf.svg"
              alt="Generate Report"
              width="20"
              height="20"
              className={`ms-2 ${
                isGeneratingReport
                  ? "cursor-not-allowed opacity-50"
                  : "cursor-pointer"
              }`}
              onClick={() => {
                if (isGeneratingReport) return;
                setShowPaletteSelector((prev) => !prev);
              }}
            />
          </OverlayTrigger>
          {showPaletteSelector && (
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
                  setShowPaletteSelector(false);
                  onGenerateReport(result, selectedPalette);
                }}
              >
                Generate
              </Button>
            </div>
          )}
        </>
      )}

      {result.pdf_url && (
        <OverlayTrigger
          placement="left"
          delay={{ show: 250, hide: 400 }}
          overlay={renderTooltip("View Report")}
          container={resultsContainerRef && resultsContainerRef.current}
        >
          <a
            href={result.pdf_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-decoration-none"
          >
            <img
              src="pdf.svg"
              alt="View Report"
              width="20"
              height="20"
              className="ms-2"
            />
          </a>
        </OverlayTrigger>
      )}

      {feedbackIcon}
    </div>
  );
};

export default ResultActions;


