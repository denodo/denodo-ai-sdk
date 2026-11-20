import React from "react";
import Form from "react-bootstrap/Form";
import CustomTooltip from "../../CustomTooltip/CustomTooltip";

const OMIT_TEMPERATURE_TOOLTIP =
  "Certain LLMs/providers might not accept a temperature parameter. To work with those models/providers in the AI SDK, check this box.";

const AgentSettingsLLMSection = ({
  sectionTitle,
  llmState,
  setLLMState,
  validProviders,
  validateTemperature,
  validateMaxTokens,
  validateContextWindow,
  submitAttempted,
  formatNumber,
  FormattedTokenInput,
  options = {},
}) => {
  const checkboxId = `omit-temperature-${(sectionTitle || "chatbot").replace(/\s+/g, "-").toLowerCase()}`;
  const temperatureInvalid = !llmState.omitTemperature && !validateTemperature(llmState.temperature);
  const maxTokensInvalid = !validateMaxTokens(llmState.max_tokens);
  
  const contextWindowInvalid = options.showContextWindow && !validateContextWindow(llmState.context_window);
  const maxTokensValue = parseInt(llmState.max_tokens, 10);
  const contextWindowValue = parseInt(llmState.context_window, 10);
  
  const maxTokensExceedsContext =
    options.showContextWindow &&
    !contextWindowInvalid &&
    !isNaN(maxTokensValue) &&
    !isNaN(contextWindowValue) &&
    maxTokensValue >= contextWindowValue;

  const maxTokensError = maxTokensInvalid
    ? `Max output tokens must be between ${formatNumber(1024)} and ${formatNumber(20000)}`
    : maxTokensExceedsContext
      ? `Max output tokens must be lower than the context window (${formatNumber(contextWindowValue)})`
      : null;

  return (
    <div className="mb-4">
      {sectionTitle && <h6 className="mb-3 rcc-modal-subtitle">{sectionTitle}</h6>}
      <div className="row g-3">
        <div className="col-md-6">
          <Form.Group className="mb-2">
            <Form.Label className="small fw-semibold">Provider</Form.Label>
            <Form.Select
              size="sm"
              value={llmState.provider}
              onChange={(e) => setLLMState((prev) => ({ ...prev, provider: e.target.value }))}
            >
              <option value="">Select provider...</option>
              {validProviders.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </Form.Select>
          </Form.Group>
        </div>
        <div className="col-md-6">
          <Form.Group className="mb-2">
            <Form.Label className="small fw-semibold">Model</Form.Label>
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
            <Form.Label className="small fw-semibold">Temperature (0.0 - 2.0)</Form.Label>
            <Form.Control
              size="sm"
              type="number"
              step="0.1"
              min="0.0"
              max="2.0"
              placeholder="e.g., 0.7"
              value={llmState.omitTemperature ? "" : llmState.temperature}
              disabled={llmState.omitTemperature}
              isInvalid={temperatureInvalid}
              onChange={(e) => setLLMState((prev) => ({ ...prev, temperature: e.target.value }))}
            />
            {temperatureInvalid && (
              <Form.Control.Feedback type="invalid">
                Temperature must be between 0.0 and 2.0
              </Form.Control.Feedback>
            )}
          </Form.Group>
          <Form.Group className="mb-2 mt-1">
            <Form.Check
              type="checkbox"
              className="small"
              id={checkboxId}
              checked={!!llmState.omitTemperature}
              onChange={(e) => setLLMState((prev) => ({ ...prev, omitTemperature: e.target.checked }))}
              label={
                <span className="d-inline-flex align-items-center form-check-label small">
                  Don't send temperature parameter
                  <CustomTooltip id={`tooltip-${checkboxId}`} content={OMIT_TEMPERATURE_TOOLTIP}>
                    <i className="bi bi-info-circle info-icon ms-1"></i>
                  </CustomTooltip>
                </span>
              }
            />
          </Form.Group>
        </div>
        <div className="col-md-6">
          <Form.Group className="mb-2">
            <Form.Label className="small fw-semibold">Max output tokens</Form.Label>
            <FormattedTokenInput
              value={llmState.max_tokens}
              placeholder={formatNumber(4096)}
              isInvalid={!!maxTokensError}
              error={maxTokensError}
              onValueChange={(digits) => setLLMState((prev) => ({ ...prev, max_tokens: digits }))}
            />
          </Form.Group>
        </div>
      </div>
      {options.showContextWindow && (
        <Form.Group className="mb-2">
          <Form.Label className="small fw-semibold d-inline-flex align-items-center">
            Context window (tokens)
            <CustomTooltip
              id="tooltip-context-window"
              placement="top"
              tooltipClassName="custom-tooltip-wide"
              content={`The chatbot uses this number to track how full the model context is and to manage it automatically. When the next message would leave no room for the answer, older complete question and answer pairs are dropped until the most recent 25% of this window remains, and never more than ${formatNumber(30000)} tokens. If that would still crowd out the answer, fewer turns are kept. The conversation then grows again from there. Set this to the context window of your configured LLM. Different LLMs have different context window sizes, so ask your LLM provider for the specific value to be configured here. Default is ${formatNumber(128000)}.`}
            >
              <i className="bi bi-info-circle info-icon ms-1"></i>
            </CustomTooltip>
          </Form.Label>
          <FormattedTokenInput
            value={llmState.context_window}
            placeholder={formatNumber(128000)}
            isInvalid={contextWindowInvalid && (llmState.context_window !== "" || submitAttempted)}
            error={`Context window must be between ${formatNumber(16000)} and ${formatNumber(10000000)} tokens`}
            onValueChange={(digits) => setLLMState((prev) => ({ ...prev, context_window: digits }))}
          />
        </Form.Group>
      )}
    </div>
  );
};

export default AgentSettingsLLMSection;
