import React from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";

const ResultInfoModal = ({ show, onClose, result }) => {
  if (!result) return null;

  const type = result.questionType?.toLowerCase();

  const renderContent = () => {
    switch (type) {
      case "data":
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
                <strong>Execution time:</strong>{" "}
                {result.total_execution_time}s
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

export default ResultInfoModal;


