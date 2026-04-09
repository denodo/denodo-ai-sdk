import React, { useState } from "react";
import PropTypes from "prop-types";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Card from "react-bootstrap/Card";
import Spinner from "react-bootstrap/Spinner";
import TableModal from "./TableModal";
import { useConfig } from "../../contexts/ConfigContext";
import AdditionalInformationModal from "./AdditionalInformationModal";
import GraphModal from "./GraphModal";
import ContextTablesModal from "./ContextTablesModal";
import FeedbackModal from "./FeedbackModal";
import RelatedQuestions from "./RelatedQuestions";
import ContextTablesAction from "./ContextTablesAction";
import ChatItemActions from "./ChatItemActions";
import ToolBlocks from "./ToolBlocks";

const ChatItem = ({
  result,
  index,
  dispatch,
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

  const [modalOverride, setModalOverride] = useState(null);

  const handleAskRelated = (question) => {
    setCurrentQuestion(question);
    setQuestionType(result?.toolName || null);
  };

  const handleAskDeepQuery = (question) => {
    setCurrentQuestion(question);
    setQuestionType("deep_query");
  };

  const handleOpenInfo = () => {
      setModalOverride(null);
      setShowInfoModal(true);
  };
  const handleCloseInfo = () => {
      setShowInfoModal(false);
      setModalOverride(null);
  };

  const handleToolIconClick = (toolResult) => {
      setModalOverride({
          ...result,
          ...toolResult, 
          toolName: toolResult.modalTool || null
      });
      setShowInfoModal(true);
  };

  const handleOpenGraph = (graphData) => {
    const g = graphData || result.graph;
    if (!g) return;
    setGraph(g);
    setShowGraphModal(true);
  };
  const handleCloseGraph = () => {
    setShowGraphModal(false);
    setGraph(null);
  };

  const handleOpenTable = (data) => {
    const d = data || result.execution_result?.full;
    if (!d) return;
    setTableData(d);
    setShowTableModal(true);
  };

  const handleCloseTable = () => {
    setShowTableModal(false);
  };

  const handleResetTableData = () => {
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
    if (!config.chatbot_feedback) return;
    setShowFeedbackModal(true);
  };
  const handleCloseFeedback = () => {
    setShowFeedbackModal(false);
  };

  const renderContent = () => {
    // Fallback for empty or loading initial state
    if (!result.blocks || result.blocks.length === 0) {
        if (result.isLoading) {
             return (
                <Card.Text className="query-loading-text">
                  <div className="d-flex align-items-start">
                    <Spinner
                      size="sm"
                      animation="border"
                      className="me-2 mt-1"
                    />
                    <span>Processing...</span>
                  </div>
                </Card.Text>
              );
        }
        // If finished but empty (rare, but possible on error)
        if (result.result) {
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
        return <div style={{ minHeight: "20px" }} />;
    }

    return (
        <>
            {result.feedback && (
              <div className="mb-2">
                <span className={`badge bg-${result.feedback === "positive" ? "success" : "danger"} ms-2`}>
                  {result.feedback === "positive" ? "Positive feedback" : "Negative feedback"}
                </span>
              </div>
            )}
            
            <ToolBlocks
              blocks={result.blocks}
              result={result}
              isGeneratingReport={isGeneratingReport}
              onGenerateReport={onGenerateReport}
              resultsContainerRef={resultsContainerRef}
              onOpenGraph={handleOpenGraph}
              onOpenTable={handleOpenTable}
              onToolIconClick={handleToolIconClick}
            />
            
            {result.isError && result.errorMessage && (
              <div
                className="mt-2"
                style={{
                  borderRadius: "0.25rem",
                  padding: "0.5rem 0.75rem",
                  backgroundColor: "rgba(220,53,69,0.08)",
                  color: "#842029",
                  fontSize: "0.9rem",
                }}
              >
                {result.errorMessage}
              </div>
            )}
            
            <RelatedQuestions
                relatedQuestions={result.relatedQuestions}
                relatedQuestionsDeepQuery={result.relatedQuestionsDeepQuery}
                onAskRelated={handleAskRelated}
                onAskDeepQuery={handleAskDeepQuery}
            />
            
            {result.combinedTablesUsed && result.combinedTablesUsed.length > 0 && (
                <ContextTablesAction
                    tables={result.combinedTablesUsed}
                    vql={result.combinedVqls}
                    dataCatalogUrl={config.data_marketplace_url}
                    icons={
                        <ChatItemActions
                            result={result}
                            config={config}
                            onOpenInfo={handleOpenInfo}
                            onFeedback={handleOpenFeedback}
                            resultsContainerRef={resultsContainerRef}
                        />
                    }
                    onOpenContext={handleOpenContext}
                />
            )}
            
            {(!result.combinedTablesUsed || result.combinedTablesUsed.length === 0) && (
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
                      <ChatItemActions
                        result={result}
                        config={config}
                        onOpenInfo={handleOpenInfo}
                        onFeedback={handleOpenFeedback}
                        resultsContainerRef={resultsContainerRef}
                      />
                    </div>
                  </div>
                </div>
            )}
        </>
    );
  };

  return (
    <>
      <div className="w-100 d-flex justify-content-center mb-3">
        <div className="w-70 d-flex justify-content-end">
          <Card
            style={{
              backgroundColor: "#ffffff",
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
              backgroundColor: "#ffffff",
              color: "#112533",
              borderRadius: "1.25em",
              boxShadow: "0 4px 12px rgba(0, 0, 0, 0.1)",
              borderColor: result.isError ? "#dc3545" : undefined,
              borderWidth: result.isError ? "2px" : undefined
            }}
            data-result-index={index}
          >
            <Card.Body className="position-relative">
              <div className="card-content-area">{renderContent()}</div>
            </Card.Body>
          </Card>
        </div>
      </div>

      <AdditionalInformationModal
        show={showInfoModal}
        onClose={handleCloseInfo}
        result={modalOverride || result}
      />
      <GraphModal
        show={showGraphModal}
        graph={graph}
        onClose={handleCloseGraph}
      />
      <TableModal
        show={showTableModal}
        handleClose={handleCloseTable}
        handleResetData={handleResetTableData}
        executionResult={tableData}
      />
      <ContextTablesModal
        show={showContextModal}
        onClose={handleCloseContext}
        tables={contextTables.tables}
        vql={contextTables.vql}
        dataCatalogUrl={config.data_marketplace_url}
      />
      <FeedbackModal
        show={showFeedbackModal}
        onClose={handleCloseFeedback}
        result={result}
        dispatch={dispatch}
        resultIndex={index}
        feedbackEnabled={config.chatbot_feedback}
      />
    </>
  );
};

export default ChatItem;

ChatItem.propTypes = {
  result: PropTypes.shape({
    execution_result: PropTypes.shape({
      full: PropTypes.object,
    }),
  }).isRequired,
  index: PropTypes.number,
  dispatch: PropTypes.func,
  setCurrentQuestion: PropTypes.func,
  setQuestionType: PropTypes.func,
  onGenerateReport: PropTypes.func,
  isGeneratingReport: PropTypes.bool,
  resultsContainerRef: PropTypes.object,
};
