import React from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";

const AdditionalInformationModal = ({ show, onClose, result }) => {
  if (!result) return null;

  const renderContent = () => {
    const modalTool = (result.modalTool || result.toolName || "").toLowerCase();

    const targetBlock =
      result.blocks?.find(b => (b.toolName || b.modalTool || "").toLowerCase() === modalTool) ||
      result.toolCalls?.find(t => (t.toolName || "").toLowerCase() === modalTool);

    const activeArtifact = targetBlock?.artifact || result.modalArtifact || {};
    // ------------------------------------

    const errorMessage =
      result.error_message ||
      activeArtifact.error_message ||
      (typeof activeArtifact.error === "string" ? activeArtifact.error : null) ||
      (result.isError ? result.errorMessage || result.result : null);
    const traceback = result.traceback || activeArtifact.traceback || result.errorDetails;
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

    if (!result.modalTool && !result.toolName) {
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

    switch (modalTool) {
      case "data_agent":
        if (errorMessage || traceback) {
          return <div>{renderErrorSection()}</div>;
        }

        const totalTime = activeArtifact.total_execution_time ?? activeArtifact.ai_sdk_time ?? result.ai_sdk_time;
        const vectorTime = activeArtifact.vector_store_search_time;
        const llmTime = activeArtifact.llm_time;
        const sqlTime = activeArtifact.sql_execution_time;
        const hasBreakdown = vectorTime != null || llmTime != null || sqlTime != null;

        return (
          <div>
            <p>
              <strong>Source:</strong> Denodo
            </p>
            <p>
              <strong>AI SDK LLM:</strong>{" "}
              {activeArtifact.llm_provider && activeArtifact.llm_model
                ? `${activeArtifact.llm_provider}/${activeArtifact.llm_model}`
                : (result.llm_provider && result.llm_model ? `${result.llm_provider}/${result.llm_model}` : "N/A")}
            </p>
            <p>
              <strong>AI-Generated SQL:</strong> {activeArtifact.vql || result.vql || "N/A"}
            </p>
            <p>
              <strong>Query explanation:</strong> {activeArtifact.query_explanation || result.query_explanation || "N/A"}
            </p>
            <p>
              <strong>AI SDK Tokens:</strong> {activeArtifact.tokens || result.tokens || "N/A"}
            </p>

            {/* --- TIMING BREAKDOWN RENDER --- */}
            <p style={{ marginBottom: hasBreakdown ? "0.25rem" : "1rem" }}>
              <strong>AI SDK Time (Total):</strong>{" "}
              {totalTime != null ? `${Number(totalTime).toFixed(2)}s` : "N/A"}
            </p>

            {hasBreakdown && (
              <div style={{ paddingLeft: "1.25rem", marginBottom: "1rem", fontSize: "0.95rem", color: "#555" }}>
                <div style={{ marginBottom: "0.25rem" }}>
                  <span style={{ color: "#adb5bd", marginRight: "6px" }}>↳</span>
                  <strong>Vector Search:</strong> {vectorTime != null ? `${Number(vectorTime).toFixed(2)}s` : "0.00s"}
                </div>
                <div style={{ marginBottom: "0.25rem" }}>
                  <span style={{ color: "#adb5bd", marginRight: "6px" }}>↳</span>
                  <strong>LLM Processing:</strong> {llmTime != null ? `${Number(llmTime).toFixed(2)}s` : "0.00s"}
                </div>
                <div>
                  <span style={{ color: "#adb5bd", marginRight: "6px" }}>↳</span>
                  <strong>SQL Execution:</strong> {sqlTime != null ? `${Number(sqlTime).toFixed(2)}s` : "0.00s"}
                </div>
              </div>
            )}
            {/* --------------------------------- */}
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
            {activeArtifact.deepquery_metadata && (
              <>
                <p>
                  <strong>Planning LLM:</strong>{" "}
                  {activeArtifact.deepquery_metadata.planning_provider &&
                  activeArtifact.deepquery_metadata.planning_model
                    ? `${activeArtifact.deepquery_metadata.planning_provider}/${activeArtifact.deepquery_metadata.planning_model}`
                    : "N/A"}
                </p>
                <p>
                  <strong>Execution LLM:</strong>{" "}
                  {activeArtifact.deepquery_metadata.executing_provider &&
                  activeArtifact.deepquery_metadata.executing_model
                    ? `${activeArtifact.deepquery_metadata.executing_provider}/${activeArtifact.deepquery_metadata.executing_model}`
                    : "N/A"}
                </p>
                <p>
                  <strong>Number of tool calls:</strong>{" "}
                  {activeArtifact.deepquery_metadata.tool_calls
                    ? activeArtifact.deepquery_metadata.tool_calls.length
                    : "N/A"}
                </p>
              </>
            )}
            {(activeArtifact.total_execution_time || result.total_execution_time) && (
              <p>
                <strong>Execution time:</strong> {activeArtifact.total_execution_time || result.total_execution_time}s
              </p>
            )}
          </div>
        );
      case "metadata_search":
        if (errorMessage || traceback) {
          return <div>{renderErrorSection()}</div>;
        }

        // Only rely on the total time, as the LLM is bypassed for this tool.
        const mdTotalTime = activeArtifact.total_execution_time ?? activeArtifact.ai_sdk_time ?? result.total_execution_time ?? result.ai_sdk_time;

        return (
          <div>
            <p>
              <strong>Source:</strong> Denodo Metadata
            </p>

            <p style={{ marginBottom: mdTotalTime != null ? "0.25rem" : "1rem" }}>
              <strong>AI SDK Time (Total):</strong>{" "}
              {mdTotalTime != null ? `${Number(mdTotalTime).toFixed(2)}s` : "N/A"}
            </p>

            {mdTotalTime != null && (
              <div style={{ paddingLeft: "1.25rem", marginBottom: "1rem", fontSize: "0.95rem", color: "#555" }}>
                <div>
                  <span style={{ color: "#adb5bd", marginRight: "6px" }}>↳</span>
                  <strong>Vector Search:</strong> {Number(mdTotalTime).toFixed(2)}s
                </div>
              </div>
            )}
          </div>
        );
      case "knowledge_query": {
        if (errorMessage || traceback) {
          return <div>{renderErrorSection()}</div>;
        }
        const collectionName = result.collection_name || activeArtifact.collection_name || "N/A";
        const collectionDescription =
          result.collection_description || activeArtifact.collection_description || "";
        return (
          <div>
            <p>
              <strong>Source:</strong> Knowledge Base
            </p>
            <p>
              <strong>Collection:</strong> {collectionName}
            </p>
            <p>
              <strong>Collection description:</strong> {collectionDescription || "N/A"}
            </p>
          </div>
        );
      }
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