import React, { useState, useEffect, useRef } from "react";
import Card from "react-bootstrap/Card";
import Button from "react-bootstrap/Button";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import Modal from "react-bootstrap/Modal";
import { CSVLink } from "react-csv";
import Badge from "react-bootstrap/Badge";
import Form from "react-bootstrap/Form";
import Toast from "react-bootstrap/Toast";
import ToastContainer from "react-bootstrap/ToastContainer";
import "./Results.css";
import { useConfig } from "../../contexts/ConfigContext";
import { usePDF } from "../../contexts/PDFContext";
import TableModal from "../TableModal";
import Spinner from "react-bootstrap/Spinner";

const Results = ({
  results,
  setResults,
  setCurrentQuestion,
  setQuestionType,
}) => {
  const [showModal, setShowModal] = useState(false);
  const [selectedResult, setSelectedResult] = useState(null);
  const resultsEndRef = useRef(null);
  const [showGraphModal, setShowGraphModal] = useState(false);
  const [selectedGraph, setSelectedGraph] = useState(null);
  const [showTableModal, setShowTableModal] = useState(false);
  const [selectedTableData, setSelectedTableData] = useState(null);
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [feedbackResult, setFeedbackResult] = useState(null);
  const [feedbackValue, setFeedbackValue] = useState("");
  const [feedbackDetails, setFeedbackDetails] = useState("");
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [showContextModal, setShowContextModal] = useState(false);
  const [selectedContextTables, setSelectedContextTables] = useState({
    used: [],
    unused: [],
    vql: "",
  });
  const [currentQuestionIndices, setCurrentQuestionIndices] = useState({});
  const { config } = useConfig();
  const { generatePDF } = usePDF();
  const [pdfGenerationStatus, setPdfGenerationStatus] = useState({});
  const [showPdfToast, setShowPdfToast] = useState(false);
  const [pdfToastMessage, setPdfToastMessage] = useState("");

  const scrollToBottom = () => {
    resultsEndRef.current.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (results.length > 0) {
      scrollToBottom();
    }
  }, [results]);

  const handleIconClick = (result) => {
    setSelectedResult(result);
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setSelectedResult(null);
  };

  const handleRelatedQuestionClick = (question) => {
    setCurrentQuestion(question);
    const type =
      selectedResult &&
      (selectedResult.questionType === "data" ||
        selectedResult.questionType === "metadata")
        ? selectedResult.questionType
        : "default";
    setQuestionType(type);
  };

  const handleDeepQueryQuestionClick = (question) => {
    setCurrentQuestion(question);
    setQuestionType("deep_query");
  };

  const handleGraphIconClick = (graph) => {
    setSelectedGraph(graph);
    setShowGraphModal(true);
  };

  const handleCloseGraphModal = () => {
    setShowGraphModal(false);
    setSelectedGraph(null);
  };

  const handleTableIconClick = (executionResult) => {
    setSelectedTableData(executionResult);
    setShowTableModal(true);
  };

  const handleCloseTableModal = () => {
    setShowTableModal(false);
    setSelectedTableData(null);
  };

  const handleFeedbackIconClick = (result) => {
    if (!config.chatbotFeedback) return;

    setFeedbackResult(result);
    setFeedbackValue("");
    setFeedbackDetails("");
    setShowFeedbackModal(true);
  };

  const handleCloseFeedbackModal = () => {
    setShowFeedbackModal(false);
    setFeedbackResult(null);
    setFeedbackValue("");
    setFeedbackDetails("");
  };

  const handleFeedbackSubmit = async () => {
    if (!config.chatbotFeedback || !feedbackResult || !feedbackResult.uuid)
      return;

    setFeedbackSubmitting(true);

    try {
      const response = await fetch("submit_feedback", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          uuid: feedbackResult.uuid,
          feedback_value: feedbackValue,
          feedback_details: feedbackDetails,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        // Update the result with feedback info in UI
        setResults((prevResults) =>
          prevResults.map((result) =>
            result.uuid === feedbackResult.uuid
              ? {
                  ...result,
                  feedback: feedbackValue,
                  feedbackDetails: feedbackDetails,
                }
              : result
          )
        );
        handleCloseFeedbackModal();
      } else {
        alert(`Error submitting feedback: ${data.message}`);
      }
    } catch (error) {
      console.error("Error submitting feedback:", error);
      alert("An error occurred while submitting feedback.");
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const handleContextIconClick = (tables, vql) => {
    if (!tables || tables.length === 0) return;

    const cleanVql = vql?.replace(/"/g, "").toLowerCase() || "";
    const usedTables = [];
    const unusedTables = [];

    tables.forEach((table) => {
      const cleanTable = table.replace(/"/g, "").toLowerCase();
      const isUsedInVql = cleanVql.includes(cleanTable);

      if (isUsedInVql) {
        usedTables.push(table);
      } else {
        unusedTables.push(table);
      }
    });

    setSelectedContextTables({
      used: usedTables,
      unused: unusedTables,
      vql: vql,
    });
    setShowContextModal(true);
  };

  const handleCloseContextModal = () => {
    setShowContextModal(false);
    setSelectedContextTables({ used: [], unused: [], vql: "" });
  };

  const handlePDFGeneration = async (result) => {
    if (!result.deepquery_metadata) {
      console.error("No deepquery_metadata available for PDF generation");
      return;
    }

    if (pdfGenerationStatus[result.uuid]) {
      console.log(
        "PDF generation is already in progress for this result. Ignoring repeated request."
      );
      return;
    }

    setPdfGenerationStatus((prevStatus) => ({
      ...prevStatus,
      [result.uuid]: true,
    }));
    setPdfToastMessage("Generating PDF...");
    setShowPdfToast(true);

    try {
      await generatePDF(result.deepquery_metadata, result.question);
      setPdfToastMessage("PDF generation finished.");
      setShowPdfToast(true);
    } catch (error) {
      console.error("Error generating PDF:", error);
      setPdfToastMessage("Error generating PDF.");
      setShowPdfToast(true);
    } finally {
      setTimeout(() => {
        setPdfGenerationStatus((prevStatus) => {
          const newStatus = { ...prevStatus };
          delete newStatus[result.uuid];
          return newStatus;
        });
        setShowPdfToast(false);
      }, 3000);
    }
  };

  const navigateRelatedQuestion = (resultIndex, direction) => {
    const result = results[resultIndex];
    if (!result.relatedQuestions || result.relatedQuestions.length <= 1) return;

    const currentIndex = currentQuestionIndices[resultIndex] || 0;
    const totalQuestions = result.relatedQuestions.length;

    let newIndex;
    if (direction === "next") {
      newIndex = (currentIndex + 1) % totalQuestions;
    } else {
      newIndex = currentIndex === 0 ? totalQuestions - 1 : currentIndex - 1;
    }

    // Add animation class based on direction
    const questionElement = document.querySelector(
      `[data-result-index="${resultIndex}"] .related-question-text`
    );
    if (questionElement) {
      questionElement.classList.remove("slide-in-left", "slide-in-right");
      questionElement.classList.add(
        direction === "next" ? "slide-in-right" : "slide-in-left"
      );

      // Remove animation class after animation completes
      setTimeout(() => {
        questionElement.classList.remove("slide-in-left", "slide-in-right");
      }, 400);
    }

    setCurrentQuestionIndices((prev) => ({
      ...prev,
      [resultIndex]: newIndex,
    }));
  };

  const renderTooltip = (props, content) => (
    <Tooltip id="button-tooltip" {...props}>
      {content}
    </Tooltip>
  );

  const getIcon = (result) => {
    if (result.isLoading) {
      return null;
    }

    const feedbackIcon = config.chatbotFeedback ? (
      <OverlayTrigger
        placement="left"
        delay={{ show: 250, hide: 400 }}
        overlay={(props) => renderTooltip(props, "Provide feedback")}
      >
        <img
          src="feedback.svg"
          alt="Feedback"
          width="20"
          height="20"
          className="ms-2 cursor-pointer"
          onClick={() => handleFeedbackIconClick(result)}
        />
      </OverlayTrigger>
    ) : null;

    const isGeneratingPdf = !!pdfGenerationStatus[result.uuid];

    switch (result.questionType?.toLowerCase()) {
      case "data":
      case "metadata":
      case "deep_query":
        return (
          <div className="d-flex flex-row align-items-center">
            <OverlayTrigger
              placement="left"
              delay={{ show: 250, hide: 400 }}
              overlay={(props) =>
                renderTooltip(
                  props,
                  result.questionType === "deep_query" ? "DeepQuery" : "Denodo"
                )
              }
            >
              <img
                src="favicon.ico"
                alt={
                  result.questionType === "deep_query"
                    ? "DeepQuery Icon"
                    : "Denodo Icon"
                }
                width="20"
                height="20"
                className="cursor-pointer"
                onClick={() => handleIconClick(result)}
              />
            </OverlayTrigger>
            {result.execution_result && (
              <>
                <OverlayTrigger
                  placement="left"
                  delay={{ show: 250, hide: 400 }}
                  overlay={(props) =>
                    renderTooltip(props, "View execution result")
                  }
                >
                  <img
                    src="table.png"
                    alt="View execution result"
                    width="20"
                    height="20"
                    className="ms-2 cursor-pointer"
                    onClick={() =>
                      handleTableIconClick(result.execution_result)
                    }
                  />
                </OverlayTrigger>
                <OverlayTrigger
                  placement="left"
                  delay={{ show: 250, hide: 400 }}
                  overlay={(props) =>
                    renderTooltip(props, "Download execution result")
                  }
                >
                  <CSVLink
                    data={parseApiResponseToCsv(result.execution_result)}
                    filename={"denodo_data.csv"}
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
            {result.graph &&
              result.graph.startsWith("data:image") &&
              result.graph.length > 300 && (
                <OverlayTrigger
                  placement="left"
                  delay={{ show: 250, hide: 400 }}
                  overlay={(props) => renderTooltip(props, "View graph")}
                >
                  <img
                    src="graph.png"
                    alt="View Graph"
                    width="20"
                    height="20"
                    className="ms-2 cursor-pointer"
                    onClick={() => handleGraphIconClick(result.graph)}
                  />
                </OverlayTrigger>
              )}
            {result.questionType === "deep_query" &&
              result.deepquery_metadata && (
                <OverlayTrigger
                  placement="left"
                  delay={{ show: 250, hide: 400 }}
                  overlay={(props) =>
                    renderTooltip(
                      props,
                      isGeneratingPdf
                        ? "Generating PDF..."
                        : "Generate PDF Report"
                    )
                  }
                >
                  <img
                    src="pdf.svg"
                    alt="Generate PDF Report"
                    width="20"
                    height="20"
                    className={`ms-2 ${
                      isGeneratingPdf
                        ? "cursor-not-allowed opacity-50"
                        : "cursor-pointer"
                    }`}
                    onClick={() => handlePDFGeneration(result)}
                    disabled={isGeneratingPdf}
                  />
                </OverlayTrigger>
              )}
            {result.pdf_url && (
              <OverlayTrigger
                placement="left"
                delay={{ show: 250, hide: 400 }}
                overlay={(props) => renderTooltip(props, "View PDF Report")}
              >
                <a
                  href={result.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-decoration-none"
                >
                  <img
                    src="pdf.svg"
                    alt="View PDF Report"
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
      case "kb":
        return (
          <div className="d-flex flex-row align-items-center">
            <OverlayTrigger
              placement="left"
              delay={{ show: 250, hide: 400 }}
              overlay={(props) => renderTooltip(props, "Knowledge Base")}
            >
              <img
                src="book.png"
                alt="Knowledge Base Icon"
                width="20"
                height="20"
                className="cursor-pointer"
                onClick={() => handleIconClick(result)}
              />
            </OverlayTrigger>
            {feedbackIcon}
          </div>
        );
      default:
        return (
          <div className="d-flex flex-row align-items-center">
            <OverlayTrigger
              placement="left"
              delay={{ show: 250, hide: 400 }}
              overlay={(props) => renderTooltip(props, "AI")}
            >
              <img
                src="ai.png"
                alt="AI Icon"
                width="20"
                height="20"
                className="cursor-pointer"
                onClick={() => handleIconClick(result)}
              />
            </OverlayTrigger>
            {feedbackIcon}
          </div>
        );
    }
  };

  const renderModalContent = (result) => {
    if (!result) return null;

    switch (result.questionType?.toLowerCase()) {
      case "data":
        return (
          <div>
            <p>
              <strong>Source:</strong> Denodo
            </p>
            <p>
              <strong>AI-Generated SQL:</strong> {result.vql || "N/A"}
            </p>
            <p>
              <strong>Query explanation:</strong>{" "}
              {result.query_explanation || "N/A"}
            </p>
            <p>
              <strong>AI SDK Tokens:</strong> {result.tokens || "N/A"}
            </p>
            <p>
              <strong>AI SDK Time:</strong>{" "}
              {result.ai_sdk_time ? `${result.ai_sdk_time}s` : "N/A"}
            </p>
          </div>
        );
      case "deep_query":
        return (
          <div>
            <p>
              <strong>Source:</strong> Denodo DeepQuery
            </p>
            {result.deepquery_metadata && (
              <>
                <p>
                  <strong>Planning LLM:</strong>{" "}
                  {result.deepquery_metadata.planning_provider &&
                  result.deepquery_metadata.planning_model
                    ? `${result.deepquery_metadata.planning_provider}/${result.deepquery_metadata.planning_model}`
                    : "N/A"}
                </p>
                <p>
                  <strong>Execution LLM:</strong>{" "}
                  {result.deepquery_metadata.executing_provider &&
                  result.deepquery_metadata.executing_model
                    ? `${result.deepquery_metadata.executing_provider}/${result.deepquery_metadata.executing_model}`
                    : "N/A"}
                </p>
                <p>
                  <strong>Number of tool calls:</strong>{" "}
                  {result.deepquery_metadata.tool_calls
                    ? result.deepquery_metadata.tool_calls.length
                    : "N/A"}
                </p>
              </>
            )}
            {result.total_execution_time && (
              <p>
                <strong>Execution time:</strong> {result.total_execution_time}s
              </p>
            )}
          </div>
        );
      case "metadata":
        return (
          <div>
            <p>
              <strong>Source:</strong> Denodo
            </p>
          </div>
        );
      case "kb":
        return (
          <div>
            <p>
              <strong>Source:</strong> Knowledge Base
            </p>
            <p>
              <strong>Vector store:</strong> {result.data_sources || "N/A"}
            </p>
          </div>
        );
      default:
        return (
          <div>
            <p>
              <strong>Source:</strong> AI
            </p>
            <p>
              <strong>Model:</strong> {result.chatbot_llm || "N/A"}
            </p>
          </div>
        );
    }
  };

  const renderTables = (tables, vql, icons = null) => {
    if (!tables || tables.length === 0) return icons;

    // Clean VQL by removing all quotes
    const cleanVql = vql?.replace(/"/g, "").toLowerCase() || "";

    // Separate used and unused tables
    const usedTables = [];
    const unusedTables = [];

    tables.forEach((table) => {
      const cleanTable = table.replace(/"/g, "").toLowerCase();
      const isUsedInVql = cleanVql.includes(cleanTable);

      if (isUsedInVql) {
        usedTables.push(table);
      } else {
        unusedTables.push(table);
      }
    });

    const renderTableButton = (table, index, isUsed = true) => {
      const cleanTable = table.replace(/"/g, "").toLowerCase();

      // Split the table name to get schema and table parts
      const tableParts = cleanTable.split(".");
      const schema = tableParts[0];
      const tableName = tableParts[1] || schema;

      // Create the URL for the Denodo Data Catalog
      const catalogUrl = config.dataCatalogUrl
        ? `${config.dataCatalogUrl}/#/view/${schema}/${tableName}`
        : null;

      return catalogUrl ? (
        <a
          key={index}
          href={catalogUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-decoration-none"
        >
          <Button
            variant={isUsed ? "success" : "secondary"}
            size="sm"
            bsPrefix="btn"
            className="me-1 mb-1 d-inline-flex align-items-center"
          >
            <img
              src="view.svg"
              alt="View"
              width="16"
              height="16"
              className="me-1"
            />
            {table.replace(/"/g, "")}
          </Button>
        </a>
      ) : (
        <Button
          key={index}
          variant={isUsed ? "success" : "secondary"}
          size="sm"
          bsPrefix="btn"
          className="me-1 mb-1 d-inline-flex align-items-center"
          style={
            isUsed ? { backgroundColor: "#143142", borderColor: "#143142" } : {}
          }
        >
          {table.replace(/"/g, "")}
        </Button>
      );
    };

    // Check if there are any table buttons to display
    const hasTableButtons = usedTables.length > 0 || unusedTables.length > 0;

    return (
      <>
        <div
          style={{
            backgroundColor: "transparent",
            padding: "1rem 0",
            marginBottom: "0",
          }}
        >
          <div
            className={`mb-2 d-flex ${
              hasTableButtons
                ? "justify-content-between"
                : "justify-content-end"
            } align-items-center`}
          >
            {hasTableButtons && (
              <div className="context-badges-container">
                {/* Show only used tables */}
                {usedTables.map((table, index) =>
                  renderTableButton(table, index, true)
                )}

                {/* Show "+X more" button if there are unused tables */}
                {unusedTables.length > 0 && (
                  <OverlayTrigger
                    placement="top"
                    delay={{ show: 250, hide: 400 }}
                    overlay={(props) =>
                      renderTooltip(props, "View all searched tables")
                    }
                  >
                    <Button
                      variant="outline-info"
                      size="sm"
                      className="me-1 mb-1 d-inline-flex align-items-center context-more-btn"
                      onClick={() => handleContextIconClick(tables, vql)}
                    >
                      +{unusedTables.length} more
                    </Button>
                  </OverlayTrigger>
                )}
              </div>
            )}
            {/* Icons on the same line */}
            {icons && (
              <div
                className="d-flex flex-row align-items-center"
                style={{ gap: "8px" }}
              >
                {icons}
              </div>
            )}
          </div>
        </div>
      </>
    );
  };

  const renderRelatedQuestions = (result, resultIndex) => {
    const hasRegularQuestions =
      result.relatedQuestions && result.relatedQuestions.length > 0;
    const hasDeepQueryQuestions =
      result.relatedQuestionsDeepQuery &&
      result.relatedQuestionsDeepQuery.length > 0;

    if (!hasRegularQuestions && !hasDeepQueryQuestions) return null;

    const currentIndex = currentQuestionIndices[resultIndex] || 0;
    const showCarouselArrows =
      hasRegularQuestions && result.relatedQuestions.length > 1;

    return (
      <div className="d-flex flex-column align-items-start mt-3">
        {/* Regular related questions carousel */}
        {hasRegularQuestions && (
          <div className="w-100 mb-2">
            <Button
              variant="outline-light"
              size="sm"
              className="text-start w-100 related-question-btn"
              onClick={() => {
                setSelectedResult(result);
                handleRelatedQuestionClick(
                  result.relatedQuestions[currentIndex]
                );
              }}
            >
              <div className="d-flex align-items-center justify-content-between w-100">
                {/* Left arrow */}
                {showCarouselArrows && (
                  <i
                    className="bi bi-chevron-left carousel-arrow-inner"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigateRelatedQuestion(resultIndex, "prev");
                    }}
                  />
                )}

                {/* Question text with animation */}
                <span className="related-question-text flex-grow-1 text-center">
                  {result.relatedQuestions[currentIndex]}
                </span>

                {/* Right arrow */}
                {showCarouselArrows && (
                  <i
                    className="bi bi-chevron-right carousel-arrow-inner"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigateRelatedQuestion(resultIndex, "next");
                    }}
                  />
                )}
              </div>
            </Button>
          </div>
        )}

        {/* DeepQuery related questions */}
        {hasDeepQueryQuestions &&
          result.relatedQuestionsDeepQuery.map((q, i) => (
            <Button
              key={`deep_query-${i}`}
              variant="outline-warning"
              size="sm"
              className="mb-2 text-start w-100 analyst-question-btn"
              onClick={() => {
                setSelectedResult(result);
                handleDeepQueryQuestionClick(q);
              }}
            >
              <div className="d-flex align-items-center justify-content-between w-100">
                <span
                  className="text-white flex-grow-1"
                  style={{ fontWeight: "500" }}
                >
                  {q}
                </span>
                <Badge className="analyst-mode-badge">DeepQuery</Badge>
              </div>
            </Button>
          ))}
      </div>
    );
  };

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

  return results.length === 0 ? null : (
    <div className="d-flex flex-column align-items-center w-100 text-light">
      {results.map((result, index) => (
        <React.Fragment key={index}>
          {/* User Question Card - Right aligned */}
          <div className="w-100 d-flex justify-content-center mb-3">
            <div className="w-70 d-flex justify-content-end">
              <Card
                style={{
                  backgroundColor: "transparent",
                  borderRadius: "1.25em",
                  color: "#112533",
                  boxShadow: "0 4px 12px rgba(0, 0, 0, 0.1)",
                  maxWidth: "80%",
                  width: "fit-content",
                }}
              >
                <Card.Body>
                  <Card.Text>{result.question}</Card.Text>
                </Card.Body>
              </Card>
            </div>
          </div>

          {/* AI Response Card - Left aligned */}
          <div className="w-100 d-flex justify-content-center mb-3">
            <div className="w-60 d-flex justify-content-start">
              <Card
                className={`w-100 ${
                  result.isLoading ? "card-loading-pulse" : ""
                }`}
                style={{
                  backgroundColor: "transparent",
                  color: "#112533",
                  borderRadius: "1.25em",
                  boxShadow: "0 4px 12px rgba(0, 0, 0, 0.1)",
                }}
                data-result-index={index}
              >
                <Card.Body className="position-relative">
                  <div className="card-content-area">
                    {/* Show nothing during initial phase */}
                    {result.queryPhase === "initial" && (
                      <div style={{ minHeight: "20px" }}></div>
                    )}

                    {/* Show intermediate query message during query phase */}
                    {result.queryPhase === "query" && (
                      <Card.Text className="query-loading-text">
                        <div className="d-flex align-items-start">
                          <Spinner
                            size="sm"
                            animation="border"
                            className="me-2 mt-1"
                          />
                          <span>
                            Querying the AI SDK:{" "}
                            <strong>{result.intermediateQuery}</strong>
                          </span>
                        </div>
                      </Card.Text>
                    )}

                    {/* Show streaming content during streaming phase - real-time updates without icons/badges */}
                    {result.queryPhase === "streaming" && (
                      <>
                        <Card.Text>
                          <div className="markdown-container">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {result.result}
                            </ReactMarkdown>
                          </div>
                        </Card.Text>
                      </>
                    )}

                    {/* Show complete content only when in complete phase */}
                    {result.queryPhase === "complete" && (
                      <>
                        {result.feedback && (
                          <div className="mb-2">
                            <Badge
                              bg={
                                result.feedback === "positive"
                                  ? "success"
                                  : "danger"
                              }
                              className="ms-2"
                            >
                              {result.feedback === "positive"
                                ? "Positive feedback"
                                : "Negative feedback"}
                            </Badge>
                          </div>
                        )}

                        <Card.Text>
                          <div className="markdown-container">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {result.result}
                            </ReactMarkdown>
                          </div>
                        </Card.Text>
                        {renderRelatedQuestions(result, index)}
                        {result.questionType === "data" ? (
                          renderTables(
                            result.tables_used,
                            result.vql,
                            getIcon(result)
                          )
                        ) : (
                          <>
                            <div
                              style={{
                                backgroundColor: "transparent",
                                padding: "1rem 0",
                                marginBottom: "0",
                              }}
                            >
                              <div className="mb-2 d-flex justify-content-end align-items-center">
                                <div
                                  className="d-flex flex-row align-items-center"
                                  style={{ gap: "8px" }}
                                >
                                  {getIcon(result)}
                                </div>
                              </div>
                            </div>
                          </>
                        )}
                      </>
                    )}
                  </div>
                </Card.Body>
              </Card>
            </div>
          </div>
        </React.Fragment>
      ))}
      <div ref={resultsEndRef} />

      <Modal
        show={showModal}
        onHide={handleCloseModal}
        size="lg"
        centered
        style={{ "--bs-modal-bg": "#112533" }}
        contentClassName="text-white border border-white"
      >
        <Modal.Header closeButton className="border-bottom border-white">
          <Modal.Title>Additional Information</Modal.Title>
        </Modal.Header>
        <Modal.Body>{renderModalContent(selectedResult)}</Modal.Body>
      </Modal>

      <Modal
        show={showGraphModal}
        onHide={handleCloseGraphModal}
        size="lg"
        centered
        style={{ "--bs-modal-bg": "#112533" }}
        contentClassName="text-white border border-white"
      >
        <Modal.Header closeButton className="border-bottom border-white">
          <Modal.Title>Graph View</Modal.Title>
        </Modal.Header>
        <Modal.Body className="text-center">
          {selectedGraph && (
            <img src={selectedGraph} alt="Graph" className="img-fluid" />
          )}
        </Modal.Body>
      </Modal>

      <TableModal
        show={showTableModal}
        handleClose={handleCloseTableModal}
        executionResult={selectedTableData}
      />

      <Modal
        show={showContextModal}
        onHide={handleCloseContextModal}
        size="lg"
        centered
        style={{ "--bs-modal-bg": "#112533" }}
        contentClassName="text-white border border-white"
      >
        <Modal.Header closeButton className="border-bottom border-white">
          <Modal.Title>Context Tables</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {selectedContextTables.used.length > 0 && (
            <div className="mb-4">
              <h6 className="text-white mb-3">
                <strong>
                  Used in Query ({selectedContextTables.used.length})
                </strong>
              </h6>
              <div className="context-badges-container">
                {selectedContextTables.used.map((table, index) => {
                  const cleanTable = table.replace(/"/g, "").toLowerCase();
                  const tableParts = cleanTable.split(".");
                  const schema = tableParts[0];
                  const tableName = tableParts[1] || schema;
                  const catalogUrl = config.dataCatalogUrl
                    ? `${config.dataCatalogUrl}/#/view/${schema}/${tableName}`
                    : null;

                  return catalogUrl ? (
                    <a
                      key={index}
                      href={catalogUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-decoration-none"
                    >
                      <Button
                        variant="success"
                        size="sm"
                        className="me-2 mb-2 d-inline-flex align-items-center"
                      >
                        <img
                          src="view.svg"
                          alt="View"
                          width="16"
                          height="16"
                          className="me-1"
                        />
                        {table.replace(/"/g, "")}
                      </Button>
                    </a>
                  ) : (
                    <Button
                      key={index}
                      variant="success"
                      size="sm"
                      className="me-2 mb-2 d-inline-flex align-items-center"
                      style={{
                        backgroundColor: "#143142",
                        borderColor: "#143142",
                      }}
                    >
                      {table.replace(/"/g, "")}
                    </Button>
                  );
                })}
              </div>
            </div>
          )}

          {selectedContextTables.unused.length > 0 && (
            <div className="mb-3">
              <h6 className="text-white mb-3">
                <strong>
                  Searched but Not Used ({selectedContextTables.unused.length})
                </strong>
              </h6>
              <div className="context-badges-container">
                {selectedContextTables.unused.map((table, index) => {
                  const cleanTable = table.replace(/"/g, "").toLowerCase();
                  const tableParts = cleanTable.split(".");
                  const schema = tableParts[0];
                  const tableName = tableParts[1] || schema;
                  const catalogUrl = config.dataCatalogUrl
                    ? `${config.dataCatalogUrl}/#/view/${schema}/${tableName}`
                    : null;

                  return catalogUrl ? (
                    <a
                      key={index}
                      href={catalogUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-decoration-none"
                    >
                      <Button
                        variant="secondary"
                        size="sm"
                        className="me-2 mb-2 d-inline-flex align-items-center"
                      >
                        <img
                          src="view.svg"
                          alt="View"
                          width="16"
                          height="16"
                          className="me-1"
                        />
                        {table.replace(/"/g, "")}
                      </Button>
                    </a>
                  ) : (
                    <Button
                      key={index}
                      variant="secondary"
                      size="sm"
                      className="me-2 mb-2 d-inline-flex align-items-center"
                    >
                      {table.replace(/"/g, "")}
                    </Button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="mt-4 pt-3 border-top border-secondary">
            <small className="text-white">
              <strong>Note:</strong> Views in green were used to find the
              answer, while grey tables were found in the database but found not
              relevant to the question.
            </small>
          </div>
        </Modal.Body>
      </Modal>

      {config.chatbotFeedback && (
        <Modal
          show={showFeedbackModal}
          onHide={handleCloseFeedbackModal}
          centered
          style={{ "--bs-modal-bg": "#112533" }}
          contentClassName="text-white border border-white"
        >
          <Modal.Header closeButton className="border-bottom border-white">
            <Modal.Title>Provide Feedback</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {feedbackResult && (
              <>
                <div className="mb-3">
                  <p className="mb-1">
                    <strong>Question:</strong>
                  </p>
                  <p>{feedbackResult.question}</p>
                </div>
                <Form>
                  <Form.Group className="mb-3">
                    <Form.Label>Was this answer helpful?</Form.Label>
                    <div>
                      <Form.Check
                        inline
                        type="radio"
                        id="positive-feedback"
                        label="Yes"
                        name="feedback"
                        value="positive"
                        checked={feedbackValue === "positive"}
                        onChange={() => setFeedbackValue("positive")}
                      />
                      <Form.Check
                        inline
                        type="radio"
                        id="negative-feedback"
                        label="No"
                        name="feedback"
                        value="negative"
                        checked={feedbackValue === "negative"}
                        onChange={() => setFeedbackValue("negative")}
                      />
                    </div>
                  </Form.Group>
                  <Form.Group className="mb-3">
                    <Form.Label>Additional details (optional)</Form.Label>
                    <Form.Control
                      as="textarea"
                      rows={3}
                      value={feedbackDetails}
                      onChange={(e) => setFeedbackDetails(e.target.value)}
                      placeholder="Please provide any additional comments..."
                    />
                  </Form.Group>
                </Form>
              </>
            )}
          </Modal.Body>
          <Modal.Footer className="border-top border-white">
            <Button variant="secondary" onClick={handleCloseFeedbackModal}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleFeedbackSubmit}
              disabled={!feedbackValue || feedbackSubmitting}
              style={{ backgroundColor: "#2D3E4B", borderColor: "#2D3E4B" }}
            >
              {feedbackSubmitting ? "Submitting..." : "Submit Feedback"}
            </Button>
          </Modal.Footer>
        </Modal>
      )}

      <ToastContainer position="bottom-end" className="p-3">
        <Toast
          show={showPdfToast}
          onClose={() => setShowPdfToast(false)}
          delay={3000}
          autohide
          className="custom-pdf-toast"
        >
          <Toast.Header closeButton>
            <strong className="me-auto">PDF Report</strong>
          </Toast.Header>
          <Toast.Body>{pdfToastMessage}</Toast.Body>
        </Toast>
      </ToastContainer>
    </div>
  );
};

export default Results;
