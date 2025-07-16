import React, { useState, useEffect } from "react";
import Navbar from "react-bootstrap/Navbar";
import Form from "react-bootstrap/Form";
import Button from "react-bootstrap/Button";
import Row from "react-bootstrap/Row";
import Col from "react-bootstrap/Col";
import Spinner from "react-bootstrap/Spinner";
import Badge from "react-bootstrap/Badge";
import useSDK from '../hooks/useSDK';

const QuestionForm = ({ 
  results, 
  setResults, 
  isAuthenticated, 
  questionType,
  setQuestionType,
}) => {
  const [question, setQuestion] = useState("");
  const { isLoading, processQuestion } = useSDK(setResults);

  useEffect(() => {
    const commandType = getCommandType(question);
    if (commandType) {
      setQuestionType(commandType);
    }
  }, [question, setQuestionType]);

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
    setQuestion(newQuestion);
    
    const commandType = getCommandType(newQuestion);
    if (commandType) {
      setQuestionType(commandType);
    } else if (questionType !== "default") {
      setQuestionType("default");
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && (event.shiftKey || event.ctrlKey)) {
      event.preventDefault();
      handleSubmit(event);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!isAuthenticated || !question.trim()) return;

    const commandType = getCommandType(question);
    const finalQuestion = commandType ? question.replace(/^\/\w+\s*/, '').trim() : question.trim();

    if (!finalQuestion) return;

    const finalQuestionType = commandType || questionType;

    const resultIndex = results.length;
    setResults((prevResults) => [
      ...prevResults,
      { question: finalQuestion, isLoading: true, result: "", questionType: finalQuestionType },
    ]);

    await processQuestion(finalQuestion, finalQuestionType, resultIndex);
    setQuestion("");
  };

  const handleClear = (event) => {
    event.preventDefault();
    setQuestion("");
  };

  return (
    <Navbar className="bg-body-tertiary justify-content-center" data-bs-theme="dark" fixed="bottom" style={{ padding: "10px 0" }}>
      <Form
        inline="true"
        className="w-100 justify-content-center"
        onSubmit={handleSubmit}
      >
        <Row className="justify-content-center align-items-center">
          <Col xs="auto">
            <Badge bg="secondary" className="me-2">
              {questionType.toUpperCase()}
            </Badge>
          </Col>
          <Col xs="auto" className="w-50 position-relative">
            <Form.Control
              as="textarea"
              type="text"
              placeholder={isAuthenticated ? "Type your question here. You can directly query data questions with /sql or /data. You can directly query metadata questions with /metadata or /schema commands." : "Please sign in to ask questions"}
              className="w-200"
              value={question}
              onChange={handleQuestionChange}
              onKeyDown={handleKeyDown}
              disabled={!isAuthenticated}
            />
          </Col>
          <Col xs="auto" className="d-flex align-items-center">
            <Button 
              className="align-middle" 
              variant="primary" 
              type="submit" 
              size="sm" 
              disabled={!isAuthenticated || !question.trim() || isOnlyCommand(question)}
            >
              {isLoading ? (
                <Spinner size="sm" animation="border" role="status">
                  <span className="visually-hidden">Loading...</span>
                </Spinner>
              ) : (
                <>
                  <i className="bi bi-send" /> Send
                </>
              )}
            </Button>
          </Col>
          <Col xs="auto" className="d-flex align-items-center">
            <Button
              className="align-middle"
              variant="danger"
              type="reset"
              size="sm"
              onClick={handleClear}
              disabled={!isAuthenticated || !question.trim()}
            >
              <i className="bi bi-trash" /> Clear
            </Button>
          </Col>
        </Row>
      </Form>
    </Navbar>
  );
};

export default QuestionForm;
