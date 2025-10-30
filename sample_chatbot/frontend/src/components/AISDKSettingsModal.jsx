import React, { useState } from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Alert from 'react-bootstrap/Alert';
import Spinner from 'react-bootstrap/Spinner';
import axios from 'axios';

const AISDKSettingsModal = ({ show, handleClose, handleClearResults }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [aiSDKBaseLLM, setAISDKBaseLLM] = useState({
    provider: '',
    model: '',
    temperature: '',
    max_tokens: ''
  });
  const [aiSDKThinkingLLM, setAISDKThinkingLLM] = useState({
    provider: '',
    model: '',
    temperature: '',
    max_tokens: ''
  });
  const [useBaseLLMForExecution, setUseBaseLLMForExecution] = useState(false);

  const validateTemperature = (temp) => {
    if (!temp) return true;
    const tempFloat = parseFloat(temp);
    return !isNaN(tempFloat) && tempFloat >= 0.0 && tempFloat <= 2.0;
  };

  const validateMaxTokens = (tokens) => {
    if (!tokens) return true;
    const tokensInt = parseInt(tokens);
    return !isNaN(tokensInt) && tokensInt >= 1024 && tokensInt <= 20000;
  };

  const validateForm = () => {
    if (!validateTemperature(aiSDKBaseLLM.temperature)) {
      alert('AI SDK Base LLM Temperature must be between 0.0 and 2.0');
      return false;
    }
    if (!validateMaxTokens(aiSDKBaseLLM.max_tokens)) {
      alert('AI SDK Base LLM Max Tokens must be between 1024 and 20000');
      return false;
    }
    if (!validateTemperature(aiSDKThinkingLLM.temperature)) {
      alert('AI SDK Thinking LLM Temperature must be between 0.0 and 2.0');
      return false;
    }
    if (!validateMaxTokens(aiSDKThinkingLLM.max_tokens)) {
      alert('AI SDK Thinking LLM Max Tokens must be between 1024 and 20000');
      return false;
    }
    return true;
  };

  const hasLLMChanges = () => {
    const values = [
      ...Object.values(aiSDKBaseLLM),
      ...Object.values(aiSDKThinkingLLM)
    ];
    return values.some((v) => v !== '' && v !== null && v !== undefined) || useBaseLLMForExecution;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateForm()) return;

    setIsLoading(true);
    try {
      const payload = {
        ai_sdk_base_llm: aiSDKBaseLLM,
        ai_sdk_thinking_llm: aiSDKThinkingLLM,
        use_base_llm_for_execution: useBaseLLMForExecution
      };
      await axios.post('update_llm_settings', payload);
      if (hasLLMChanges()) {
        await handleClearResults();
        alert('AI SDK settings updated. Conversation history cleared.');
      } else {
        alert('AI SDK settings updated.');
      }
      handleClose();
    } catch (error) {
      console.error('Error updating AI SDK settings:', error);
      alert(error.response?.data?.error || 'An error occurred while updating AI SDK settings.');
    } finally {
      setIsLoading(false);
    }
  };

  const renderLLMSection = (title, llmState, setLLMState) => (
    <div className="mb-3">
      <h6 className="mb-2 small fw-bold">{title}</h6>
      <div className="row g-2">
        <div className="col-md-6">
          <Form.Group className="mb-2">
            <Form.Label className="small">Provider</Form.Label>
            <Form.Control
              size="sm"
              type="text"
              placeholder="e.g., openai, google, bedrock"
              value={llmState.provider}
              onChange={(e) => setLLMState((prev) => ({ ...prev, provider: e.target.value }))}
            />
          </Form.Group>
        </div>
        <div className="col-md-6">
          <Form.Group className="mb-2">
            <Form.Label className="small">Model</Form.Label>
            <Form.Control
              size="sm"
              type="text"
              placeholder="e.g., gpt-4o, gemini-2.5-flash"
              value={llmState.model}
              onChange={(e) => setLLMState((prev) => ({ ...prev, model: e.target.value }))}
            />
          </Form.Group>
        </div>
        <div className="col-md-6">
          <Form.Group className="mb-2">
            <Form.Label className="small">Temperature (0.0 - 1.0)</Form.Label>
            <Form.Control
              size="sm"
              type="number"
              step="0.1"
              min="0.0"
              max="1.0"
              placeholder="e.g., 0.7"
              value={llmState.temperature}
              onChange={(e) => setLLMState((prev) => ({ ...prev, temperature: e.target.value }))}
            />
          </Form.Group>
        </div>
        <div className="col-md-6">
          <Form.Group className="mb-2">
            <Form.Label className="small">Max Tokens (1024 - 20000)</Form.Label>
            <Form.Control
              size="sm"
              type="number"
              min="1024"
              max="20000"
              placeholder="e.g., 4096"
              value={llmState.max_tokens}
              onChange={(e) => setLLMState((prev) => ({ ...prev, max_tokens: e.target.value }))}
            />
          </Form.Group>
        </div>
      </div>
    </div>
  );

  return (
    <Modal show={show} onHide={handleClose} size="lg" style={{ '--bs-modal-bg': '#112533' }} contentClassName="text-white border border-white">
      <Modal.Header closeButton className="custom-header-modal">
        <Modal.Title>AI SDK Settings</Modal.Title>
      </Modal.Header>
      <Modal.Body style={{ maxHeight: '70vh', overflowY: 'auto' }}>
        <Alert variant="info" className="mb-3 py-2">
          <small>
            <strong>Note:</strong> Leave fields empty to use system defaults. Changing LLM settings will clear your conversation
            history. API keys and provider configuration must be set in sdk_config.env before running the chatbot.
          </small>
        </Alert>
        <Form onSubmit={handleSubmit}>
          {renderLLMSection('Base LLM', aiSDKBaseLLM, setAISDKBaseLLM)}
          {renderLLMSection('Thinking LLM', aiSDKThinkingLLM, setAISDKThinkingLLM)}
          <Form.Group className="mb-3">
            <Form.Check
              type="checkbox"
              className="small"
              label="Use Base LLM for execution (default: Thinking LLM for both)"
              checked={useBaseLLMForExecution}
              onChange={(e) => setUseBaseLLMForExecution(e.target.checked)}
            />
          </Form.Group>
          <div className="d-flex justify-content-end pt-2">
            <Button variant="primary" size="sm" type="submit" disabled={isLoading} style={{ backgroundColor: '#2D3E4B', borderColor: '#2D3E4B' }}>
              {isLoading ? (
                <>
                  <Spinner as="span" animation="border" size="sm" role="status" aria-hidden="true" />
                  <span className="ms-2">Updating...</span>
                </>
              ) : (
                'Save Settings'
              )}
            </Button>
          </div>
        </Form>
      </Modal.Body>
    </Modal>
  );
};

export default AISDKSettingsModal;


