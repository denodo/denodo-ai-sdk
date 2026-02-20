import React, { useState, useEffect } from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Alert from 'react-bootstrap/Alert';
import Spinner from 'react-bootstrap/Spinner';
import axios from 'axios';
import NotificationToast from '../NotificationToast/NotificationToast';

const STORAGE_KEY = 'ai_sdk_llm_settings';

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
    console.error('Error saving AI SDK LLM settings to localStorage:', e);
  }
};

const clearStoredSettings = (username) => {
  try {
    localStorage.removeItem(`${username}_${STORAGE_KEY}`);
  } catch (e) {
    console.error('Error clearing AI SDK LLM settings from localStorage:', e);
  }
};

// Exported for use during login auto-apply
export { STORAGE_KEY, getStoredSettings };

const AISDKSettingsModal = ({ show, handleClose, handleClearResults }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
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
  const [checkAmbiguity, setCheckAmbiguity] = useState(true);
  const [validProviders, setValidProviders] = useState([]);
  const [isCustomBaseProvider, setIsCustomBaseProvider] = useState(false);
  const [isCustomThinkingProvider, setIsCustomThinkingProvider] = useState(false);
  const [sdkDefaults, setSdkDefaults] = useState({ base: {}, thinking: {} });
  const [sdkDeepQueryEnabled, setSdkDeepQueryEnabled] = useState(false);
  const [chatbotDeepQueryEnabled, setChatbotDeepQueryEnabled] = useState(false);
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

        const sdkInfo = data.ai_sdk_info || {};
        const baseDefaults = sdkInfo.base_llm || {};
        const thinkingDefaults = sdkInfo.thinking_llm || {};
        const providers = sdkInfo.valid_providers || [];
        const basePrefs = data.ai_sdk_base_llm_preferences || {};
        const thinkingPrefs = data.ai_sdk_thinking_llm_preferences || {};

        const hasThinkingModel = sdkInfo.thinking_llm != null;
        setSdkDeepQueryEnabled(hasThinkingModel);
        setChatbotDeepQueryEnabled(data.chatbot_deepquery ?? false);

        setValidProviders(providers);
        setSdkDefaults({ base: baseDefaults, thinking: thinkingDefaults });

        // Merge preferences over defaults (preferences take priority)
        const effectiveBaseProvider = basePrefs.provider || baseDefaults.provider || '';
        setAISDKBaseLLM({
          provider: effectiveBaseProvider,
          model: basePrefs.model || baseDefaults.model || '',
          temperature: basePrefs.temperature ?? baseDefaults.temperature ?? '',
          max_tokens: basePrefs.max_tokens || baseDefaults.max_tokens || '',
        });

        const effectiveThinkingProvider = thinkingPrefs.provider || thinkingDefaults.provider || '';
        setAISDKThinkingLLM({
          provider: effectiveThinkingProvider,
          model: thinkingPrefs.model || thinkingDefaults.model || '',
          temperature: thinkingPrefs.temperature ?? thinkingDefaults.temperature ?? '',
          max_tokens: thinkingPrefs.max_tokens || thinkingDefaults.max_tokens || '',
        });

        // Check ambiguity from user pref (already tracked on user object)
        setCheckAmbiguity(data.check_ambiguity ?? sdkInfo.check_ambiguity ?? true);

        // DeepQuery execution model
        const execModel = sdkInfo.deepquery_execution_model || 'thinking';
        setUseBaseLLMForExecution(execModel === 'base');

        // Determine if providers are custom
        const providersLower = new Set(providers.map(p => p.toLowerCase()));
        setIsCustomBaseProvider(effectiveBaseProvider !== '' && !providersLower.has(effectiveBaseProvider.toLowerCase()));
        setIsCustomThinkingProvider(effectiveThinkingProvider !== '' && !providersLower.has(effectiveThinkingProvider.toLowerCase()));
      } catch (error) {
        console.error('Error fetching AI SDK settings:', error);
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

  const deepQueryActive = sdkDeepQueryEnabled && chatbotDeepQueryEnabled;

  const validateForm = () => {
    if (!validateTemperature(aiSDKBaseLLM.temperature)) {
      showToast('AI SDK Base LLM Temperature must be between 0.0 and 2.0', 'warning', 'Validation Error');
      return false;
    }
    if (!validateMaxTokens(aiSDKBaseLLM.max_tokens)) {
      showToast('AI SDK Base LLM Max Output Tokens must be between 1024 and 20000', 'warning', 'Validation Error');
      return false;
    }
    if (deepQueryActive) {
      if (!validateTemperature(aiSDKThinkingLLM.temperature)) {
        showToast('AI SDK Thinking LLM Temperature must be between 0.0 and 2.0', 'warning', 'Validation Error');
        return false;
      }
      if (!validateMaxTokens(aiSDKThinkingLLM.max_tokens)) {
        showToast('AI SDK Thinking LLM Max Output Tokens must be between 1024 and 20000', 'warning', 'Validation Error');
        return false;
      }
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
        check_ambiguity: checkAmbiguity,
        ...(deepQueryActive && {
          ai_sdk_thinking_llm: aiSDKThinkingLLM,
          use_base_llm_for_execution: useBaseLLMForExecution,
        }),
      };
      await axios.post('update_llm_settings', payload);

      // Persist to localStorage for session recovery
      const username = localStorage.getItem('current_user');
      if (username) {
        saveStoredSettings(username, payload);
      }

      if (hasLLMChanges()) {
        await handleClearResults();
        showToast('AI SDK settings updated. Conversation history cleared.', 'success', 'Settings Updated');
      } else {
        showToast('AI SDK settings updated.', 'success', 'Settings Updated');
      }
      handleClose();
    } catch (error) {
      console.error('Error updating AI SDK settings:', error);
      showToast(error.response?.data?.error || 'An error occurred while updating AI SDK settings.', 'danger', 'Update Error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetToDefaults = async () => {
    setIsLoading(true);
    try {
      await axios.post('reset_llm_settings', { component: 'ai_sdk' });

      // Clear localStorage
      const username = localStorage.getItem('current_user');
      if (username) {
        clearStoredSettings(username);
      }

      // Reset form to server defaults
      const baseDefaults = sdkDefaults.base;
      const providersLower = new Set(validProviders.map(p => p.toLowerCase()));

      setAISDKBaseLLM({
        provider: baseDefaults.provider || '',
        model: baseDefaults.model || '',
        temperature: baseDefaults.temperature ?? '',
        max_tokens: baseDefaults.max_tokens || '',
      });
      setCheckAmbiguity(true);

      const baseP = baseDefaults.provider || '';
      setIsCustomBaseProvider(baseP !== '' && !providersLower.has(baseP.toLowerCase()));

      if (deepQueryActive) {
        const thinkingDefaults = sdkDefaults.thinking;
        setAISDKThinkingLLM({
          provider: thinkingDefaults.provider || '',
          model: thinkingDefaults.model || '',
          temperature: thinkingDefaults.temperature ?? '',
          max_tokens: thinkingDefaults.max_tokens || '',
        });
        setUseBaseLLMForExecution(false);
        const thinkP = thinkingDefaults.provider || '';
        setIsCustomThinkingProvider(thinkP !== '' && !providersLower.has(thinkP.toLowerCase()));
      }

      await handleClearResults();
      showToast('AI SDK settings reset to defaults. Conversation history cleared.', 'success', 'Settings Reset');
    } catch (error) {
      console.error('Error resetting AI SDK settings:', error);
      showToast(error.response?.data?.error || 'An error occurred while resetting AI SDK settings.', 'danger', 'Reset Error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleProviderSelect = (value, setLLMState, setIsCustom) => {
    if (value === '__custom__') {
      setIsCustom(true);
      setLLMState((prev) => ({ ...prev, provider: '' }));
    } else {
      setIsCustom(false);
      setLLMState((prev) => ({ ...prev, provider: value }));
    }
  };

  const renderProviderField = (llmState, setLLMState, isCustom, setIsCustom) => {
    if (isCustom) {
      return (
        <div className="d-flex gap-1">
          <Form.Control
            size="sm"
            type="text"
            placeholder="Custom provider name"
            value={llmState.provider}
            onChange={(e) => setLLMState((prev) => ({ ...prev, provider: e.target.value }))}
          />
          <Button
            size="sm"
            variant="outline-secondary"
            onClick={() => setIsCustom(false)}
            title="Switch back to provider list"
          >
            &#x2630;
          </Button>
        </div>
      );
    }
    return (
      <Form.Select
        size="sm"
        value={llmState.provider}
        onChange={(e) => handleProviderSelect(e.target.value, setLLMState, setIsCustom)}
      >
        <option value="">Select provider...</option>
        {validProviders.map((p) => (
          <option key={p} value={p}>{p}</option>
        ))}
        <option value="__custom__">Custom...</option>
      </Form.Select>
    );
  };

  const renderLLMSection = (title, llmState, setLLMState, isCustom, setIsCustom) => (
    <div className="mb-3">
      <h6 className="mb-2 small fw-bold">{title}</h6>
      <div className="row g-2">
        <div className="col-md-6">
          <Form.Group className="mb-2">
            <Form.Label className="small">Provider</Form.Label>
            {renderProviderField(llmState, setLLMState, isCustom, setIsCustom)}
          </Form.Group>
        </div>
        <div className="col-md-6">
          <Form.Group className="mb-2">
            <Form.Label className="small">Model</Form.Label>
            <Form.Control
              size="sm"
              type="text"
              placeholder="e.g., gpt-5.2-none, gemini-2.5-flash"
              value={llmState.model}
              onChange={(e) => setLLMState((prev) => ({ ...prev, model: e.target.value }))}
            />
          </Form.Group>
        </div>
        <div className="col-md-6">
          <Form.Group className="mb-2">
            <Form.Label className="small">Temperature (0.0 - 2.0)</Form.Label>
            <Form.Control
              size="sm"
              type="number"
              step="0.1"
              min="0.0"
              max="2.0"
              placeholder="e.g., 0.7"
              value={llmState.temperature}
              onChange={(e) => setLLMState((prev) => ({ ...prev, temperature: e.target.value }))}
            />
          </Form.Group>
        </div>
        <div className="col-md-6">
          <Form.Group className="mb-2">
            <Form.Label className="small">Max Output Tokens</Form.Label>
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
    <>
    <Modal show={show} onHide={handleClose} size="lg" centered>
      <Modal.Header closeButton data-bs-theme="light">
        <Modal.Title>AI SDK Settings</Modal.Title>
      </Modal.Header>
      <Modal.Body style={{ maxHeight: '70vh', overflowY: 'auto' }}>
        <Alert variant="info" className="mb-3 py-2">
          <small>
            <strong>Note:</strong> Fields are pre-filled with the current AI SDK configuration.
            Changing LLM settings will clear your conversation history.
            Your settings are saved and will be restored on your next login.
          </small>
        </Alert>
        {((aiSDKBaseLLM.provider && sdkDefaults.base.provider &&
            aiSDKBaseLLM.provider.toLowerCase() !== sdkDefaults.base.provider.toLowerCase()) ||
          (deepQueryActive && aiSDKThinkingLLM.provider && sdkDefaults.thinking.provider &&
            aiSDKThinkingLLM.provider.toLowerCase() !== sdkDefaults.thinking.provider.toLowerCase())) && (
          <Alert variant="warning" className="mb-3 py-2">
            <small>
              <strong>Important:</strong> If you select a different provider or model, make sure the corresponding
              API keys are already configured in <code>sdk_config.env</code>. Authentication credentials must be set before
              starting the AI SDK.
            </small>
          </Alert>
        )}

        {isFetching ? (
          <div className="text-center py-4">
            <Spinner animation="border" size="sm" />
            <span className="ms-2">Loading current settings...</span>
          </div>
        ) : (
          <Form id="sdk-settings-form" onSubmit={handleSubmit}>
            {renderLLMSection(
              'Base LLM', aiSDKBaseLLM, setAISDKBaseLLM,
              isCustomBaseProvider, setIsCustomBaseProvider
            )}
            {!sdkDeepQueryEnabled ? (
              <Alert variant="warning" className="mb-3 py-2">
                <small>
                  <strong>DeepQuery disabled:</strong> No thinking model is configured in the AI SDK.
                  Thinking LLM and execution model settings are not available.
                  Configure <code>THINKING_LLM_PROVIDER</code> and <code>THINKING_LLM_MODEL</code> in{' '}
                  <code>sdk_config.env</code> to enable DeepQuery.
                </small>
              </Alert>
            ) : !chatbotDeepQueryEnabled ? (
              <Alert variant="info" className="mb-3 py-2">
                <small>
                  <strong>DeepQuery disabled at chatbot level:</strong> The AI SDK has a thinking model
                  configured, but DeepQuery is disabled in the chatbot (<code>CHATBOT_DEEPQUERY=0</code>).
                  Thinking LLM settings are not available until DeepQuery is enabled in{' '}
                  <code>chatbot_config.env</code>.
                </small>
              </Alert>
            ) : (
              <>
                {renderLLMSection(
                  'Thinking LLM', aiSDKThinkingLLM, setAISDKThinkingLLM,
                  isCustomThinkingProvider, setIsCustomThinkingProvider
                )}
                <Form.Group className="mb-3">
                  <Form.Check
                    type="checkbox"
                    className="small"
                    label="Use Base LLM for execution (default: Thinking LLM for both)"
                    checked={useBaseLLMForExecution}
                    onChange={(e) => setUseBaseLLMForExecution(e.target.checked)}
                  />
                </Form.Group>
              </>
            )}
            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                className="small"
                label="Enable ambiguity detection in the AI SDK (ask for clarification on ambiguous questions)"
                checked={checkAmbiguity}
                onChange={(e) => setCheckAmbiguity(e.target.checked)}
              />
            </Form.Group>
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
          form="sdk-settings-form"
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

export default AISDKSettingsModal;
