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
import './Results.css';
import useSDK from '../hooks/useSDK';

const Results = ({ results, setResults }) => {
  const [showModal, setShowModal] = useState(false);
  const [selectedResult, setSelectedResult] = useState(null);
  const resultsEndRef = useRef(null);
  const [showGraphModal, setShowGraphModal] = useState(false);
  const [selectedGraph, setSelectedGraph] = useState(null);

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
                className="mb-2 cursor-pointer" 
                onClick={() => handleIconClick(result)}
              />
            </OverlayTrigger>
            {result.execution_result && (
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
                  <img src="export.png" alt="Export CSV" width="20" height="20" />
                </CSVLink>
              </OverlayTrigger>
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
          </div>
        );
      case "kb":
        return (
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
        );
      default:
        return (
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
            return (
              <Badge 
                key={index} 
                bg={isUsedInVql ? "success" : "secondary"} 
                className="context-badge me-1 mb-1"
              >
                {table.replace(/"/g, '')}
              </Badge>
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
                <div className="flex-grow-1 pe-3">
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
                  </div>
                  {(
                    <>
                      <Card.Text>
                        <b>Answer: </b>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.result}</ReactMarkdown>
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
    </div>
  );
};

export default Results;
