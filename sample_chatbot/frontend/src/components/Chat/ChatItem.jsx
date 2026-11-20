import React, { useState, useEffect } from "react";
import PropTypes from "prop-types";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Card from "react-bootstrap/Card";
import Collapse from "react-bootstrap/Collapse";
import Spinner from "react-bootstrap/Spinner";
import TableModal from "./Modals/TableModal";
import { useConfig } from "../../contexts/ConfigContext";
import AdditionalInformationModal from "./Modals/AdditionalInformationModal";
import GraphModal from "./Modals/GraphModal";
import FeedbackModal from "./Modals/FeedbackModal";
import RelatedQuestions from "./RelatedQuestions";
import ChatItemActions from "./ChatItemActions";
import ContextTablesAction from "./ContextTablesAction";
import ContextTablesModal from "./Modals/ContextTablesModal";
import ToolBlocks from "./ToolBlocks";
import NotificationToast from "../NotificationToast/NotificationToast";
import CopyButton from "../CopyButton/CopyButton";
import { markdownComponents } from "./markdownComponents";
import { InlineGraphsProvider, replaceGraphFences } from "./inlineGraphs";

// Tracks active streaming messages during this session so that,
// even if React unmounts the component upon receiving a UUID,
// it mounts expanded, displays the toggle, and smoothly auto-collapses once finished.
const activeStreamItems = new Set();

const ChatItem = ({
  result,
  index,
  dispatch,
  setCurrentQuestion,
  setQuestionType,
  resultsContainerRef,
  receivedToolOutputs,
  contextViews,
}) => {
  const { config } = useConfig();
  const [isExpanded, setIsExpanded] = useState(() => {
    if (result.isLoading) return true;
    if (activeStreamItems.has(index) || (result.uuid && activeStreamItems.has(result.uuid))) {
      return true;
    }
    return false;
  });
  const [showInfoModal, setShowInfoModal] = useState(false);
  const [showGraphModal, setShowGraphModal] = useState(false);
  const [graph, setGraph] = useState(null);
  const [graphVql, setGraphVql] = useState("");
  const [showTableModal, setShowTableModal] = useState(false);
  const [tableData, setTableData] = useState(null);
  const [showContextModal, setShowContextModal] = useState(false);
  const [contextTables, setContextTables] = useState({ tables: [], vql: "" });
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [modalOverride, setModalOverride] = useState(null);
  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: "",
    variant: "info",
    title: "",
    showCopyButton: true,
  });

  useEffect(() => {
    const isStreaming =
      activeStreamItems.has(index) ||
      (result.uuid && activeStreamItems.has(result.uuid));

    if (result.isLoading) {
      activeStreamItems.add(index);
      if (result.uuid) activeStreamItems.add(result.uuid);
      setIsExpanded(true);
      return;
    }

    // Only auto-collapse the first time (when triggered by an active stream completion)
    if (!result.isLoading && isExpanded && isStreaming) {
      const timer = setTimeout(() => {
        setIsExpanded(false);
        activeStreamItems.delete(index);
        if (result.uuid) activeStreamItems.delete(result.uuid);
      }, 750);

      return () => clearTimeout(timer);
    }

    // If already collapsed or manually closed by the user, release the active flag
    if (!isExpanded) {
      activeStreamItems.delete(index);
      if (result.uuid) activeStreamItems.delete(result.uuid);
    }
  }, [result.isLoading, isExpanded, index, result.uuid]);

  const handleAskRelated = (question) => {
    setCurrentQuestion(question);
    setQuestionType(result?.toolName || 'auto');
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
  };

  const handleResetInfo = () => {
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
    const entry = graphData || result.graph;
    if (!entry) return;
    const src = typeof entry === "string" ? entry : entry.src || entry.graph;
    if (!src) return;
    setGraph(src);
    setGraphVql(typeof entry === "string" ? "" : entry.vql || "");
    setShowGraphModal(true);
  };

  const handleCloseGraph = () => {
    setShowGraphModal(false);
  };

  const handleResetGraph = () => {
    setGraph(null);
    setGraphVql("");
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
  };

  const handleResetContext = () => {
    setContextTables({ tables: [], vql: "" });
  };

  const handleOpenFeedback = () => {
    if (!config.chatbot_feedback || result.disableFeedback) return;
    setShowFeedbackModal(true);
  };

  const handleCloseFeedback = () => {
    setShowFeedbackModal(false);
  };

  const handleClipboardError = (errorMessage) => {
    setToastConfig({
      show: true,
      title: "Clipboard Error",
      message:
        errorMessage ||
        "Unable to copy to clipboard. Clipboard permissions may be blocked or the connection is not secure (HTTP/0.0.0.0).",
      variant: "warning",
      showCopyButton: false,
    });
  };

  const renderContent = () => {
    if (result.isLoading && (!result.blocks || result.blocks.length === 0)) {
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

    // Logic to separate technical process (tools + intermediate reasoning) from the final response.
    const blocks = result.blocks || [];
    
    let lastToolIndex = -1;
    for (let i = blocks.length - 1; i >= 0; i--) {
      if (blocks[i].type === "tool") {
        lastToolIndex = i;
        break;
      }
    }

    // We assume the last block is the final answer if it's a message,
    // AND either we are not loading OR there were tools executed before it.
    let processBlocks = [];
    let finalAnswerBlock = null;

    if (lastToolIndex === -1) {
      processBlocks = [];
      finalAnswerBlock = blocks[blocks.length - 1] || null;
    } else if (!result.isLoading) {
      processBlocks = blocks.slice(0, lastToolIndex + 1);
      if (lastToolIndex < blocks.length - 1) {
        finalAnswerBlock = blocks[blocks.length - 1];
      }
    } else {
      processBlocks = blocks;
      finalAnswerBlock = null;
    }

    const toolExecutionCount = processBlocks.filter((b) => b.type === "tool").length;
    const hasProcess = processBlocks.length > 0 && toolExecutionCount > 0;
    const emptyBlocksText = (!blocks || blocks.length === 0)
      ? (result.result || (result.isError ? result.errorMessage : null))
      : null;
    const responseCopyText =
      (finalAnswerBlock && finalAnswerBlock.content) ||
      emptyBlocksText ||
      "";

    return (
      <>
        {result.feedback && !result.isError && (
          <div className="mb-2">
            <span className={`badge bg-${result.feedback === "positive" ? "success" : "danger"} ms-2`}>
              {result.feedback === "positive" ? "Positive feedback" : "Negative feedback"}
            </span>
          </div>
        )}
        
        {!result.isLoading && hasProcess && (
          <div className="process-toggle-container mb-2 toggle-fade-in">
            <button
              className="btn btn-sm process-toggle-btn d-flex align-items-center"
              onClick={() => setIsExpanded(!isExpanded)}
              aria-expanded={isExpanded}
              type="button"
            >
              <i className={`bi bi-caret-${isExpanded ? "down" : "right"}-fill`}></i>
              <span className="ms-2">
                {`${toolExecutionCount} ${toolExecutionCount === 1 ? 'executed tool' : 'executed tools'}`}
              </span>
            </button>
          </div>
        )}

        {hasProcess && (
          <Collapse in={isExpanded}>
            <div id={`collapse-tools-${index}`} className="collapse-tools-wrapper">
              <ToolBlocks
                blocks={processBlocks}
                resultsContainerRef={resultsContainerRef}
                onOpenGraph={handleOpenGraph}
                onOpenTable={handleOpenTable}
                onToolIconClick={handleToolIconClick}
                receivedToolOutputs={receivedToolOutputs}
                onClipboardError={handleClipboardError}
              />
            </div>
          </Collapse>
        )}

        {finalAnswerBlock && finalAnswerBlock.content && (
          <Card.Text as="div" className="mt-0">
            <div className="markdown-container">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={markdownComponents}
              >
                {replaceGraphFences(finalAnswerBlock.content)}
              </ReactMarkdown>
            </div>
          </Card.Text>
        )}

        {emptyBlocksText && (
          <Card.Text as="div" className="mt-0">
            <div className="markdown-container">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={markdownComponents}
              >
                {replaceGraphFences(emptyBlocksText)}
              </ReactMarkdown>
            </div>
          </Card.Text>
        )}

        <RelatedQuestions
          relatedQuestions={result.relatedQuestions}
          relatedQuestionsDeepQuery={result.relatedQuestionsDeepQuery}
          onAskRelated={handleAskRelated}
          onAskDeepQuery={handleAskDeepQuery}
        />

        <ContextTablesAction
          tables={result.combinedTablesUsed}
          vql={result.combinedVqls}
          dataCatalogUrl={config.data_marketplace_url}
          contextViews={contextViews}
          icons={
            <ChatItemActions
              result={result}
              config={{ ...config, chatbot_feedback: config.chatbot_feedback && !result.disableFeedback }}
              onOpenInfo={handleOpenInfo}
              onFeedback={handleOpenFeedback}
              resultsContainerRef={resultsContainerRef}
              copyText={responseCopyText}
              onError={handleClipboardError}
            />
          }
          onOpenContext={handleOpenContext}
        />
      </>
    );
  };

  return (
    <>
      <div className="w-100 d-flex justify-content-center mb-3">
        <div className="w-70 d-flex justify-content-end">
          <div
            className="user-question-container d-flex align-items-center gap-2"
            style={{ maxWidth: "80%" }}
          >
            {result.question && (
              <CopyButton
                text={result.question}
                tooltipText="Copy question"
                placement="top"
                className="user-question-copy-btn flex-shrink-0"
                onError={handleClipboardError}
              />
            )}
            <Card
              style={{
                backgroundColor: "#ffffff",
                borderRadius: "1.25em",
                color: "#112533",
                boxShadow: "0 4px 12px rgba(0, 0, 0, 0.1)",
                width: "fit-content",
              }}
            >
              <Card.Body>
                <Card.Text className="mb-0">{result.question}</Card.Text>
              </Card.Body>
            </Card>
          </div>
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
              <div className="card-content-area">
                <InlineGraphsProvider blocks={result.blocks} onOpenGraph={handleOpenGraph}>
                  {renderContent()}
                </InlineGraphsProvider>
              </div>
            </Card.Body>
          </Card>
        </div>
      </div>

      <AdditionalInformationModal
        show={showInfoModal}
        onClose={handleCloseInfo}
        onExited={handleResetInfo}
        result={modalOverride || result}
      />
      <GraphModal
        show={showGraphModal}
        graph={graph}
        vql={graphVql}
        onClose={handleCloseGraph}
        onExited={handleResetGraph}
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
        onExited={handleResetContext}
        tables={contextTables.tables}
        vql={contextTables.vql}
        dataCatalogUrl={config.data_marketplace_url}
        contextViews={contextViews}
      />
      <FeedbackModal
        show={showFeedbackModal}
        onClose={handleCloseFeedback}
        result={result}
        dispatch={dispatch}
        resultIndex={index}
        feedbackEnabled={config.chatbot_feedback}
        onShowToast={setToastConfig}
      />
      <NotificationToast
        show={toastConfig.show}
        message={toastConfig.message}
        variant={toastConfig.variant}
        title={toastConfig.title}
        showCopyButton={toastConfig.showCopyButton !== false}
        onError={handleClipboardError}
        onClose={() => setToastConfig((prev) => ({ ...prev, show: false }))}
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
    isError: PropTypes.bool,
    errorMessage: PropTypes.string,
    blocks: PropTypes.array,
    result: PropTypes.string,
    question: PropTypes.string,
    isLoading: PropTypes.bool,
    uuid: PropTypes.string,
    feedback: PropTypes.string,
    combinedTablesUsed: PropTypes.array,
    combinedVqls: PropTypes.string,
    relatedQuestions: PropTypes.array,
    relatedQuestionsDeepQuery: PropTypes.array,
    toolName: PropTypes.string,
    graph: PropTypes.any,
    disableFeedback: PropTypes.bool,
  }).isRequired,
  index: PropTypes.number,
  dispatch: PropTypes.func,
  setCurrentQuestion: PropTypes.func,
  setQuestionType: PropTypes.func,
  resultsContainerRef: PropTypes.object,
  receivedToolOutputs: PropTypes.object,
  contextViews: PropTypes.array,
};
