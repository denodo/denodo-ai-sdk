import Form from "react-bootstrap/Form";
import Navbar from "react-bootstrap/Navbar";
import Button from "react-bootstrap/Button";
import Dropdown from "react-bootstrap/Dropdown";
import React, { useEffect, useState } from "react";
import ResourcesFilterModal from "./ResourcesFilterModal";
import useQuestionForm from "../../hooks/useQuestionForm";
import NotificationToast from "../NotificationToast/NotificationToast";
import "./QuestionForm.css";

const baseToolOptions = [
  { id: 'auto', label: 'Auto (Default)', bg: '#6c757d', icon: 'bi-stars', iconColor: '#6c757d' }, 
  { id: 'deep_query', label: 'Deep Query', bg: 'linear-gradient(135deg, #ED342A 0%, #413581 100%)', icon: 'bi-magic', iconColor: '#7953aa' },
  { id: 'data_agent', label: 'Data Agent', bg: '#0d6efd', icon: 'bi-database', iconColor: '#0d6efd' }, 
  { id: 'metadata_search', label: 'Metadata Search', bg: '#20c997', icon: 'bi-code-slash', iconColor: '#20c997' }, 
  { id: 'knowledge_query', label: 'Knowledge Base Query', bg: '#fd7e14', icon: 'bi-book', iconColor: '#fd7e14' }
];

const QuestionForm = ({ 
  results, 
  dispatch, 
  isAuthenticated, 
  currentQuestion: propCurrentQuestion,
  setCurrentQuestion: propSetCurrentQuestion,
  questionType,
  setQuestionType,
  sdk,
  syncedResources,
  partialResources,
  selectedChatbot
}) => {
  const {
    currentQuestion,
    showFilterModal,
    setShowFilterModal,
    searchFilters,
    allowExternalAssociations,
    isQueryRunning,
    isAnyQueryRunning,
    filterCount,
    textInputRef,
    handleQuestionChange,
    handleFilterSave,
    handleSendClick,
    handleCancelQuery,
    lastToolRequest,
    config,
  } = useQuestionForm(
    propCurrentQuestion,
    propSetCurrentQuestion,
    results,
    dispatch,
    sdk,
    isAuthenticated,
    selectedChatbot
  );

  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: "",
    variant: "info",
    title: "",
  });

  const toolOptions = baseToolOptions.filter(tool => {
    if (tool.id === 'deep_query') return config.enable_deep_query;
    if (tool.id === 'knowledge_query') return config.unstructured_mode;
    return true;
  });

  const activeTool = toolOptions.find(t => t.id === questionType) || toolOptions.find(t => t.id === 'auto') || baseToolOptions[0];

  useEffect(() => {
    setQuestionType('auto');
  }, [selectedChatbot, setQuestionType]);

  const handleToastClose = () => {
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  useEffect(() => {
    if (lastToolRequest) {
      if (lastToolRequest.name === 'deep_query' && !config.enable_deep_query) return;
      if (lastToolRequest.name === 'knowledge_query' && !config.unstructured_mode) return;

      const matchedTool = baseToolOptions.find(tool => tool.id === lastToolRequest.name);
      const toolLabel = (matchedTool && matchedTool.label) || lastToolRequest.prettyName || lastToolRequest.name || "tool";

      setToastConfig({
        show: true,
        message: `Requested the "${toolLabel}" tool for this question.`,
        variant: "info",
        title: "Tool Requested",
      });
    }
  }, [lastToolRequest, config.enable_deep_query, config.unstructured_mode]);

  const handleSubmitWithTool = (e) => {
    if (e && e.preventDefault) e.preventDefault();
    const forceTool = activeTool.id === 'auto' ? null : activeTool.id;
    handleSendClick(e, forceTool);
    setQuestionType('auto');
  };

  const handleQuestionKeyDown = (e) => {
    if (e.key !== 'Enter') return;

    if (config.input_method === 'ctrl_enter') {
      // metaKey is checked because macOS reports Cmd as metaKey, never as ctrlKey,
      // so Cmd+Enter is accepted alongside Ctrl+Enter on Mac keyboards
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        handleSubmitWithTool(e);
      } else if (!e.shiftKey) {
        // Plain Enter is ignored so the Enter that completes an IME conversion never sends
        e.preventDefault();
      }
    } else if (!e.shiftKey) {
      e.preventDefault();
      handleSubmitWithTool(e);
    }
  };

  const getPlaceholder = () => {
    if (!isAuthenticated) return "Please sign in to ask questions";

    let options = ['@data', '@metadata'];
    if (config.unstructured_mode) options.push('@kb');
    if (config.enable_deep_query) options.push('@deepquery');

    return `Type your question here. Use @ to ask the LLM to use a specific tool, e.g. ${options.join(', ')}.`;
  };

  const getPaddingRight = () => {
    let base = 60;
    if (isQueryRunning) {
      base += 80;
    } else {
      base += 40;
    }
    return `${base}px`;
  };

  return (
    <>
    <NotificationToast
      show={toastConfig.show}
      message={toastConfig.message}
      variant={toastConfig.variant}
      title={toastConfig.title}
      onClose={handleToastClose}
    />

    <Navbar className="justify-content-center w-100" data-bs-theme="dark" style={{ backgroundColor: "transparent" }}>
      <div className="w-100 d-flex justify-content-center">
        <div style={{ width: '80%', maxWidth: '800px' }}>
          <Form onSubmit={handleSubmitWithTool}>
            <div className="position-relative">
              <div
                className="position-absolute" 
                style={{ left: '12px', top: '50%', transform: 'translateY(-50%)', zIndex: 5, display: 'flex', alignItems: 'center' }}
              >
                {config.filters_enabled && (
                  <Button
                    variant="link"
                    onClick={() => setShowFilterModal(true)}
                    disabled={!isAuthenticated || isAnyQueryRunning}
                    title="Context selection"
                    style={{ 
                      color: '#6c757d', 
                      textDecoration: 'none',
                      padding: '0.2rem 0.4rem',
                      position: 'relative'
                    }}
                    onMouseEnter={(e) => e.target.style.color = '#112533'}
                    onMouseLeave={(e) => e.target.style.color = '#6c757d'}
                  >
                    <i className="bi bi-filter" style={{ fontSize: '1.25rem' }}></i>
                    {filterCount > 0 && (
                      <span 
                        className="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger"
                        style={{ 
                              fontSize: '0.6em', 
                              padding: '0.3em 0.5em',
                              pointerEvents: 'none' 
                          }}
                      >
                        {filterCount}
                      </span>
                    )}
                  </Button>
                )}
              </div>
              <Form.Control
                ref={textInputRef}
                as="textarea"
                type="text"
                placeholder={getPlaceholder()}
                value={currentQuestion}
                onChange={handleQuestionChange}
                onKeyDown={handleQuestionKeyDown}
                disabled={!isAuthenticated}
                className="question-textarea bg-white"
                style={{ 
                  paddingRight: getPaddingRight(),
                  paddingLeft: '60px',
                  paddingTop: '12px',
                  paddingBottom: '12px',
                  minHeight: '47px',
                  resize: 'none',
                  color: '#212529',
                  border: '1px solid #ced4da',
                  borderRadius: '1.25em',
                  boxShadow: '0 2px 6px rgba(0,0,0,0.05)'
                }}
              />
              <div className="position-absolute" style={{ right: '12px', top: '50%', transform: 'translateY(-50%)', display: 'flex', gap: '8px', alignItems: 'center' }}>
                {isQueryRunning ? (
                  <Button
                    variant="link"
                    type="button"
                    onClick={handleCancelQuery}
                    title="Stop"
                    style={{
                      color: '#dc3545',
                      textDecoration: 'none',
                      padding: '0.2rem',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      transition: 'all 0.2s ease'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.color = '#a71d2a';
                      e.currentTarget.style.transform = 'scale(1.15)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.color = '#dc3545';
                      e.currentTarget.style.transform = 'scale(1)';
                    }}
                  >
                    <i className="bi bi-stop-circle" style={{ fontSize: '1.2rem', pointerEvents: 'none' }}></i>
                  </Button>
                ) : (
                  <Dropdown drop="up" title={activeTool.label}>
                    <Dropdown.Toggle
                      size="sm"
                      disabled={!isAuthenticated || isAnyQueryRunning}
                      style={{
                        background: activeTool.id === 'auto' ? 'transparent' : activeTool.bg,
                        border: activeTool.id === 'auto' ? '1px solid #ced4da' : 'none',
                        color: activeTool.id === 'auto' ? '#6c757d' : 'white',
                        height: '32px',
                        transition: 'all 0.3s ease',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: '0 10px',
                        borderRadius: '8px'
                      }}
                      id="dropdown-tool-selector"
                    >
                      <i className={`bi ${activeTool.icon}`} style={{ fontSize: '1.1rem' }}></i>
                    </Dropdown.Toggle>

                    <Dropdown.Menu
                      align="end"
                      className="shadow border-0 mb-2"
                      style={{
                        fontSize: '0.9rem',
                        minWidth: '200px',
                        borderRadius: '0.75rem',
                        backgroundColor: '#ffffff',
                        padding: '0.5rem 0'
                      }}
                    >
                      <Dropdown.Header className="py-1 fw-bold" style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: '#112533' }}>
                        Select Mode
                      </Dropdown.Header>

                      {toolOptions.map(tool => (
                        <Dropdown.Item
                          key={tool.id}
                          onClick={() => setQuestionType(tool.id)}
                          className={`py-2 d-flex align-items-center ${activeTool.id === tool.id ? 'fw-bold' : ''}`}
                          style={{
                            color: '#212529',
                            backgroundColor: activeTool.id === tool.id ? '#f8f9fa' : 'transparent',
                            cursor: 'pointer'
                          }}
                        >
                          <i
                            className={`bi ${tool.icon} me-2`}
                            style={{
                              fontSize: '1.1rem',
                              color: activeTool.id === tool.id ? (tool.iconColor || tool.bg.split(' ')[0]) : '#6c757d'
                            }}
                          ></i>
                          {tool.label}
                        </Dropdown.Item>
                      ))}
                    </Dropdown.Menu>
                  </Dropdown>
                )}

                <Button
                  variant="link"
                  type="button"
                  onClick={handleSubmitWithTool}
                  disabled={!isAuthenticated || isAnyQueryRunning}
                  title="Send question"
                  style={{
                    color: activeTool.id === 'auto' ? '#112533' : (activeTool.iconColor || activeTool.bg.split(' ')[0]),
                    textDecoration: 'none',
                    padding: '0.2rem',
                    opacity: (!isAuthenticated || isAnyQueryRunning || !currentQuestion.trim()) ? 0.4 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = activeTool.id === 'auto' ? '#0056b3' : (activeTool.iconColor || activeTool.bg.split(' ')[0]);
                    e.currentTarget.style.transform = 'scale(1.15)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = activeTool.id === 'auto' ? '#112533' : (activeTool.iconColor || activeTool.bg.split(' ')[0]);
                    e.currentTarget.style.transform = 'scale(1)';
                  }}
                >
                  <i className="bi bi-send" style={{ fontSize: '1.2rem', pointerEvents: 'none' }}></i>
                </Button>
               </div>
             </div>
           </Form>
         </div>
       </div>
     </Navbar>

    <ResourcesFilterModal 
      show={showFilterModal}
      handleClose={() => setShowFilterModal(false)}
      syncedResources={syncedResources}
      partialResources={partialResources}
      currentFilters={searchFilters}
      currentAllowExternalAssociations={allowExternalAssociations}
      onSave={handleFilterSave}
    />
  </>
  );
};

export default QuestionForm;
