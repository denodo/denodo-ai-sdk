import React, { useState, useEffect } from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";
import Alert from "react-bootstrap/Alert";
import Spinner from "react-bootstrap/Spinner";
import Tabs from "react-bootstrap/Tabs";
import Tab from "react-bootstrap/Tab";
import NotificationToast from "../NotificationToast/NotificationToast";
import CustomTooltip from "../CustomTooltip/CustomTooltip";
import { useConfig } from "../../contexts/ConfigContext";
import api from "../../api/client";

const assetBaseUrl = import.meta.env.BASE_URL;

export const AI_SDK_STORAGE_KEY = "ai_sdk_llm_settings";
export const CHATBOT_STORAGE_KEY = "chatbot_llm_settings";

export const getDict = (username, dictName) => {
  try {
    const stored = localStorage.getItem(`${username}_${dictName}`);
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
};

export const saveDict = (username, dictName, dict) => {
  try {
    localStorage.setItem(`${username}_${dictName}`, JSON.stringify(dict));
  } catch (e) {
    console.error(`Error saving ${dictName}:`, e);
  }
};

const SettingsModal = ({
  show,
  handleClose,
  handleClearResults,
  selectedChatbot,
  onSettingsApplied,
  title,
}) => {
  const [activeTab, setActiveTab] = useState("info");
  const [isLoading, setIsLoading] = useState(false);
  const [isFetching, setIsFetching] = useState(false);

  const { config } = useConfig();

  const [validProviders, setValidProviders] = useState([]);
  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: "",
    variant: "info",
    title: "Notification",
    duration: 5000,
  });

  const [customInstructions, setCustomInstructions] = useState("");

  const [aiSDKBaseLLM, setAISDKBaseLLM] = useState({
    provider: "",
    model: "",
    temperature: "",
    max_tokens: "",
  });
  const [aiSDKThinkingLLM, setAISDKThinkingLLM] = useState({
    provider: "",
    model: "",
    temperature: "",
    max_tokens: "",
  });
  const [useBaseLLMForExecution, setUseBaseLLMForExecution] = useState(false);
  const [checkAmbiguity, setCheckAmbiguity] = useState(true);
  const [isCustomBaseProvider, setIsCustomBaseProvider] = useState(false);
  const [isCustomThinkingProvider, setIsCustomThinkingProvider] =
    useState(false);
  const [sdkDefaults, setSdkDefaults] = useState({ base: {}, thinking: {} });
  const [sdkDeepQueryEnabled, setSdkDeepQueryEnabled] = useState(false);

  const [chatbotLLM, setChatbotLLM] = useState({
    provider: "",
    model: "",
    temperature: "",
    max_tokens: "",
  });
  const [isCustomChatbotProvider, setIsCustomChatbotProvider] = useState(false);
  const [chatbotDefaults, setChatbotDefaults] = useState({});
  const [chatbotDeepQueryEnabled, setChatbotDeepQueryEnabled] = useState(false);

  const agentKey = selectedChatbot
    ? selectedChatbot.isGlobal
      ? "global"
      : selectedChatbot.id
    : "global";
  const isSpecializedChat = selectedChatbot && !selectedChatbot.isGlobal;
  const isGlobalChat = selectedChatbot && selectedChatbot.isGlobal;

  const canEditLLM = config?.user_edit_llm;
  const canAddCustomInstructions = config?.can_add_custom_instructions;

  const showToast = (message, variant, toastTitle, duration = 5000) => {
    setToastConfig({
      show: true,
      message,
      variant,
      title: toastTitle,
      duration,
    });
  };

  const handleToastClose = () => {
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  const handleOnExited = () => {
    setActiveTab("info");
    setIsLoading(false);
  };

  useEffect(() => {
    if (!show) return;

    const fetchSettings = async () => {
      setIsFetching(true);
      try {
        const response = await api.get("llm_settings");
        const data = response.data;

        const sdkInfo = data.ai_sdk_info || {};
        const providers = sdkInfo.valid_providers || [];

        const baseDefaults =
          Object.keys(data.ai_sdk_base_llm_defaults || {}).length > 0
            ? data.ai_sdk_base_llm_defaults
            : sdkInfo.base_llm || {};

        const thinkingDefaults =
          Object.keys(data.ai_sdk_thinking_llm_defaults || {}).length > 0
            ? data.ai_sdk_thinking_llm_defaults
            : sdkInfo.thinking_llm || {};

        const chatbotServerDefaults = data.chatbot_llm_defaults || {};

        const basePrefs = data.ai_sdk_base_llm_preferences || {};
        const thinkingPrefs = data.ai_sdk_thinking_llm_preferences || {};
        const chatbotPrefs = data.chatbot_llm_preferences || {};

        setValidProviders(providers);

        const hasThinkingModel =
          sdkInfo.thinking_llm != null ||
          Object.keys(data.ai_sdk_thinking_llm_defaults || {}).length > 0;
        setSdkDeepQueryEnabled(hasThinkingModel);
        setChatbotDeepQueryEnabled(data.chatbot_deepquery ?? false);
        setSdkDefaults({ base: baseDefaults, thinking: thinkingDefaults });
        setChatbotDefaults(chatbotServerDefaults);

        const effectiveBaseProvider =
          basePrefs.provider || baseDefaults.provider || "";
        const effectiveBaseSettings = {
          provider: effectiveBaseProvider,
          model: basePrefs.model || baseDefaults.model || "",
          temperature: basePrefs.temperature ?? baseDefaults.temperature ?? "",
          max_tokens: basePrefs.max_tokens || baseDefaults.max_tokens || "",
        };

        const effectiveThinkingProvider =
          thinkingPrefs.provider || thinkingDefaults.provider || "";
        const effectiveThinkingSettings = {
          provider: effectiveThinkingProvider,
          model: thinkingPrefs.model || thinkingDefaults.model || "",
          temperature:
            thinkingPrefs.temperature ?? thinkingDefaults.temperature ?? "",
          max_tokens:
            thinkingPrefs.max_tokens || thinkingDefaults.max_tokens || "",
        };

        const checkAmbVal =
          data.check_ambiguity ?? sdkInfo.check_ambiguity ?? true;

        const execModelFromData = data.use_base_llm_for_execution;
        const useBaseExecVal =
          execModelFromData !== null && execModelFromData !== undefined
            ? execModelFromData
            : sdkInfo.deepquery_execution_model === "base";

        const effectiveChatbotProvider =
          chatbotPrefs.provider || chatbotServerDefaults.provider || "";
        const effectiveChatbotSettings = {
          provider: effectiveChatbotProvider,
          model: chatbotPrefs.model || chatbotServerDefaults.model || "",
          temperature:
            chatbotPrefs.temperature ?? chatbotServerDefaults.temperature ?? "",
          max_tokens:
            chatbotPrefs.max_tokens || chatbotServerDefaults.max_tokens || "",
        };

        const username = localStorage.getItem("current_user") || "";
        if (username) {
          const customInstDict = getDict(username, "custom_instructions_dict");
          setCustomInstructions(customInstDict[agentKey] || "");

          if (canEditLLM) {
            const aiSdkLlmDict = getDict(username, "ai_sdk_llm_settings_dict");
            aiSdkLlmDict[agentKey] = {
              ai_sdk_base_llm: effectiveBaseSettings,
              check_ambiguity: checkAmbVal,
              ...(hasThinkingModel &&
                data.chatbot_deepquery && {
                  ai_sdk_thinking_llm: effectiveThinkingSettings,
                  use_base_llm_for_execution: useBaseExecVal,
                }),
            };
            saveDict(username, "ai_sdk_llm_settings_dict", aiSdkLlmDict);

            const chatbotLlmDict = getDict(
              username,
              "chatbot_llm_settings_dict",
            );
            chatbotLlmDict[agentKey] = effectiveChatbotSettings;
            saveDict(username, "chatbot_llm_settings_dict", chatbotLlmDict);
          }
        }

        setAISDKBaseLLM(effectiveBaseSettings);
        setAISDKThinkingLLM(effectiveThinkingSettings);
        setChatbotLLM(effectiveChatbotSettings);
        setCheckAmbiguity(checkAmbVal);
        setUseBaseLLMForExecution(useBaseExecVal);

        const providersLower = new Set(providers.map((p) => p.toLowerCase()));
        setIsCustomBaseProvider(
          effectiveBaseProvider !== "" &&
            !providersLower.has(effectiveBaseProvider.toLowerCase()),
        );
        setIsCustomThinkingProvider(
          effectiveThinkingProvider !== "" &&
            !providersLower.has(effectiveThinkingProvider.toLowerCase()),
        );
        setIsCustomChatbotProvider(
          effectiveChatbotProvider !== "" &&
            !providersLower.has(effectiveChatbotProvider.toLowerCase()),
        );
      } catch (error) {
        console.error("Error fetching settings:", error);
      } finally {
        setIsFetching(false);
      }
    };

    fetchSettings();
  }, [show, agentKey, canAddCustomInstructions, canEditLLM]);

  const validateTemperature = (temp) => {
    if (temp === "" || temp === null || temp === undefined) return true;
    const tempFloat = parseFloat(temp);
    return !isNaN(tempFloat) && tempFloat >= 0.0 && tempFloat <= 2.0;
  };

  const validateMaxTokens = (tokens) => {
    if (tokens === "" || tokens === null || tokens === undefined) return true;
    const tokensInt = parseInt(tokens);
    return !isNaN(tokensInt) && tokensInt >= 1024 && tokensInt <= 20000;
  };

  const deepQueryActive = sdkDeepQueryEnabled && chatbotDeepQueryEnabled;

  const validateForm = () => {
    if (!canEditLLM) return true;

    if (
      !validateTemperature(aiSDKBaseLLM.temperature) ||
      !validateTemperature(chatbotLLM.temperature)
    ) {
      showToast(
        "Temperature must be between 0.0 and 2.0",
        "warning",
        "Validation Error",
      );
      return false;
    }
    if (
      !validateMaxTokens(aiSDKBaseLLM.max_tokens) ||
      !validateMaxTokens(chatbotLLM.max_tokens)
    ) {
      showToast(
        "Max Output Tokens must be between 1024 and 20000",
        "warning",
        "Validation Error",
      );
      return false;
    }
    if (deepQueryActive) {
      if (!validateTemperature(aiSDKThinkingLLM.temperature)) {
        showToast(
          "AI SDK Thinking LLM Temperature must be between 0.0 and 2.0",
          "warning",
          "Validation Error",
        );
        return false;
      }
      if (!validateMaxTokens(aiSDKThinkingLLM.max_tokens)) {
        showToast(
          "AI SDK Thinking LLM Max Output Tokens must be between 1024 and 20000",
          "warning",
          "Validation Error",
        );
        return false;
      }
    }
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateForm()) return;

    setIsLoading(true);
    try {
      const username = localStorage.getItem("current_user") || "";

      if (username && canAddCustomInstructions) {
        const userDetails =
          localStorage.getItem(`${username}_user_details`) || "";
        await api.post("update_custom_instructions", {
          custom_instructions: customInstructions,
          user_details: userDetails,
        });

        const customInstDict = getDict(username, "custom_instructions_dict");
        customInstDict[agentKey] = customInstructions;
        saveDict(username, "custom_instructions_dict", customInstDict);
      }

      if (username && canEditLLM) {
        const payload = {
          ai_sdk_base_llm: aiSDKBaseLLM,
          check_ambiguity: checkAmbiguity,
          ...(deepQueryActive && {
            ai_sdk_thinking_llm: aiSDKThinkingLLM,
            use_base_llm_for_execution: useBaseLLMForExecution,
          }),
          chatbot_llm: chatbotLLM,
        };

        await api.post("update_llm_settings", payload);

        const aiSdkLlmDict = getDict(username, "ai_sdk_llm_settings_dict");
        aiSdkLlmDict[agentKey] = {
          ai_sdk_base_llm: aiSDKBaseLLM,
          check_ambiguity: checkAmbiguity,
          ...(deepQueryActive && {
            ai_sdk_thinking_llm: aiSDKThinkingLLM,
            use_base_llm_for_execution: useBaseLLMForExecution,
          }),
        };
        saveDict(username, "ai_sdk_llm_settings_dict", aiSdkLlmDict);

        const chatbotLlmDict = getDict(username, "chatbot_llm_settings_dict");
        chatbotLlmDict[agentKey] = chatbotLLM;
        saveDict(username, "chatbot_llm_settings_dict", chatbotLlmDict);
      }

      if (onSettingsApplied && selectedChatbot) {
        await onSettingsApplied(selectedChatbot);
      } else if (handleClearResults) {
        await handleClearResults();
      }

      showToast(
        "Settings updated. Conversation history cleared.",
        "success",
        "Settings Updated",
      );
      handleClose();
    } catch (error) {
      console.error("Error updating settings:", error);
      showToast(
        error.response?.data?.error ||
          "An error occurred while updating settings.",
        "danger",
        "Update Error",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetToDefaults = async () => {
    setIsLoading(true);
    try {
      await api.post("reset_llm_settings", { component: activeTab });

      const username = localStorage.getItem("current_user") || "";

      if (activeTab === "ai_sdk" && username) {
        const aiSdkLlmDict = getDict(username, "ai_sdk_llm_settings_dict");
        delete aiSdkLlmDict[agentKey];
        saveDict(username, "ai_sdk_llm_settings_dict", aiSdkLlmDict);
      } else if (activeTab === "chatbot" && username) {
        const chatbotLlmDict = getDict(username, "chatbot_llm_settings_dict");
        delete chatbotLlmDict[agentKey];
        saveDict(username, "chatbot_llm_settings_dict", chatbotLlmDict);
      }

      if (onSettingsApplied && selectedChatbot) {
        await onSettingsApplied(selectedChatbot);
      } else if (handleClearResults) {
        await handleClearResults();
      }

      showToast(
        `${activeTab === "ai_sdk" ? "AI SDK" : "Chatbot"} settings reset to defaults. Conversation history cleared.`,
        "success",
        "Settings Reset",
      );
      handleClose();
    } catch (error) {
      console.error("Error resetting settings:", error);
      showToast(
        error.response?.data?.error ||
          "An error occurred while resetting settings.",
        "danger",
        "Reset Error",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleProviderSelect = (value, setLLMState, setIsCustom) => {
    if (value === "__custom__") {
      setIsCustom(true);
      setLLMState((prev) => ({ ...prev, provider: "" }));
    } else {
      setIsCustom(false);
      setLLMState((prev) => ({ ...prev, provider: value }));
    }
  };

  const renderProviderField = (
    llmState,
    setLLMState,
    isCustom,
    setIsCustom,
  ) => {
    if (isCustom) {
      return (
        <div className="d-flex gap-1">
          <Form.Control
            size="sm"
            type="text"
            placeholder="Custom provider name"
            value={llmState.provider}
            onChange={(e) =>
              setLLMState((prev) => ({ ...prev, provider: e.target.value }))
            }
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
        onChange={(e) =>
          handleProviderSelect(e.target.value, setLLMState, setIsCustom)
        }
      >
        <option value="">Select provider...</option>
        {validProviders.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
        <option value="__custom__">Custom...</option>
      </Form.Select>
    );
  };

  const renderLLMSection = (
    sectionTitle,
    llmState,
    setLLMState,
    isCustom,
    setIsCustom,
  ) => (
    <div className="mb-3">
      {sectionTitle && <h6 className="mb-2 small fw-bold">{sectionTitle}</h6>}
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
              onChange={(e) =>
                setLLMState((prev) => ({ ...prev, model: e.target.value }))
              }
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
              onChange={(e) =>
                setLLMState((prev) => ({
                  ...prev,
                  temperature: e.target.value,
                }))
              }
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
              onChange={(e) =>
                setLLMState((prev) => ({ ...prev, max_tokens: e.target.value }))
              }
            />
          </Form.Group>
        </div>
      </div>
    </div>
  );

  const showSDKWarning =
    (aiSDKBaseLLM.provider &&
      sdkDefaults.base?.provider &&
      aiSDKBaseLLM.provider.toLowerCase() !==
        sdkDefaults.base.provider.toLowerCase()) ||
    (deepQueryActive &&
      aiSDKThinkingLLM.provider &&
      sdkDefaults.thinking?.provider &&
      aiSDKThinkingLLM.provider.toLowerCase() !==
        sdkDefaults.thinking.provider.toLowerCase());

  const showChatbotWarning =
    chatbotLLM.provider &&
    chatbotDefaults.provider &&
    chatbotLLM.provider.toLowerCase() !==
      chatbotDefaults.provider.toLowerCase();

  const tooltipInstructionContent = isSpecializedChat
    ? "Passed to the AI SDK's answerQuestion endpoint for view search and VQL generation. These instructions are appended to any existing ones already defined in the AI SDK and the default instructions configured for this agent."
    : "Passed to the AI SDK's answerQuestion endpoint for view search and VQL generation. These instructions are appended to any existing ones already defined in the AI SDK.";

  if (!canEditLLM && !canAddCustomInstructions) return null;

  return (
    <>
      <Modal
        show={show}
        onHide={handleClose}
        onExited={handleOnExited}
        size="lg"
        centered
      >
        <Modal.Header closeButton data-bs-theme="light">
          <Modal.Title>{title}</Modal.Title>
        </Modal.Header>
        <Modal.Body style={{ maxHeight: "70vh", overflowY: "auto" }}>
          <Alert variant="info" className="mb-3 py-2">
            <small>
              <strong>Note:</strong> Fields are pre-filled with the current
              configurations for this agent. Changing these settings will clear
              your conversation history. Your settings are saved and will be
              restored on your next login.
            </small>
          </Alert>

          {isFetching ? (
            <div className="text-center py-4">
              <Spinner animation="border" size="sm" />
              <span className="ms-2">Loading current settings...</span>
            </div>
          ) : (
            <Form id="combined-settings-form" onSubmit={handleSubmit}>
              <Tabs
                activeKey={activeTab}
                onSelect={(k) => setActiveTab(k)}
                className="mb-3"
              >
                <Tab eventKey="info" title="General">
                  <div className="mt-3">
                    <div
                      className="d-flex align-items-center p-3 mb-4 rounded"
                      style={{
                        backgroundColor: "#f8f9fa",
                        border: "1px solid #e9ecef",
                      }}
                    >
                      <div
                        className="me-3 rounded-circle d-flex justify-content-center align-items-center bg-white border"
                        style={{
                          width: "56px",
                          height: "56px",
                          flexShrink: 0,
                        }}
                      >
                        {isGlobalChat ? (
                          <img
                            src={`${assetBaseUrl}denodo_chat_transparent.png`}
                            alt="General Chat"
                            style={{
                              height: "32px",
                              width: "32px",
                              objectFit: "contain",
                            }}
                            onError={(e) => {
                              e.target.style.display = "none";
                              e.target.nextSibling.style.display =
                                "inline-block";
                            }}
                          />
                        ) : selectedChatbot?.icon ? (
                          <img
                            src={selectedChatbot.icon}
                            alt={selectedChatbot.name}
                            style={{
                              height: "32px",
                              width: "32px",
                              objectFit: "contain",
                            }}
                            onError={(e) => {
                              e.target.style.display = "none";
                              e.target.nextSibling.style.display =
                                "inline-block";
                            }}
                          />
                        ) : null}
                        <i
                          className={
                              isGlobalChat
                              ? "bi bi-chat-left-text"
                              : "bi bi-robot"
                          }
                          style={{
                            fontSize: "1.5rem",
                            color: "#143142",
                            display:
                              isGlobalChat || selectedChatbot?.icon
                                ? "none"
                                : "inline-block",
                          }}
                        ></i>
                      </div>
                      <div>
                        <h5 className="mb-1 fw-bold text-dark">
                          {selectedChatbot?.name || "General Chat"}
                        </h5>
                        <span
                          className="text-muted"
                          style={{ fontSize: "0.9rem" }}
                        >
                          {selectedChatbot?.description ||
                            "No description provided for this agent."}
                        </span>
                      </div>
                    </div>

                    {canAddCustomInstructions && (
                      <Form.Group
                        controlId="formCustomInstructions"
                        className="mb-3"
                      >
                        <Form.Label className="fw-semibold d-flex align-items-center">
                          Custom Instructions
                          <CustomTooltip
                            id="tooltip-custom-instructions"
                            content={tooltipInstructionContent}
                          >
                            <i
                              className="bi bi-info-circle ms-2"
                              style={{
                                cursor: "help",
                                fontSize: "0.85rem",
                                color: "#adb5bd",
                                transition: "color 0.2s",
                              }}
                              onMouseEnter={(e) =>
                                (e.target.style.color = "#112533")
                              }
                              onMouseLeave={(e) =>
                                (e.target.style.color = "#adb5bd")
                              }
                            ></i>
                          </CustomTooltip>
                        </Form.Label>
                        <Form.Control
                          as="textarea"
                          rows={6}
                          placeholder="Enter custom instructions here..."
                          value={customInstructions}
                          onChange={(e) =>
                            setCustomInstructions(e.target.value)
                          }
                          style={{ resize: "none" }}
                        />
                      </Form.Group>
                    )}
                  </div>
                </Tab>

                {canEditLLM && (
                  <Tab eventKey="ai_sdk" title="AI SDK">
                    <div className="mt-3">
                      {showSDKWarning && (
                        <Alert variant="warning" className="mb-3 py-2">
                          <small>
                            <strong>Important:</strong> If you select a
                            different provider or model, make sure the
                            corresponding API keys are already configured in{" "}
                            <code>sdk_config.env</code>.
                          </small>
                        </Alert>
                      )}

                      {renderLLMSection(
                        "Base LLM",
                        aiSDKBaseLLM,
                        setAISDKBaseLLM,
                        isCustomBaseProvider,
                        setIsCustomBaseProvider,
                      )}

                      {!sdkDeepQueryEnabled ? (
                        <Alert variant="warning" className="mb-3 py-2">
                          <small>
                            <strong>DeepQuery disabled:</strong> No thinking
                            model is configured in the AI SDK. Thinking LLM and
                            execution model settings are not available.
                            Configure <code>THINKING_LLM_PROVIDER</code> and{" "}
                            <code>THINKING_LLM_MODEL</code> in{" "}
                            <code>sdk_config.env</code> to enable DeepQuery.
                          </small>
                        </Alert>
                      ) : !chatbotDeepQueryEnabled ? (
                        <Alert variant="info" className="mb-3 py-2">
                          <small>
                            <strong>
                              DeepQuery disabled at chatbot level:
                            </strong>{" "}
                            The AI SDK has a thinking model configured, but
                            DeepQuery is disabled in the chatbot (
                            <code>CHATBOT_DEEPQUERY=0</code>). Thinking LLM
                            settings are not available until DeepQuery is
                            enabled in <code>chatbot_config.env</code>.
                          </small>
                        </Alert>
                      ) : (
                        <>
                          {renderLLMSection(
                            "Thinking LLM",
                            aiSDKThinkingLLM,
                            setAISDKThinkingLLM,
                            isCustomThinkingProvider,
                            setIsCustomThinkingProvider,
                          )}
                          <Form.Group className="mb-3">
                            <Form.Check
                              type="checkbox"
                              className="small"
                              label="Use Base LLM for execution (default: Thinking LLM for both)"
                              checked={useBaseLLMForExecution}
                              onChange={(e) =>
                                setUseBaseLLMForExecution(e.target.checked)
                              }
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
                    </div>
                  </Tab>
                )}

                {canEditLLM && (
                  <Tab eventKey="chatbot" title="Chatbot">
                    <div className="mt-3">
                      {showChatbotWarning && (
                        <Alert variant="warning" className="mb-3 py-2">
                          <small>
                            <strong>Important:</strong> If you select a
                            different provider or model, make sure the
                            corresponding API keys are already configured in{" "}
                            <code>chatbot_config.env</code>.
                          </small>
                        </Alert>
                      )}

                      {renderLLMSection(
                        "",
                        chatbotLLM,
                        setChatbotLLM,
                        isCustomChatbotProvider,
                        setIsCustomChatbotProvider,
                      )}
                    </div>
                  </Tab>
                )}
              </Tabs>
            </Form>
          )}
        </Modal.Body>

        <Modal.Footer>
          {activeTab !== "info" && canEditLLM ? (
            <Button
              variant="outline-danger"
              size="sm"
              onClick={handleResetToDefaults}
              disabled={isLoading || isFetching}
              className="me-auto"
              title={`Reset only the ${activeTab === "ai_sdk" ? "AI SDK" : "Chatbot"} settings`}
            >
              Reset {activeTab === "ai_sdk" ? "AI SDK" : "Chatbot"} defaults and save
            </Button>
          ) : (
            <div className="me-auto"></div>
          )}

          <Button variant="light" onClick={handleClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            variant="dark"
            type="submit"
            form="combined-settings-form"
            disabled={isLoading || isFetching}
          >
            {isLoading ? (
              <>
                <Spinner
                  as="span"
                  animation="border"
                  size="sm"
                  role="status"
                  aria-hidden="true"
                />
                <span className="ms-2">Saving...</span>
              </>
            ) : (
              "Save"
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

export default SettingsModal;
