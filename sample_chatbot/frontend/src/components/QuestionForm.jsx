import Form from "react-bootstrap/Form";
import Navbar from "react-bootstrap/Navbar";
import Button from "react-bootstrap/Button";
import React, { useState, useEffect, useRef } from "react";

const QuestionForm = ({ 
  results, 
  setResults, 
  isAuthenticated, 
  questionType,
  setQuestionType,
  currentQuestion,
  setCurrentQuestion,
  sdk,
  completedRequestId,
}) => {
  const { isLoading, processQuestion, cancelDeepQuery, runningDeepQueries } = sdk;
  const [lastRequestId, setLastRequestId] = useState(null);
  const textInputRef = useRef(null);

  useEffect(() => {
    const commandType = getCommandType(currentQuestion);
    if (commandType) {
      setQuestionType(commandType);
    }
  }, [currentQuestion, setQuestionType]);

  const isOnlyCommand = (input) => {
    const trimmed = input.trim();
    return !!getCommandType(trimmed) && trimmed.split(/\s+/).length === 1;
  };

  const getCommandType = (input) => {
    const trimmedInput = input.trim().toLowerCase();
    if (trimmedInput.startsWith("/sql") || trimmedInput.startsWith("/data")) {
      return "data";
    } else if (trimmedInput.startsWith("/metadata") || trimmedInput.startsWith("/schema")) {
      return "metadata";
    }
    return null;
  };

  const handleQuestionChange = (event) => {
    const newQuestion = event.target.value;
    setCurrentQuestion(newQuestion);
    
    const commandType = getCommandType(newQuestion);
    if (commandType) {
      setQuestionType(commandType);
    } else if (questionType !== "default") {
      setQuestionType("default");
    }
  };

  const handleKeyDown = (event) => {
    // Submit with Enter, add new line with Shift+Enter
    if (event.key === "Enter" && !event.shiftKey) {
      if (!isAnyQueryRunning) {
        event.preventDefault();
        handleSubmit(event);
      }
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!isAuthenticated || !currentQuestion.trim() || isAnyQueryRunning) return;

    const commandType = getCommandType(currentQuestion);
    const finalQuestion = commandType ? currentQuestion.replace(/^\/\w+\s*/, '').trim() : currentQuestion.trim();

    if (!finalQuestion) return;

    const finalQuestionType = commandType || questionType;

    const resultIndex = results.length;
    setResults((prevResults) => [
      ...prevResults,
      { 
        question: finalQuestion, 
        isLoading: true, 
        result: "", 
        questionType: finalQuestionType,
        isShowingBadge: false,
        isShowingQuery: false,
        intermediateQuery: "",
        queryPhase: "initial"
      },
    ]);

    const requestId = await processQuestion(finalQuestion, finalQuestionType, resultIndex);
    
    if (requestId) {
      setLastRequestId(requestId);
    }
    
    setCurrentQuestion("");
  };

  const handleDeepQuerySubmit = async (event) => {
    event.preventDefault();
    if (!isAuthenticated || !currentQuestion.trim() || isAnyQueryRunning) return;

    const finalQuestion = currentQuestion.trim();
    if (!finalQuestion) return;

    const resultIndex = results.length;
    
    setResults((prevResults) => [
      ...prevResults,
      { 
        question: finalQuestion, 
        isLoading: true, 
        result: "", 
        questionType: "deep_query",
        isShowingBadge: false,
        isShowingQuery: false,
        intermediateQuery: "",
        queryPhase: "initial"
      },
    ]);

    const requestId = await processQuestion(finalQuestion, "deep_query", resultIndex);

    if (requestId) {
      setLastRequestId(requestId);
    }
    setCurrentQuestion("");
  };

  const handleCancelDeepQuery = () => {
    if (lastRequestId && runningDeepQueries.includes(lastRequestId)) {
      cancelDeepQuery(lastRequestId);
    }
  };

  const handleSendClick = (event) => {
    if (!isAuthenticated || isAnyQueryRunning) return;
    
    if (!currentQuestion.trim() || isOnlyCommand(currentQuestion)) {
      // Focus the text input if no valid text
      textInputRef.current?.focus();
      return;
    }
    
    // Submit if there's valid text
    handleSubmit(event);
  };

  const handleDeepQueryClick = (event) => {
    if (!isAuthenticated || isAnyQueryRunning) return;
    
    if (!currentQuestion.trim() || isOnlyCommand(currentQuestion)) {
      // Focus the text input if no valid text
      textInputRef.current?.focus();
      return;
    }
    
    // Submit deep query if there's valid text
    handleDeepQuerySubmit(event);
  };

  // Clean up completed requests
  useEffect(() => {
    if (completedRequestId && completedRequestId === lastRequestId) {
      setLastRequestId(null);
    }
  }, [completedRequestId, lastRequestId]);

  const isDeepQueryRunning = lastRequestId !== null && runningDeepQueries.includes(lastRequestId);
  const isAnyQueryRunning = isLoading || results.some(r => r.isLoading);

  return (
    <Navbar className="justify-content-center" data-bs-theme="dark" fixed="bottom" style={{ padding: "10px 0", backgroundColor: "transparent" }}>
      <div className="w-100 d-flex justify-content-center">
        <div style={{ width: '70%', maxWidth: '70%' }}>
          <Form onSubmit={handleSubmit}>
            <div className="position-relative">
              <Form.Control
                ref={textInputRef}
                as="textarea"
                type="text"
                placeholder={isAuthenticated ? "Type your question here. You can directly query data questions with /sql or /data. You can directly query metadata questions with /metadata or /schema commands." : "Please sign in to ask questions"}
                value={currentQuestion}
                onChange={handleQuestionChange}
                onKeyDown={handleKeyDown}
                disabled={!isAuthenticated}
                style={{ 
                  paddingRight: isDeepQueryRunning ? '150px' : '190px',
                  paddingLeft: '20px',
                  paddingTop: '12px',
                  paddingBottom: '12px',
                  minHeight: '47px',
                  resize: 'none',
                  backgroundColor: 'transparent',
                  color: '#6c757d',
                  border: '1px solid #112533',
                  borderRadius: '1.25em'
                }}
              />
              <div className="position-absolute" style={{ right: '15px', top: '50%', transform: 'translateY(-50%)', display: 'flex', gap: '8px' }}>
                <Button
                  variant="primary"
                  type="button"
                  size="sm"
                  disabled={!isAuthenticated || isAnyQueryRunning}
                  onClick={handleSendClick}
                  style={{ 
                    backgroundColor: '#112533',
                    borderColor: '#112533',
                    height: '32px',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => e.target.style.opacity = '0.8'}
                  onMouseLeave={(e) => e.target.style.opacity = '1'}
                >
                  Send
                </Button>
                {isDeepQueryRunning ? (
                  <Button
                    variant="danger"
                    type="button"
                    size="sm"
                    onClick={handleCancelDeepQuery}
                    style={{ height: '32px' }}
                  >
                    Cancel
                  </Button>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    onClick={handleDeepQueryClick}
                    disabled={!isAuthenticated || isAnyQueryRunning}
                    style={{ 
                      background: 'linear-gradient(135deg, #ED342A 0%, #413581 100%)',
                      border: 'none',
                      height: '32px',
                      transition: 'all 0.2s ease'
                    }}
                    onMouseEnter={(e) => e.target.style.opacity = '0.8'}
                    onMouseLeave={(e) => e.target.style.opacity = '1'}
                  >
                    DeepQuery
                  </Button>
                )}
              </div>
            </div>
          </Form>
        </div>
      </div>
    </Navbar>
  );
};

export default QuestionForm;
