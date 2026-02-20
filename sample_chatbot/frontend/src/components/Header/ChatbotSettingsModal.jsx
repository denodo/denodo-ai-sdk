import React, { useState, useEffect } from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Alert from 'react-bootstrap/Alert';
import Spinner from 'react-bootstrap/Spinner';
import axios from 'axios';
import NotificationToast from '../NotificationToast/NotificationToast';

const STORAGE_KEY = 'chatbot_llm_settings';

const getStoredSettings = (username) => {
  try {
    const stored = localStorage.getItem(`${username}_${STORAGE_KEY}`);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
};

const saveStoredSettings = (username, settings) => {
  try {
    localStorage.setItem(`${username}_${STORAGE_KEY}`, JSON.stringify(settings));
  } catch (e) {
    console.error('Error saving chatbot LLM settings to localStorage:', e);
  }
};

const clearStoredSettings = (username) => {
  try {
    localStorage.removeItem(`${username}_${STORAGE_KEY}`);
  } catch (e) {
    console.error('Error clearing chatbot LLM settings from localStorage:', e);
  }
};

// Exported for use during login auto-apply
export { STORAGE_KEY, getStoredSettings };

const ChatbotSettingsModal = ({ show, handleClose, handleClearResults }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const [chatbotLLM, setChatbotLLM] = useState({
    provider: '',
    model: '',
    temperature: '',
    max_tokens: ''
  });
  const [validProviders, setValidProviders] = useState([]);
  const [isCustomProvider, setIsCustomProvider] = useState(false);
  const [defaults, setDefaults] = useState({});
  const [toastConfig, setToastConfig] = useState({
    show: false, message: '', variant: 'info', title: 'Notification', duration: 5000
  });

  const showToast = (message, variant, title, duration = 5000) => {
    setToastConfig({ show: true, message, variant, title, duration });
  };

  const handleToastClose = () => {
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  // Fetch defaults and user preferences when the modal opens
  useEffect(() => {
    if (!show) return;

    const fetchSettings = async () => {
      setIsFetching(true);
      try {
        const response = await axios.get('api/llm_settings');
        const data = response.data;

        const serverDefaults = data.chatbot_llm_defaults || {};
        const prefs = data.chatbot_llm_preferences || {};
        const providers = data.ai_sdk_info?.valid_providers || [];

        setValidProviders(providers);
        setDefaults(serverDefaults);

        const effectiveProvider = prefs.provider || serverDefaults.provider || '';
        setChatbotLLM({
          provider: effectiveProvider,
          model: prefs.model || serverDefaults.model || '',
          temperature: prefs.temperature ?? serverDefaults.temperature ?? '',
          max_tokens: prefs.max_tokens || serverDefaults.max_tokens || '',
        });

        // Check if the effective provider is custom (not in the standard list)
        const providersLower = new Set(providers.map(p => p.toLowerCase()));
        setIsCustomProvider(effectiveProvider !== '' && !providersLower.has(effectiveProvider.toLowerCase()));
      } catch (error) {
        console.error('Error fetching LLM settings:', error);
      } finally {
        setIsFetching(false);
      }
    };

    fetchSettings();
  }, [show]);

  const validateTemperature = (temp) => {
    if (temp === '' || temp === null || temp === undefined) return true;
    const tempFloat = parseFloat(temp);
    return !isNaN(tempFloat) && tempFloat >= 0.0 && tempFloat <= 2.0;
  };

  const validateMaxTokens = (tokens) => {
    if (tokens === '' || tokens === null || tokens === undefined) return true;
    const tokensInt = parseInt(tokens);
    return !isNaN(tokensInt) && tokensInt >= 1024 && tokensInt <= 20000;
  };

  const validateForm = () => {
    if (!validateTemperature(chatbotLLM.temperature)) {
      showToast('Chatbot LLM Temperature must be between 0.0 and 2.0', 'warning', 'Validation Error');
      return false;
    }
    if (!validateMaxTokens(chatbotLLM.max_tokens)) {
      showToast('Chatbot LLM Max Output Tokens must be between 1024 and 20000', 'warning', 'Validation Error');
      return false;
    }
    return true;
  };

  const hasLLMChanges = () => {
    return Object.values(chatbotLLM).some((v) => v !== '' && v !== null && v !== undefined);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateForm()) return;

    setIsLoading(true);
    try {
      const payload = { chatbot_llm: chatbotLLM };
      await axios.post('update_llm_settings', payload);

      // Persist to localStorage for session recovery
      const username = localStorage.getItem('current_user');
      if (username) {
        saveStoredSettings(username, payload);
      }

      if (hasLLMChanges()) {
        await handleClearResults();
        showToast('Chatbot settings updated. Conversation history cleared.', 'success', 'Settings Updated');
      } else {
        showToast('Chatbot settings updated.', 'success', 'Settings Updated');
      }
      handleClose();
    } catch (error) {
      console.error('Error updating Chatbot settings:', error);
      showToast(error.response?.data?.error || 'An error occurred while updating chatbot settings.', 'danger', 'Update Error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetToDefaults = async () => {
    setIsLoading(true);
    try {
      await axios.post('reset_llm_settings', { component: 'chatbot' });

      // Clear localStorage
      const username = localStorage.getItem('current_user');
      if (username) {
        clearStoredSettings(username);
      }

      // Reset form to server defaults
      setChatbotLLM({
        provider: defaults.provider || '',
        model: defaults.model || '',
        temperature: defaults.temperature ?? '',
        max_tokens: defaults.max_tokens || '',
      });

      const providersLower = new Set(validProviders.map(p => p.toLowerCase()));
      const defProvider = defaults.provider || '';
      setIsCustomProvider(defProvider !== '' && !providersLower.has(defProvider.toLowerCase()));

      await handleClearResults();
      showToast('Chatbot settings reset to defaults. Conversation history cleared.', 'success', 'Settings Reset');
    } catch (error) {
      console.error('Error resetting Chatbot settings:', error);
      showToast(error.response?.data?.error || 'An error occurred while resetting chatbot settings.', 'danger', 'Reset Error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleProviderSelect = (value) => {
    if (value === '__custom__') {
      setIsCustomProvider(true);
      setChatbotLLM((prev) => ({ ...prev, provider: '' }));
    } else {
      setIsCustomProvider(false);
      setChatbotLLM((prev) => ({ ...prev, provider: value }));
    }
  };

  return (
    <>
    <Modal show={show} onHide={handleClose} size="lg" centered>
      <Modal.Header closeButton data-bs-theme="light">
        <Modal.Title>Chatbot Settings</Modal.Title>
      </Modal.Header>
      <Modal.Body style={{ maxHeight: '70vh', overflowY: 'auto' }}>
        <Alert variant="info" className="mb-3 py-2">
          <small>
            <strong>Note:</strong> Fields are pre-filled with the current configuration.
            Changing LLM settings will clear your conversation history.
            Your settings are saved and will be restored on your next login.
          </small>
        </Alert>
        {chatbotLLM.provider && defaults.provider &&
          chatbotLLM.provider.toLowerCase() !== defaults.provider.toLowerCase() && (
          <Alert variant="warning" className="mb-3 py-2">
            <small>
              <strong>Important:</strong> If you select a different provider or model, make sure the corresponding
              API keys are already configured in <code>chatbot_config.env</code>. Authentication credentials must be set before
              starting the chatbot.
            </small>
          </Alert>
        )}

        {isFetching ? (
          <div className="text-center py-4">
            <Spinner animation="border" size="sm" />
            <span className="ms-2">Loading current settings...</span>
          </div>
        ) : (
          <Form id="chatbot-settings-form" onSubmit={handleSubmit}>
            <div className="row g-2">
              <div className="col-md-6">
                <Form.Group controlId="chatbotLLM-provider" className="mb-2">
                  <Form.Label className="small">Provider</Form.Label>
                  {isCustomProvider ? (
                    <div className="d-flex gap-1">
                      <Form.Control
                        size="sm"
                        type="text"
                        placeholder="Custom provider name"
                        value={chatbotLLM.provider}
                        onChange={(e) => setChatbotLLM((prev) => ({ ...prev, provider: e.target.value }))}
                      />
                      <Button
                        size="sm"
                        variant="outline-secondary"
                        onClick={() => setIsCustomProvider(false)}
                        title="Switch back to provider list"
                      >
                        &#x2630;
                      </Button>
                    </div>
                  ) : (
                    <Form.Select
                      size="sm"
                      value={chatbotLLM.provider}
                      onChange={(e) => handleProviderSelect(e.target.value)}
                    >
                      <option value="">Select provider...</option>
                      {validProviders.map((p) => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                      <option value="__custom__">Custom...</option>
                    </Form.Select>
                  )}
                </Form.Group>
              </div>
              <div className="col-md-6">
                <Form.Group controlId="chatbotLLM-model" className="mb-2">
                  <Form.Label className="small">Model</Form.Label>
                  <Form.Control
                    size="sm"
                    type="text"
                    placeholder="e.g., gpt-5.2-none, gemini-2.5-flash"
                    value={chatbotLLM.model}
                    onChange={(e) => setChatbotLLM((prev) => ({ ...prev, model: e.target.value }))}
                  />
                </Form.Group>
              </div>
              <div className="col-md-6">
                <Form.Group controlId="chatbotLLM-temperature" className="mb-2">
                  <Form.Label className="small">Temperature (0.0 - 2.0)</Form.Label>
                  <Form.Control
                    size="sm"
                    type="number"
                    step="0.1"
                    min="0.0"
                    max="2.0"
                    placeholder="e.g., 0.7"
                    value={chatbotLLM.temperature}
                    onChange={(e) => setChatbotLLM((prev) => ({ ...prev, temperature: e.target.value }))}
                  />
                </Form.Group>
              </div>
              <div className="col-md-6">
                <Form.Group controlId="chatbotLLM-maxTokens" className="mb-2">
                  <Form.Label className="small">Max Output Tokens</Form.Label>
                  <Form.Control
                    size="sm"
                    type="number"
                    min="1024"
                    max="20000"
                    placeholder="e.g., 4096"
                    value={chatbotLLM.max_tokens}
                    onChange={(e) => setChatbotLLM((prev) => ({ ...prev, max_tokens: e.target.value }))}
                  />
                </Form.Group>
              </div>
            </div>
          </Form>
        )}
      </Modal.Body>

      <Modal.Footer>
        <Button
          variant="outline-danger"
          size="sm"
          onClick={handleResetToDefaults}
          disabled={isLoading || isFetching}
          className="me-auto"
        >
          Reset to Defaults
        </Button>
        <Button variant="light" onClick={handleClose} disabled={isLoading}>
          Cancel
        </Button>
        <Button
          variant="dark"
          type="submit"
          form="chatbot-settings-form"
          disabled={isLoading || isFetching}
        >
              {isLoading ? (
                <>
                  <Spinner as="span" animation="border" size="sm" role="status" aria-hidden="true" />
                  <span className="ms-2">Updating...</span>
                </>
              ) : (
                'Save'
              )}
        </Button>
      </Modal.Footer>
    </Modal>
    <NotificationToast
      show={toastConfig.show}
      message={toastConfig.message}
      variant={toastConfig.variant}
      title={toastConfig.title}
      duration={toastConfig.duration}
      onClose={handleToastClose}
    />
    </>
  );
};

export default ChatbotSettingsModal;
