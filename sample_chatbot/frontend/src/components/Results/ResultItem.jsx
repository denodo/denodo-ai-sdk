import React, { useState } from "react";
import Card from "react-bootstrap/Card";
import Badge from "react-bootstrap/Badge";
import Spinner from "react-bootstrap/Spinner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import TableModal from "../TableModal";
import { useConfig } from "../../contexts/ConfigContext";
import ResultInfoModal from "./ResultInfoModal";
import GraphModal from "./GraphModal";
import ContextTablesModal from "./ContextTablesModal";
import FeedbackModal from "./FeedbackModal";
import RelatedQuestions from "./RelatedQuestions";
import ContextTablesStrip from "./ContextTablesStrip";
import ResultActions from "./ResultActions";

const ResultItem = ({
  result,
  index,
  setResults,
  setCurrentQuestion,
  setQuestionType,
  onGenerateReport,
  isGeneratingReport,
  resultsContainerRef,
}) => {
  const { config } = useConfig();

  const [showInfoModal, setShowInfoModal] = useState(false);
  const [showGraphModal, setShowGraphModal] = useState(false);
  const [graph, setGraph] = useState(null);
  const [showTableModal, setShowTableModal] = useState(false);
  const [tableData, setTableData] = useState(null);
  const [showContextModal, setShowContextModal] = useState(false);
  const [contextTables, setContextTables] = useState({
    tables: [],
    vql: "",
  });
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);

  const handleAskRelated = (question) => {
    setCurrentQuestion(question);
    const type =
      result &&
      (result.questionType === "data" || result.questionType === "metadata")
        ? result.questionType
        : "default";
    setQuestionType(type);
  };

  const handleAskDeepQuery = (question) => {
    setCurrentQuestion(question);
    setQuestionType("deep_query");
  };

  const handleOpenInfo = () => setShowInfoModal(true);
  const handleCloseInfo = () => setShowInfoModal(false);

  const handleOpenGraph = () => {
    if (!result.graph) return;
    setGraph(result.graph);
    setShowGraphModal(true);
  };
  const handleCloseGraph = () => {
    setShowGraphModal(false);
    setGraph(null);
  };

  const handleOpenTable = () => {
    if (!result.execution_result) return;
    setTableData(result.execution_result);
    setShowTableModal(true);
  };
  const handleCloseTable = () => {
    setShowTableModal(false);
    setTableData(null);
  };

  const handleOpenContext = (tables, vql) => {
    if (!tables || tables.length === 0) return;
    setContextTables({ tables, vql });
    setShowContextModal(true);
  };
  const handleCloseContext = () => {
    setShowContextModal(false);
    setContextTables({ tables: [], vql: "" });
  };

  const handleOpenFeedback = () => {
    if (!config.chatbotFeedback) return;
    setShowFeedbackModal(true);
  };
  const handleCloseFeedback = () => {
    setShowFeedbackModal(false);
  };

  const renderContent = () => {
    if (result.queryPhase === "initial") {
      return <div style={{ minHeight: "20px" }} />;
    }

    if (result.queryPhase === "query") {
      return (
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
      );
    }

    if (result.queryPhase === "streaming") {
      return (
        <Card.Text>
          <div className="markdown-container">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {result.result}
            </ReactMarkdown>
          </div>
        </Card.Text>
      );
    }

    if (result.queryPhase === "complete") {
      return (
        <>
          {result.feedback && (
            <div className="mb-2">
              <Badge
                bg={result.feedback === "positive" ? "success" : "danger"}
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
          <RelatedQuestions
            relatedQuestions={result.relatedQuestions}
            relatedQuestionsDeepQuery={result.relatedQuestionsDeepQuery}
            onAskRelated={handleAskRelated}
            onAskDeepQuery={handleAskDeepQuery}
          />
          {result.questionType === "data" ? (
            <ContextTablesStrip
              tables={result.tables_used}
              vql={result.vql}
              dataCatalogUrl={config.dataCatalogUrl}
              icons={
                <ResultActions
                  result={result}
                  config={config}
                  isGeneratingReport={isGeneratingReport}
                  onOpenInfo={handleOpenInfo}
                  onOpenTable={handleOpenTable}
                  onOpenGraph={handleOpenGraph}
                  onGenerateReport={onGenerateReport}
                  onFeedback={handleOpenFeedback}
                    resultsContainerRef={resultsContainerRef}
                />
              }
              onOpenContext={handleOpenContext}
            />
          ) : (
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
                  <ResultActions
                    result={result}
                    config={config}
                    isGeneratingReport={isGeneratingReport}
                    onOpenInfo={handleOpenInfo}
                    onOpenTable={handleOpenTable}
                    onOpenGraph={handleOpenGraph}
                    onGenerateReport={onGenerateReport}
                    onFeedback={handleOpenFeedback}
                    resultsContainerRef={resultsContainerRef}
                  />
                </div>
              </div>
            </div>
          )}
        </>
      );
    }

    return null;
  };

  return (
    <>
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
              <div className="card-content-area">{renderContent()}</div>
            </Card.Body>
          </Card>
        </div>
      </div>

      <ResultInfoModal
        show={showInfoModal}
        onClose={handleCloseInfo}
        result={result}
      />
      <GraphModal
        show={showGraphModal}
        graph={graph}
        onClose={handleCloseGraph}
      />
      <TableModal
        show={showTableModal}
        handleClose={handleCloseTable}
        executionResult={tableData}
      />
      <ContextTablesModal
        show={showContextModal}
        onClose={handleCloseContext}
        tables={contextTables.tables}
        vql={contextTables.vql}
        dataCatalogUrl={config.dataCatalogUrl}
      />
      <FeedbackModal
        show={showFeedbackModal}
        onClose={handleCloseFeedback}
        result={result}
        setResults={setResults}
        feedbackEnabled={config.chatbotFeedback}
      />
    </>
  );
};

export default ResultItem;


