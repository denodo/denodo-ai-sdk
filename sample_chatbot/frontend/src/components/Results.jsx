import React, { useState, useEffect, useRef } from "react";
import Card from "react-bootstrap/Card";
import Button from "react-bootstrap/Button";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Spinner from "react-bootstrap/Spinner";
import Modal from 'react-bootstrap/Modal';
import { CSVLink } from "react-csv";
import Badge from "react-bootstrap/Badge";
import Form from "react-bootstrap/Form";
import './Results.css';
import useSDK from '../hooks/useSDK';
import { useConfig } from '../contexts/ConfigContext';
import TableModal from './TableModal';

const Results = ({ results, setResults }) => {
  const [showModal, setShowModal] = useState(false);
  const [selectedResult, setSelectedResult] = useState(null);
  const resultsEndRef = useRef(null);
  const [showGraphModal, setShowGraphModal] = useState(false);
  const [selectedGraph, setSelectedGraph] = useState(null);
  const [showTableModal, setShowTableModal] = useState(false);
  const [selectedTableData, setSelectedTableData] = useState(null);
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [feedbackResult, setFeedbackResult] = useState(null);
  const [feedbackValue, setFeedbackValue] = useState('');
  const [feedbackDetails, setFeedbackDetails] = useState('');
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const { config } = useConfig();

  const { processQuestion } = useSDK(
    setResults
  );

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

  const handleRelatedQuestionClick = async (question) => {
    const resultIndex = results.length;
    setResults(prevResults => [...prevResults, { question, isLoading: true, result: "" }]);
    const type = selectedResult && (selectedResult.questionType === 'data' || selectedResult.questionType === 'metadata') ? selectedResult.questionType : 'default';
    await processQuestion(question, type, resultIndex);
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
    setFeedbackValue('');
    setFeedbackDetails('');
    setShowFeedbackModal(true);
  };

  const handleCloseFeedbackModal = () => {
    setShowFeedbackModal(false);
    setFeedbackResult(null);
    setFeedbackValue('');
    setFeedbackDetails('');
  };

  const handleFeedbackSubmit = async () => {
    if (!config.chatbotFeedback || !feedbackResult || !feedbackResult.uuid) return;
    
    setFeedbackSubmitting(true);
    
    try {
      const response = await fetch('submit_feedback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          uuid: feedbackResult.uuid,
          feedback_value: feedbackValue,
          feedback_details: feedbackDetails
        })
      });
      
      const data = await response.json();
      
      if (response.ok) {
        // Update the result with feedback info in UI
        setResults(prevResults => 
          prevResults.map(result => 
            result.uuid === feedbackResult.uuid 
              ? { ...result, feedback: feedbackValue, feedbackDetails: feedbackDetails } 
              : result
          )
        );
        handleCloseFeedbackModal();
      } else {
        alert(`Error submitting feedback: ${data.message}`);
      }
    } catch (error) {
      console.error('Error submitting feedback:', error);
      alert('An error occurred while submitting feedback.');
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const renderTooltip = (props, content) => (
    <Tooltip id="button-tooltip" {...props}>
      {content}
    </Tooltip>
  );

  const getIcon = (result) => {
    if (result.isLoading) {
      return (
        <Spinner
          animation="border"
          role="status"
          size="sm"
          style={{ width: '16px', height: '16px' }}
        >
          <span className="visually-hidden">Loading...</span>
        </Spinner>
      );
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
          className="mt-2 cursor-pointer" 
          onClick={() => handleFeedbackIconClick(result)}
        />
      </OverlayTrigger>
    ) : null;
    
    switch (result.questionType?.toLowerCase()) {
      case "data":
      case "metadata":
        return (
          <div className="d-flex flex-column align-items-center">
            <OverlayTrigger
              placement="left"
              delay={{ show: 250, hide: 400 }}
              overlay={(props) => renderTooltip(props, "Denodo")}
            >
              <img 
                src="favicon.ico" 
                alt="Denodo Icon" 
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
                  overlay={(props) => renderTooltip(props, "View execution result")}
                >
                  <img 
                    src="table.png" 
                    alt="View execution result" 
                    width="20" 
                    height="20" 
                    className="mt-2 cursor-pointer"
                    onClick={() => handleTableIconClick(result.execution_result)}
                  />
                </OverlayTrigger>
                <OverlayTrigger
                  placement="left"
                  delay={{ show: 250, hide: 400 }}
                  overlay={(props) => renderTooltip(props, "Download execution result")}
                >
                  <CSVLink
                    data={parseApiResponseToCsv(result.execution_result)}
                    filename={"denodo_data.csv"}
                    className="csv-link"
                    target="_blank"
                  >
                    <img src="export.png" alt="Export CSV" width="20" height="20" className="mt-2" />
                  </CSVLink>
                </OverlayTrigger>
              </>
            )}
            {result.graph && result.graph.startsWith('data:image') && result.graph.length > 300 && (
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
                  className="mt-2 cursor-pointer"
                  onClick={() => handleGraphIconClick(result.graph)}
                />
              </OverlayTrigger>
            )}
            {feedbackIcon}
          </div>
        );
      case "kb":
        return (
          <div className="d-flex flex-column align-items-center">
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
          <div className="d-flex flex-column align-items-center">
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
            <p><strong>Source:</strong> Denodo</p>
            <p><strong>AI-Generated SQL:</strong> {result.vql || "N/A"}</p>
            <p><strong>Query explanation:</strong> {result.query_explanation || "N/A"}</p>
            <p><strong>AI SDK Tokens:</strong> {result.tokens || "N/A"}</p>
            <p><strong>AI SDK Time:</strong> {result.ai_sdk_time ? `${result.ai_sdk_time}s` : "N/A"}</p>
          </div>
        );
      case "metadata":
        return (
          <div>
            <p><strong>Source:</strong> Denodo</p>
            <p><strong>AI-Generated SQL:</strong> N/A</p>
            <p><strong>Query explanation:</strong> N/A</p>
          </div>
        );
      case "kb":
        return (
          <div>
            <p><strong>Source:</strong> Knowledge Base</p>
            <p><strong>Vector store:</strong> {result.data_sources || "N/A"}</p>
          </div>
        );
      default:
        return (
          <div>
            <p><strong>Source:</strong> AI</p>
            <p><strong>Model:</strong> {result.data_sources || "N/A"}</p>
          </div>
        );
    }
  };

  const renderTables = (tables, vql) => {
    if (!tables || tables.length === 0) return null;

    // Clean VQL by removing all quotes
    const cleanVql = vql?.replace(/"/g, '').toLowerCase() || '';

    // Sort tables - used tables first
    const sortedTables = [...tables].sort((a, b) => {
      const aClean = a.replace(/"/g, '').toLowerCase();
      const bClean = b.replace(/"/g, '').toLowerCase();
      const aUsed = cleanVql.includes(aClean);
      const bUsed = cleanVql.includes(bClean);
      return bUsed - aUsed;
    });

    return (
      <div className="mb-2">
        <b>Context:</b>{' '}
        <div className="context-badges-container">
          {sortedTables.map((table, index) => {
            const cleanTable = table.replace(/"/g, '').toLowerCase();
            const isUsedInVql = cleanVql.includes(cleanTable);
            
            // Split the table name to get schema and table parts
            const tableParts = cleanTable.split('.');
            const schema = tableParts[0];
            const tableName = tableParts[1] || schema; // If no schema, use the whole name as tableName
            
            // Create the URL for the Denodo Data Catalog
            const catalogUrl = config.dataCatalogUrl ? `${config.dataCatalogUrl}/#/view/${schema}/${tableName}` : null;
            
            return (
              catalogUrl ? (
                <a 
                  key={index}
                  href={catalogUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-decoration-none"
                >
                  <Button
                    variant={isUsedInVql ? "success" : "secondary"} 
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
                    {table.replace(/"/g, '')}
                  </Button>
                </a>
              ) : (
                <Button 
                  key={index}
                  variant={isUsedInVql ? "success" : "secondary"} 
                  size="sm"
                  bsPrefix="btn"
                  className="me-1 mb-1 d-inline-flex align-items-center"
                >
                  {table.replace(/"/g, '')}
                </Button>
              )
            );
          })}
        </div>
      </div>
    );
  };

  const renderRelatedQuestions = (result) => {
    if (!result.relatedQuestions || result.relatedQuestions.length === 0) return null;

    return (
      <div className="d-flex flex-column align-items-start mt-3">
        {result.relatedQuestions.map((q, i) => (
          <Button
            key={i}
            variant="outline-light"
            size="sm"
            className="mb-2 text-start w-100"
            onClick={() => {
              setSelectedResult(result);
              handleRelatedQuestionClick(q);
            }}
          >
            {q + " →"}
          </Button>
        ))}
      </div>
    );
  };

  const parseApiResponseToCsv = (apiResponse) => {
    if (!apiResponse || typeof apiResponse === 'string' || Object.keys(apiResponse).length === 0) return [];

    const rows = Object.values(apiResponse);
    const headers = rows[0].map(item => item.columnName);
    const dataRows = rows.map(row => 
      row.map(item => item.value)
    );

    return [headers, ...dataRows];
  };

  return results.length === 0 ? null : (
    <div className="d-flex flex-column align-items-center w-100 text-light">
      {results.map((result, index) => (
        <React.Fragment key={index}>
          <div className="w-100 d-flex justify-content-center mb-2">
            <Card className={`w-60 bg-dark text-light border border-white`}>
              <Card.Body className="d-flex">
                <div className="flex-grow-1 pe-3 card-content-area">
                  <Card.Title>
                    <b>Question: </b> {result.question}
                  </Card.Title>
                  <div className="mb-2">
                    {(() => {
                      let badgeText, badgeVariant;
                      switch (result.questionType?.toLowerCase()) {
                        case 'data':
                          badgeText = 'Data';
                          badgeVariant = 'primary';
                          break;
                        case 'metadata':
                          badgeText = 'Metadata';
                          badgeVariant = 'danger';
                          break;
                        case 'kb':
                          badgeText = 'Unstructured';
                          badgeVariant = 'success';
                          break;
                        default:
                          badgeText = 'LLM';
                          badgeVariant = 'light';
                      }
                      return (
                        <Badge bg={badgeVariant} text={badgeVariant === 'light' ? 'dark' : 'light'}>
                          {badgeText}
                        </Badge>
                      );
                    })()}
                    {result.feedback && (
                      <Badge 
                        bg={result.feedback === 'positive' ? 'success' : 'danger'} 
                        className="ms-2"
                      >
                        {result.feedback === 'positive' ? 'Positive feedback' : 'Negative feedback'}
                      </Badge>
                    )}
                  </div>
                  {(
                    <>
                      <Card.Text>
                        <b>Answer: </b>
                        <div className="markdown-container">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.result}</ReactMarkdown>
                        </div>
                      </Card.Text>
                      {renderRelatedQuestions(result)}
                      {(result.questionType === "data" || result.questionType === "metadata") && renderTables(result.tables_used, result.vql)}
                    </>
                  )}
                </div>
                <div className="d-flex align-items-center justify-content-center" style={{ width: '40px' }}>
                  {getIcon(result)}
                </div>
              </Card.Body>
            </Card>
          </div>
        </React.Fragment>
      ))}
      <div ref={resultsEndRef} />
      
      <Modal 
        show={showModal} 
        onHide={handleCloseModal} 
        size="lg" 
        centered
        contentClassName="bg-dark text-white border border-white"
      >
        <Modal.Header closeButton className="border-bottom border-white">
          <Modal.Title>Additional Information</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {renderModalContent(selectedResult)}
        </Modal.Body>
      </Modal>

      <Modal 
        show={showGraphModal} 
        onHide={handleCloseGraphModal} 
        size="lg" 
        centered
        contentClassName="bg-dark text-white border border-white"
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
        llm_response_rows_limit={config.llm_response_rows_limit}
        handleClose={handleCloseTableModal}
        executionResult={selectedTableData}
      />
      
      {config.chatbotFeedback && (
        <Modal 
          show={showFeedbackModal} 
          onHide={handleCloseFeedbackModal} 
          centered
          contentClassName="bg-dark text-white border border-white"
        >
          <Modal.Header closeButton className="border-bottom border-white">
            <Modal.Title>Provide Feedback</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {feedbackResult && (
              <>
                <div className="mb-3">
                  <p className="mb-1"><strong>Question:</strong></p>
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
                        checked={feedbackValue === 'positive'}
                        onChange={() => setFeedbackValue('positive')}
                      />
                      <Form.Check
                        inline
                        type="radio"
                        id="negative-feedback"
                        label="No"
                        name="feedback"
                        value="negative"
                        checked={feedbackValue === 'negative'}
                        onChange={() => setFeedbackValue('negative')}
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
            >
              {feedbackSubmitting ? 'Submitting...' : 'Submit Feedback'}
            </Button>
          </Modal.Footer>
        </Modal>
      )}
    </div>
  );
};

export default Results;
