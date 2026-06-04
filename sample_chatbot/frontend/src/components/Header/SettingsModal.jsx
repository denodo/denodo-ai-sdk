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

const readInstructionEntry = (dict, key) => {
  const raw = dict[key];
  if (!raw) return { ai_sdk: "", chatbot: "" };
  if (typeof raw === "string") return { ai_sdk: raw, chatbot: "" };
  return {
    ai_sdk: raw.ai_sdk || "",
    chatbot: raw.chatbot || "",
  };
};

/** Map API/YAML provider string to the option value from valid_providers (case-insensitive). */
const canonicalProviderForSelect = (provider, validProviders) => {
  if (!provider || !validProviders?.length) return provider || "";
  const match = validProviders.find(
    (p) => p.toLowerCase() === String(provider).toLowerCase(),
  );
  if (match === undefined) return provider;
  return match;
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

  const [chatbotInstructions, setChatbotInstructions] = useState("");
  const [aiSdkUserInstructions, setAiSdkUserInstructions] = useState("");

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
  const [defaultCustomInstructions, setDefaultCustomInstructions] = useState({
    chatbot: "",
    ai_sdk: "",
  });

  const agentKey = selectedChatbot
    ? selectedChatbot.isGlobal
      ? "global"
      : selectedChatbot.id
    : "global";
  const isGlobalChat = selectedChatbot && selectedChatbot.isGlobal;

  const canEditLLM = config?.user_edit_llm;
  const canEditInstructions = config?.can_edit_instructions;

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

        const effectiveBaseProvider = canonicalProviderForSelect(
          basePrefs.provider || baseDefaults.provider || "",
          providers,
        );
        const effectiveBaseSettings = {
          provider: effectiveBaseProvider,
          model: basePrefs.model || baseDefaults.model || "",
          temperature: basePrefs.temperature ?? baseDefaults.temperature ?? "",
          max_tokens: basePrefs.max_tokens || baseDefaults.max_tokens || "",
        };

        const effectiveThinkingProvider = canonicalProviderForSelect(
          thinkingPrefs.provider || thinkingDefaults.provider || "",
          providers,
        );
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

        const effectiveChatbotProvider = canonicalProviderForSelect(
          chatbotPrefs.provider || chatbotServerDefaults.provider || "",
          providers,
        );
        const effectiveChatbotSettings = {
          provider: effectiveChatbotProvider,
          model: chatbotPrefs.model || chatbotServerDefaults.model || "",
          temperature:
            chatbotPrefs.temperature ?? chatbotServerDefaults.temperature ?? "",
          max_tokens:
            chatbotPrefs.max_tokens || chatbotServerDefaults.max_tokens || "",
        };

        const defs = data.default_custom_instructions || {};
        setDefaultCustomInstructions({
          chatbot: defs.chatbot || "",
          ai_sdk: defs.ai_sdk || "",
        });
        const username = localStorage.getItem("current_user") || "";
        const customInstDict = username
          ? getDict(username, "custom_instructions_dict")
          : {};
        const hasStored =
          username &&
          Object.prototype.hasOwnProperty.call(customInstDict, agentKey);
        const entry = readInstructionEntry(customInstDict, agentKey);
        if (!hasStored) {
          setChatbotInstructions(entry.chatbot || defs.chatbot || "");
          setAiSdkUserInstructions(entry.ai_sdk || defs.ai_sdk || "");
        } else {
          setChatbotInstructions(entry.chatbot);
          setAiSdkUserInstructions(entry.ai_sdk);
        }

        if (username) {
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
  }, [show, agentKey, canEditInstructions, canEditLLM]);

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

      if (username && canEditInstructions) {
        const userDetails =
          localStorage.getItem(`${username}_user_details`) || "";
        const customInstDict = getDict(username, "custom_instructions_dict");
        customInstDict[agentKey] = {
          ai_sdk: aiSdkUserInstructions,
          chatbot: chatbotInstructions,
        };
        await api.post("update_custom_instructions", {
          custom_instructions: customInstDict,
          user_details: userDetails,
        });

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
      const response = await api.get("llm_settings");
      const data = response.data;
      const sdkInfo = data.ai_sdk_info || {};

      const baseDefaults =
        Object.keys(data.ai_sdk_base_llm_defaults || {}).length > 0
          ? data.ai_sdk_base_llm_defaults
          : sdkInfo.base_llm || {};

      const thinkingDefaults =
        Object.keys(data.ai_sdk_thinking_llm_defaults || {}).length > 0
          ? data.ai_sdk_thinking_llm_defaults
          : sdkInfo.thinking_llm || {};

      const chatbotServerDefaults = data.chatbot_llm_defaults || {};
      const providersLower = new Set(
        validProviders.map((p) => p.toLowerCase()),
      );

      const markCustom = (provider) =>
        provider !== "" && !providersLower.has(provider.toLowerCase());

      if (activeTab === "agent_llm") {
        const p = canonicalProviderForSelect(
          chatbotServerDefaults.provider || "",
          validProviders,
        );
        setChatbotLLM({
          provider: p,
          model: chatbotServerDefaults.model || "",
          temperature: chatbotServerDefaults.temperature ?? "",
          max_tokens: chatbotServerDefaults.max_tokens || "",
        });
        setIsCustomChatbotProvider(markCustom(p));
      } else if (activeTab === "ai_sdk") {
        const baseP = canonicalProviderForSelect(
          baseDefaults.provider || "",
          validProviders,
        );
        setAISDKBaseLLM({
          provider: baseP,
          model: baseDefaults.model || "",
          temperature: baseDefaults.temperature ?? "",
          max_tokens: baseDefaults.max_tokens || "",
        });
        setIsCustomBaseProvider(markCustom(baseP));

        const hasThinkingModel =
          sdkInfo.thinking_llm != null ||
          Object.keys(data.ai_sdk_thinking_llm_defaults || {}).length > 0;
        const deepQ = hasThinkingModel && (data.chatbot_deepquery ?? false);

        if (deepQ) {
          const thP = canonicalProviderForSelect(
            thinkingDefaults.provider || "",
            validProviders,
          );
          setAISDKThinkingLLM({
            provider: thP,
            model: thinkingDefaults.model || "",
            temperature: thinkingDefaults.temperature ?? "",
            max_tokens: thinkingDefaults.max_tokens || "",
          });
          setIsCustomThinkingProvider(markCustom(thP));
          const defExec = data.use_base_llm_for_execution_default;
          setUseBaseLLMForExecution(
            defExec !== null && defExec !== undefined
              ? defExec
              : sdkInfo.deepquery_execution_model === "base",
          );
        }

        const defAmb = data.check_ambiguity_default;
        setCheckAmbiguity(
          defAmb !== null && defAmb !== undefined ? defAmb : true,
        );

        const defs = data.default_custom_instructions || {};
        setDefaultCustomInstructions((prev) => ({
          ...prev,
          ai_sdk: defs.ai_sdk || "",
        }));
        setAiSdkUserInstructions(defs.ai_sdk || "");
      }

      showToast(
        activeTab === "ai_sdk"
          ? "AI SDK custom instructions, LLM options, and related settings restored to server defaults. Save to apply."
          : "LLM fields restored to server defaults. Save to apply.",
        "info",
        "Defaults restored",
      );
    } catch (error) {
      console.error("Error loading defaults:", error);
      showToast(
        error.response?.data?.error ||
          "Could not load default settings to restore the form.",
        "danger",
        "Reset Error",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetGeneralDefaults = () => {
    setChatbotInstructions(defaultCustomInstructions.chatbot);
    showToast(
      "General (agent) instructions reset to server defaults. Save to apply.",
      "info",
      "Defaults restored",
    );
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

  const tooltipAiSdkInstructionsContent =
    "Only the data query path (e.g. data_search tool) uses this text as request custom_instructions. The AI SDK server appends it after CUSTOM_INSTRUCTIONS from sdk_config.env. The metadata search path does not use an LLM the same way.";

  if (!canEditLLM && !canEditInstructions) return null;

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

                    {canEditInstructions && (
                      <Form.Group
                        controlId="formChatbotInstructions"
                        className="mb-3"
                      >
                        <Form.Label className="fw-semibold mb-1">
                          How should the agent behave?
                        </Form.Label>
                        <Form.Control
                          as="textarea"
                          rows={6}
                          placeholder="For example: always answer in Spanish, or always reference a specific view when answering."
                          value={chatbotInstructions}
                          onChange={(e) =>
                            setChatbotInstructions(e.target.value)
                          }
                          style={{ resize: "none" }}
                        />
                      </Form.Group>
                    )}
                  </div>
                </Tab>

                {canEditLLM && (
                  <Tab eventKey="agent_llm" title="LLM">
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

                {canEditLLM && (
                  <Tab eventKey="ai_sdk" title="AI SDK">
                    <div className="mt-3">
                      <div
                        className="mb-4 p-3 rounded border"
                        style={{ backgroundColor: "#f8f9fa" }}
                      >
                        <h6
                          className="text-uppercase text-secondary mb-2"
                          style={{ fontSize: "0.7rem", letterSpacing: "0.04em" }}
                        >
                          How the agent and the AI SDK work together
                        </h6>
                        <p className="small text-muted mb-2">
                          The <strong>agent</strong> works with the tools exposed
                          in the <strong>AI SDK</strong> to satisfy the
                          user&apos;s requests.
                        </p>
                        <ul
                          className="small text-muted mb-0 ps-3"
                          style={{ listStyleType: "disc" }}
                        >
                          <li className="mb-1">
                            <code>data_agent</code> is a specialized subagent
                            that turns natural language into VQL and executes
                            it, so the agent can focus on orchestration and
                            leave VQL generation to the subagent.
                          </li>
                          <li className="mb-1">
                            <code>metadata_search</code> is a vector search tool
                            that allows the agent to explore the views vectorized
                            in the vectorDB.
                          </li>
                          <li className="mb-0">
                            <code>deep_query</code> is a specialized subagent
                            focused on complex, long-running, analytical tasks.
                          </li>
                        </ul>
                      </div>

                      {canEditInstructions && (
                        <Form.Group
                          controlId="formAiSdkInstructions"
                          className="mb-4"
                        >
                          <Form.Label className="fw-semibold d-flex align-items-center">
                            How should the AI SDK behave?
                            <CustomTooltip
                              id="tooltip-ai-sdk-instructions"
                              content={tooltipAiSdkInstructionsContent}
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
                            rows={5}
                            placeholder='For example: always use a descriptive alias for columns when generating VQL'
                            value={aiSdkUserInstructions}
                            onChange={(e) =>
                              setAiSdkUserInstructions(e.target.value)
                            }
                            style={{ resize: "none" }}
                          />
                        </Form.Group>
                      )}

                      <h6
                        className="text-uppercase text-secondary mb-3"
                        style={{ fontSize: "0.7rem", letterSpacing: "0.04em" }}
                      >
                        AI SDK LLMs
                      </h6>

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

                      <div className="row g-3 align-items-start mb-1">
                        <div
                          className={
                            deepQueryActive ? "col-lg-6" : "col-12"
                          }
                        >
                          {renderLLMSection(
                            "Base LLM",
                            aiSDKBaseLLM,
                            setAISDKBaseLLM,
                            isCustomBaseProvider,
                            setIsCustomBaseProvider,
                          )}
                        </div>
                        {deepQueryActive && (
                          <div className="col-lg-6">
                            {renderLLMSection(
                              "Thinking LLM",
                              aiSDKThinkingLLM,
                              setAISDKThinkingLLM,
                              isCustomThinkingProvider,
                              setIsCustomThinkingProvider,
                            )}
                          </div>
                        )}
                      </div>

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
                      ) : null}

                      <div className="mt-2 pt-2 border-top">
                        <h6
                          className="text-uppercase text-secondary mb-2"
                          style={{ fontSize: "0.7rem", letterSpacing: "0.04em" }}
                        >
                          Other AI SDK options
                        </h6>
                        {deepQueryActive && (
                          <Form.Group className="mb-2">
                            <Form.Check
                              type="checkbox"
                              className="small"
                              id="use-base-llm-exec"
                              checked={useBaseLLMForExecution}
                              onChange={(e) =>
                                setUseBaseLLMForExecution(e.target.checked)
                              }
                              label={
                                <span className="d-inline-flex align-items-center">
                                  Use Base LLM for execution in DeepQuery
                                  <CustomTooltip
                                    id="tooltip-use-base-llm-exec"
                                    content="Thinking model will generate the plan and the base model will execute each step. By default, thinking LLM takes care of planning and execution."
                                  >
                                    <i
                                      className="bi bi-info-circle ms-1"
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
                                </span>
                              }
                            />
                          </Form.Group>
                        )}
                        <Form.Group className="mb-0">
                          <Form.Check
                            type="checkbox"
                            className="small"
                            label="Enable ambiguity detection in the AI SDK (ask for clarification on ambiguous questions)"
                            checked={checkAmbiguity}
                            onChange={(e) => setCheckAmbiguity(e.target.checked)}
                          />
                        </Form.Group>
                      </div>
                    </div>
                  </Tab>
                )}
              </Tabs>
            </Form>
          )}
        </Modal.Body>

        <Modal.Footer>
          {activeTab === "info" && canEditInstructions && (
            <Button
              variant="outline-danger"
              size="sm"
              type="button"
              onClick={handleResetGeneralDefaults}
              disabled={isLoading || isFetching}
              className="me-auto"
              title="Reset General settings to server defaults."
            >
              Reset General defaults
            </Button>
          )}
          {activeTab !== "info" && canEditLLM && (
            <Button
              variant="outline-danger"
              size="sm"
              onClick={handleResetToDefaults}
              disabled={isLoading || isFetching}
              className="me-auto"
              title={
                activeTab === "ai_sdk"
                  ? "Reset AI SDK custom instructions, LLM options, and related options to server defaults"
                  : "Reset only the chatbot LLM fields to server defaults"
              }
            >
              Reset {activeTab === "ai_sdk" ? "AI SDK" : "LLM"} defaults
            </Button>
          )}
          {!(
            (activeTab === "info" && canEditInstructions) ||
            (activeTab !== "info" && canEditLLM)
          ) && <div className="me-auto" />}

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
