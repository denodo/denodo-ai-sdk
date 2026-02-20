import React from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";

const AdditionalInformationModal = ({ show, onClose, result }) => {
  if (!result) return null;

  const renderContent = () => {
    const artifact = result.modalArtifact || {};
    const errorMessage =
      result.error_message ||
      artifact.error_message ||
      (typeof artifact.error === "string" ? artifact.error : null) ||
      (result.isError ? result.errorMessage || result.result : null);
    const traceback = result.traceback || artifact.traceback || result.errorDetails;
    const hasError = !!(errorMessage || traceback);

    const renderErrorSection = () => {
      if (!errorMessage && !traceback) return null;
      return (
        <div
          style={{
            marginBottom: "1rem",
            borderRadius: "0.25rem",
            padding: "0.5rem 0.75rem",
            backgroundColor: "rgba(220,53,69,0.08)",
            color: "#842029",
            fontSize: "0.9rem",
          }}
        >
          {errorMessage && (
            <p style={{ marginBottom: traceback ? "0.25rem" : 0 }}>
              <strong>Error:</strong> {errorMessage}
            </p>
          )}
          {traceback && (
            <div>
              <strong>Traceback:</strong>
              <pre
                style={{
                  marginTop: "0.25rem",
                  maxHeight: "250px",
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  fontSize: "0.8rem",
                }}
              >
                {traceback}
              </pre>
            </div>
          )}
        </div>
      );
    };

    if (!result.modalTool) {
      return (
        <div>
          {renderErrorSection()}
          {!hasError && (
            <p>
              <strong>Chatbot LLM:</strong> {result.chatbot_llm || "N/A"}
            </p>
          )}
        </div>
      );
    }

    const modalTool = (result.modalTool || result.toolName || "").toLowerCase();

    switch (modalTool) {
      case "data_query":
        if (errorMessage || traceback) {
          return <div>{renderErrorSection()}</div>;
        }
        return (
          <div>
            <p>
              <strong>Source:</strong> Denodo
            </p>
            <p>
              <strong>AI SDK LLM:</strong>{" "}
              {result.llm_provider && result.llm_model
                ? `${result.llm_provider}/${result.llm_model}`
                : "N/A"}
            </p>
            <p>
              <strong>AI-Generated SQL:</strong> {result.vql || "N/A"}
            </p>
            <p>
              <strong>Query explanation:</strong> {result.query_explanation || "N/A"}
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
        if (errorMessage || traceback) {
          return <div>{renderErrorSection()}</div>;
        }
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
      case "metadata_query":
        if (errorMessage || traceback) {
          return <div>{renderErrorSection()}</div>;
        }
        return (
          <div>
            <p>
              <strong>Source:</strong> Denodo
            </p>
          </div>
        );
      case "knowledge_query":
        if (errorMessage || traceback) {
          return <div>{renderErrorSection()}</div>;
        }
        return (
          <div>
            <p>
              <strong>Source:</strong> Knowledge Base
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
              <strong>Chatbot LLM:</strong> {result.chatbot_llm || "N/A"}
            </p>
          </div>
        );
    }
  };

  return (
    <Modal show={show} onHide={onClose} size="lg" centered>
      <Modal.Header closeButton data-bs-theme="light">
        <Modal.Title>Additional Information</Modal.Title>
      </Modal.Header>
      <Modal.Body>{renderContent()}</Modal.Body>
      <Modal.Footer>
        <Button variant="light" onClick={onClose}>
          Close
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default AdditionalInformationModal;


