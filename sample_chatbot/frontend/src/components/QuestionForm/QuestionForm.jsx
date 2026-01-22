import Form from "react-bootstrap/Form";
import Navbar from "react-bootstrap/Navbar";
import Button from "react-bootstrap/Button";
import React, { useEffect, useState } from "react";
import ResourcesFilterModal from "./ResourcesFilterModal";
import useQuestionForm from "../../hooks/useQuestionForm";
import NotificationToast from "../NotificationToast/NotificationToast";
import "./QuestionForm.css";

const QuestionForm = ({ 
  results, 
  dispatch, 
  isAuthenticated, 
  currentQuestion: propCurrentQuestion,
  setCurrentQuestion: propSetCurrentQuestion,
  sdk,
  completedRequestId,
  syncedResources,
  partialResources
}) => {
  const {
    currentQuestion,
    showFilterModal,
    setShowFilterModal,
    searchFilters,
    allowExternalAssociations,
    isDeepQueryRunning,
    isAnyQueryRunning,
    filterCount,
    textInputRef,
    handleQuestionChange,
    handleFilterSave,
    handleSubmit,
    handleKeyDown,
    handleSendClick,
    handleDeepQueryClick,
    handleCancelDeepQuery,
    lastToolRequest,
    config,
  } = useQuestionForm(
    propCurrentQuestion,
    propSetCurrentQuestion,
    results,
    dispatch,
    sdk,
    isAuthenticated
  );
  
  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: "",
    variant: "info",
    title: "",
  });

  const handleToastClose = () => {
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  useEffect(() => {
    if (lastToolRequest) {
      const toolLabel = lastToolRequest.prettyName || lastToolRequest.name || "tool";
      setToastConfig({
        show: true,
        message: `Requested the "${toolLabel}" tool for this question.`,
        variant: "info",
        title: "Tool Requested",
      });
    }
  }, [lastToolRequest]);

  const getPlaceholder = () => {
    if (!isAuthenticated) {
      return "Please sign in to ask questions";
    }
    if (config.enableDeepQuery) {
      return "Type your question here. Use @ to ask the LLM to use a specific tool(s), e.g. @data_query, @metadata_query, @deep_query.";
    }
    return "Type your question here. Use @ to ask the LLM to use a specific tool(s), e.g. @data_query, @metadata_query.";
  };

  const getPaddingRight = () => {
    if (isDeepQueryRunning) return "150px";
    if (config.enableDeepQuery) return "190px";
    return "90px";
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

    <Navbar className="justify-content-center" data-bs-theme="dark" fixed="bottom" style={{ padding: "10px 0", backgroundColor: "transparent" }}>
      <div className="w-100 d-flex justify-content-center">
        <div style={{ width: '70%', maxWidth: '70%' }}>
          <Form onSubmit={handleSubmit}>
            <div className="position-relative">
              <div className="position-absolute" style={{ left: '10px', top: '50%', transform: 'translateY(-50%)', zIndex: 5 }}>
                <Button
                  variant="link"
                  onClick={() => setShowFilterModal(true)}
                  disabled={!isAuthenticated || isAnyQueryRunning}
                  style={{ 
                    color: '#6c757d', 
                    textDecoration: 'none',
                    padding: '0.25rem 0.5rem',
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
              </div>
              <Form.Control
                ref={textInputRef}
                as="textarea"
                type="text"
                placeholder={getPlaceholder()}
                value={currentQuestion}
                onChange={handleQuestionChange}
                onKeyDown={handleKeyDown}
                disabled={!isAuthenticated}
                className="question-textarea"
                style={{ 
                  paddingRight: getPaddingRight(),
                  paddingLeft: '70px',
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
                  config.enableDeepQuery && (
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
                  )
                 )}
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
