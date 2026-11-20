import React, { useState, useEffect, useRef } from "react";
import PropTypes from "prop-types";
import { BaseModal } from "../../Common/Modal";
import Spinner from "react-bootstrap/Spinner";
import Form from "react-bootstrap/Form";
import Tabs from "react-bootstrap/Tabs";
import Tab from "react-bootstrap/Tab";
import Alert from "react-bootstrap/Alert";
import NotificationToast from "../../NotificationToast/NotificationToast";
import CustomTooltip from "../../CustomTooltip/CustomTooltip";
import AgentSettingsLLMSection from "./AgentSettingsLLMSection";
import { useConfig, useNumberFormat } from "../../../contexts/ConfigContext";
import api from "../../../api/client";
import "./AgentSettingsModal.css";

const assetBaseUrl = import.meta.env.BASE_URL;

const readInstructionEntry = (raw) => {
  if (!raw) return null;
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

const OMIT_TEMPERATURE_VALUE = -1;

const isOmittedTemperature = (temp) => {
  if (temp === "" || temp === null || temp === undefined) return false;
  const parsed = parseFloat(temp);
  return !Number.isNaN(parsed) && parsed === OMIT_TEMPERATURE_VALUE;
};

const toFormLLM = (settings = {}) => {
  const omitTemperature = isOmittedTemperature(settings.temperature);
  return {
    provider: settings.provider || "",
    model: settings.model || "",
    temperature: omitTemperature ? "" : (settings.temperature ?? ""),
    max_tokens: settings.max_tokens || "",
    context_window: settings.context_window || "",
    omitTemperature,
  };
};

const toPayloadLLM = (llmState = {}) => {
  const payload = {
    provider: llmState.provider,
    model: llmState.model,
    temperature: llmState.omitTemperature ? OMIT_TEMPERATURE_VALUE : llmState.temperature,
    max_tokens: llmState.max_tokens,
  };
  if (llmState.context_window !== undefined && llmState.context_window !== "") {
    payload.context_window = Number(llmState.context_window);
  }
  return payload;
};

const digitsOnly = (raw) => String(raw ?? "").replace(/\D/g, "");

// Shows an integer with the thousands separator from the user profile.
// The stored value stays digits-only so save and validation can parse it.
const FormattedTokenInput = ({ value, onValueChange, placeholder, isInvalid = false, error = null }) => {
  const formatNumber = useNumberFormat();
  const inputRef = useRef(null);
  const digitsBeforeCaret = useRef(null);
  const display = value === "" || value == null ? "" : (formatNumber(value) || "");

  useEffect(() => {
    const input = inputRef.current;
    const target = digitsBeforeCaret.current;
    if (!input || target == null) return;
    let position = display.length;
    if (target === 0) {
      position = 0;
    } else {
      let seen = 0;
      for (let index = 0; index < display.length; index += 1) {
        if (/\d/.test(display[index])) seen += 1;
        if (seen >= target) {
          position = index + 1;
          break;
        }
      }
    }
    input.setSelectionRange(position, position);
    digitsBeforeCaret.current = null;
  }, [display]);

  return (
    <>
      <Form.Control
        ref={inputRef}
        size="sm"
        type="text"
        inputMode="numeric"
        autoComplete="off"
        placeholder={placeholder}
        value={display}
        isInvalid={isInvalid}
        onChange={(event) => {
          const raw = event.target.value;
          const caret = event.target.selectionStart ?? raw.length;
          digitsBeforeCaret.current = raw.slice(0, caret).replace(/\D/g, "").length;
          onValueChange(digitsOnly(raw));
        }}
      />
      {isInvalid && error && (
        <Form.Control.Feedback type="invalid">{error}</Form.Control.Feedback>
      )}
    </>
  );
};

const AgentSettingsModal = ({
  show,
  handleClose,
  selectedChatbot,
  onSettingsApplied,
  onSkillsChanged,
  title,
  isCurrentAgent = true,
}) => {
  const [activeTab, setActiveTab] = useState("info");
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const [settingsError, setSettingsError] = useState(null);

  const { config } = useConfig();
  const formatNumber = useNumberFormat();

  const [validProviders, setValidProviders] = useState([]);
  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: "",
    variant: "info",
    title: "Notification",
    duration: 5000,
  });

  const [showInfoBanner, setShowInfoBanner] = useState(true);
  const [chatbotInstructions, setChatbotInstructions] = useState("");
  const [aiSdkUserInstructions, setAiSdkUserInstructions] = useState("");

  const [aiSDKBaseLLM, setAISDKBaseLLM] = useState({
    provider: "",
    model: "",
    temperature: "",
    max_tokens: "",
    omitTemperature: false,
  });
  const [aiSDKThinkingLLM, setAISDKThinkingLLM] = useState({
    provider: "",
    model: "",
    temperature: "",
    max_tokens: "",
    omitTemperature: false,
  });
  const [useBaseLLMForExecution, setUseBaseLLMForExecution] = useState(false);
  const [checkAmbiguity, setCheckAmbiguity] = useState(true);
  const [autoFixing, setAutoFixing] = useState(true);
  const [autoFixingAttempts, setAutoFixingAttempts] = useState(2);
  const [sdkDefaults, setSdkDefaults] = useState({ base: {}, thinking: {} });
  const [sdkDeepQueryEnabled, setSdkDeepQueryEnabled] = useState(false);

  const [chatbotLLM, setChatbotLLM] = useState({
    provider: "",
    model: "",
    temperature: "",
    max_tokens: "",
    context_window: "",
    omitTemperature: false,
  });
  const [chatbotDefaults, setChatbotDefaults] = useState({});
  const [chatbotDeepQueryEnabled, setChatbotDeepQueryEnabled] = useState(false);
  const [defaultCustomInstructions, setDefaultCustomInstructions] = useState({
    chatbot: "",
    ai_sdk: "",
  });

  // Skills, memory, and knowledge toggles (per user, per agent). These act
  // immediately (no Save needed) and work for any agent, not just the
  // currently selected one.
  const [agentSkills, setAgentSkills] = useState([]);
  const [agentKBs, setAgentKBs] = useState([]);
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [memorySaving, setMemorySaving] = useState(false);
  const [togglesLoading, setTogglesLoading] = useState(false);
  const [togglesError, setTogglesError] = useState(null);

  const isGlobalChat = !selectedChatbot || selectedChatbot.isGlobal === true;
  const agentKey = isGlobalChat ? "global" : selectedChatbot.id || "global";

  // Permissions evaluated for the agent being configured (fetched with its
  // settings); fall back to the current agent's config until loaded.
  const [agentPerms, setAgentPerms] = useState(null);
  const canEditLLM = agentPerms ? agentPerms.user_edit_llm : config?.user_edit_llm;
  const canEditInstructions = agentPerms ? agentPerms.can_edit_instructions : config?.can_edit_instructions;

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
    setSettingsError(null);
  };

  // The modal instance is shared across agents: reset to the first tab every
  // time it opens.
  useEffect(() => {
    if (show) {
      setActiveTab("info");
      setSubmitAttempted(false);
    }
  }, [show, isCurrentAgent]);

  const loadToggles = async () => {
    setTogglesLoading(true);
    setTogglesError(null);
    const [skillsRes, kbRes, memoryRes] = await Promise.allSettled([
      api.get("skills/list", { params: { agent_id: agentKey } }),
      api.get("csv/list", { params: { agent_id: agentKey } }),
      api.get("memories/activation", { params: { agent_id: agentKey } }),
    ]);
    const failed = [];
    if (skillsRes.status === "fulfilled" && skillsRes.value.data.success) {
      setAgentSkills(skillsRes.value.data.skills || []);
    } else {
      failed.push("skills");
    }
    if (memoryRes.status === "fulfilled" && memoryRes.value.data.success) {
      setMemoryEnabled(!!memoryRes.value.data.active);
    } else {
      failed.push("memory");
    }
    if (kbRes.status === "fulfilled" && kbRes.value.data.success) {
      // Show agent-declared, public, and the user's own private
      // collections; other users' private collections (admin-visible in
      // the KB Manager) are not listed here.
      setAgentKBs((kbRes.value.data.sources || []).filter((s) => s.agent_managed || !s.private || s.is_owner));
    } else if (kbRes.status === "rejected" && kbRes.reason?.response?.status === 403) {
      setAgentKBs([]);
    } else {
      failed.push("knowledge bases");
    }
    if (failed.length) {
      const joined = failed.length === 1
        ? failed[0]
        : `${failed.slice(0, -1).join(", ")} and ${failed[failed.length - 1]}`;
      setTogglesError(`Failed to load ${joined} for this agent.`);
      console.error("Error fetching agent toggles:", { skillsRes, kbRes, memoryRes });
    }
    setTogglesLoading(false);
  };

  useEffect(() => {
    if (!show) return;
    loadToggles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [show, agentKey]);

  const handleToggleSkill = async (skillName, currentActive) => {
    try {
      const response = await api.post("skills/activate", {
        skill_name: skillName,
        active: !currentActive,
        agent_id: agentKey,
      });
      if (response.data.success) {
        setAgentSkills((prev) => prev.map((s) =>
          s.skill_name === skillName ? { ...s, active: !currentActive } : s
        ));
        if (isCurrentAgent && onSkillsChanged) onSkillsChanged();
      }
    } catch (err) {
      setTogglesError(`Failed to toggle skill: ${err.response?.data?.error || err.message}`);
    }
  };

  const handleToggleMemory = async () => {
    const next = !memoryEnabled;
    setMemorySaving(true);
    setTogglesError(null);
    try {
      const response = await api.post("memories/activation", {
        active: next,
        agent_id: agentKey,
      });
      if (response.data.success) setMemoryEnabled(!!response.data.active);
    } catch (err) {
      setTogglesError(`Failed to update memory: ${err.response?.data?.error || err.message}`);
    } finally {
      setMemorySaving(false);
    }
  };

  const handleToggleKB = async (sourceName, currentActive) => {
    try {
      const response = await api.post("csv/activate", {
        source_name: sourceName,
        active: !currentActive,
        agent_id: agentKey,
      });
      if (response.data.success) {
        setAgentKBs((prev) => prev.map((s) =>
          s.source_name === sourceName ? { ...s, active: !currentActive } : s
        ));
      }
    } catch (err) {
      setTogglesError(`Failed to toggle knowledge base: ${err.response?.data?.error || err.message}`);
    }
  };

  const handleResetResources = async () => {
    setTogglesError(null);
    setTogglesLoading(true);
    try {
      await api.post("reset_agent_resources", { agent_id: agentKey });
    } catch (err) {
      setTogglesError(err.response?.data?.error || "Failed to reset skills and knowledge bases.");
      setTogglesLoading(false);
      return;
    }
    await loadToggles();
    if (isCurrentAgent && onSkillsChanged) onSkillsChanged();
    showToast(
      "Toggleable skills are on, and toggleable knowledge bases are off. Items managed by the agent were left as configured.",
      "info",
      "Defaults restored",
    );
  };

  useEffect(() => {
    if (!show) return;

    const fetchSettings = async () => {
      setIsFetching(true);
      setSettingsError(null);
      try {
        const response = await api.get("llm_settings", { params: { agent_id: agentKey } });
        const data = response.data;
        setAgentPerms({
          user_edit_llm: data.user_edit_llm ?? config?.user_edit_llm,
          can_edit_instructions: data.user_edit_instructions ?? config?.can_edit_instructions,
        });

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
        const effectiveBaseSettings = toFormLLM({
          provider: effectiveBaseProvider,
          model: basePrefs.model || baseDefaults.model || "",
          temperature: basePrefs.temperature ?? baseDefaults.temperature ?? "",
          max_tokens: basePrefs.max_tokens || baseDefaults.max_tokens || "",
        });

        const effectiveThinkingProvider = canonicalProviderForSelect(
          thinkingPrefs.provider || thinkingDefaults.provider || "",
          providers,
        );
        const effectiveThinkingSettings = toFormLLM({
          provider: effectiveThinkingProvider,
          model: thinkingPrefs.model || thinkingDefaults.model || "",
          temperature: thinkingPrefs.temperature ?? thinkingDefaults.temperature ?? "",
          max_tokens: thinkingPrefs.max_tokens || thinkingDefaults.max_tokens || "",
        });

        const checkAmbVal = data.check_ambiguity ?? sdkInfo.check_ambiguity ?? true;
        const autoFixingVal = data.auto_fixing ?? sdkInfo.auto_fixing ?? true;
        const autoFixingAttemptsVal = data.auto_fixing_attempts ?? sdkInfo.auto_fixing_attempts ?? 2;

        const execModelFromData = data.use_base_llm_for_execution;
        const useBaseExecVal =
          execModelFromData !== null && execModelFromData !== undefined
            ? execModelFromData
            : sdkInfo.deepquery_execution_model === "base";

        const effectiveChatbotProvider = canonicalProviderForSelect(
          chatbotPrefs.provider || chatbotServerDefaults.provider || "",
          providers,
        );
        const effectiveChatbotSettings = toFormLLM({
          provider: effectiveChatbotProvider,
          model: chatbotPrefs.model || chatbotServerDefaults.model || "",
          temperature: chatbotPrefs.temperature ?? chatbotServerDefaults.temperature ?? "",
          max_tokens: chatbotPrefs.max_tokens || chatbotServerDefaults.max_tokens || "",
          context_window: chatbotPrefs.context_window || chatbotServerDefaults.context_window || 128000,
        });

        const defs = data.default_custom_instructions || {};
        setDefaultCustomInstructions({
          chatbot: defs.chatbot || "",
          ai_sdk: defs.ai_sdk || "",
        });
        const entry = readInstructionEntry(data.custom_instructions);
        if (!entry) {
          setChatbotInstructions(defs.chatbot || "");
          setAiSdkUserInstructions(defs.ai_sdk || "");
        } else {
          setChatbotInstructions(entry.chatbot);
          setAiSdkUserInstructions(entry.ai_sdk);
        }

        setAISDKBaseLLM(effectiveBaseSettings);
        setAISDKThinkingLLM(effectiveThinkingSettings);
        setChatbotLLM(effectiveChatbotSettings);
        setCheckAmbiguity(checkAmbVal);
        setAutoFixing(autoFixingVal);
        setAutoFixingAttempts(autoFixingAttemptsVal);
        setUseBaseLLMForExecution(useBaseExecVal);

      } catch (error) {
        console.error("Error fetching settings:", error);
        setSettingsError(error.response?.data?.error || "Settings could not be loaded.");
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

  const validateContextWindow = (tokens) => {
    const tokensInt = parseInt(tokens, 10);
    return !isNaN(tokensInt) && tokensInt >= 16000 && tokensInt <= 10000000;
  };

  const deepQueryActive = sdkDeepQueryEnabled && chatbotDeepQueryEnabled;

  // Validation errors are shown inline under the offending field (see
  // renderLLMSection); on failure we switch to the tab that contains it.
  const validateForm = () => {
    if (!canEditLLM) return true;

    if (
      (!chatbotLLM.omitTemperature && !validateTemperature(chatbotLLM.temperature)) ||
      !validateMaxTokens(chatbotLLM.max_tokens) ||
      !validateContextWindow(chatbotLLM.context_window)
    ) {
      setActiveTab("info");
      return false;
    }
    const maxTokensInt = parseInt(chatbotLLM.max_tokens, 10);
    const contextWindowInt = parseInt(chatbotLLM.context_window, 10);
    if (!isNaN(maxTokensInt) && !isNaN(contextWindowInt) && maxTokensInt >= contextWindowInt) {
      setActiveTab("info");
      return false;
    }
    if (
      (!aiSDKBaseLLM.omitTemperature && !validateTemperature(aiSDKBaseLLM.temperature)) ||
      !validateMaxTokens(aiSDKBaseLLM.max_tokens)
    ) {
      setActiveTab("ai_sdk");
      return false;
    }
    const attemptsInt = parseInt(autoFixingAttempts, 10);
    if (isNaN(attemptsInt) || attemptsInt < 1 || attemptsInt > 5) {
      setActiveTab("ai_sdk");
      return false;
    }
    if (deepQueryActive) {
      if (
        (!aiSDKThinkingLLM.omitTemperature && !validateTemperature(aiSDKThinkingLLM.temperature)) ||
        !validateMaxTokens(aiSDKThinkingLLM.max_tokens)
      ) {
        setActiveTab("ai_sdk");
        return false;
      }
    }
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (settingsError) return;
    setSubmitAttempted(true);
    if (!validateForm()) return;

    setIsLoading(true);
    try {
      if (canEditInstructions) {
        await api.post("update_custom_instructions", {
          agent_id: agentKey,
          custom_instructions: {
            ai_sdk: aiSdkUserInstructions,
            chatbot: chatbotInstructions,
          },
        });
      }

      if (canEditLLM) {
        await api.post("update_llm_settings", {
          agent_id: agentKey,
          ai_sdk_base_llm: toPayloadLLM(aiSDKBaseLLM),
          check_ambiguity: checkAmbiguity,
          auto_fixing: autoFixing,
          auto_fixing_attempts: Number(autoFixingAttempts),
          // Hidden Deep Query fields are cleared so a previous choice does not
          // stay in effect after those controls are no longer on the form.
          ...(deepQueryActive
            ? {
                ai_sdk_thinking_llm: toPayloadLLM(aiSDKThinkingLLM),
                use_base_llm_for_execution: useBaseLLMForExecution,
              }
            : {
                ai_sdk_thinking_llm: null,
                use_base_llm_for_execution: null,
              }),
          chatbot_llm: toPayloadLLM(chatbotLLM),
        });
      }

      if (onSettingsApplied && selectedChatbot && isCurrentAgent) {
        await onSettingsApplied(selectedChatbot);
      }

      showToast(
        isCurrentAgent
          ? "Settings updated successfully."
          : "Settings saved. They will apply the next time you use this agent.",
        "success",
        "Settings Updated",
      );
      handleClose();
    } catch (error) {
      console.error("Error updating settings:", error);
      showToast(
        error.response?.data?.error || "An error occurred while updating settings.",
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
      const response = await api.get("llm_settings", { params: { agent_id: agentKey } });
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

      if (activeTab === "info") {
        if (canEditInstructions) {
          const defs = data.default_custom_instructions || {};
          const chatbotDef = defs.chatbot !== undefined ? defs.chatbot : defaultCustomInstructions.chatbot;
          setDefaultCustomInstructions((prev) => ({ ...prev, chatbot: chatbotDef || "" }));
          setChatbotInstructions(chatbotDef || "");
        }
        if (canEditLLM) {
          const p = canonicalProviderForSelect(chatbotServerDefaults.provider || "", validProviders);
          setChatbotLLM(
            toFormLLM({
              provider: p,
              model: chatbotServerDefaults.model || "",
              temperature: chatbotServerDefaults.temperature ?? "",
              max_tokens: chatbotServerDefaults.max_tokens || "",
              context_window: chatbotServerDefaults.context_window || 128000,
            }),
          );
        }
      } else if (activeTab === "ai_sdk") {
        const baseP = canonicalProviderForSelect(baseDefaults.provider || "", validProviders);
        setAISDKBaseLLM(
          toFormLLM({
            provider: baseP,
            model: baseDefaults.model || "",
            temperature: baseDefaults.temperature ?? "",
            max_tokens: baseDefaults.max_tokens || "",
          }),
        );

        const hasThinkingModel =
          sdkInfo.thinking_llm != null ||
          Object.keys(data.ai_sdk_thinking_llm_defaults || {}).length > 0;
        const deepQ = hasThinkingModel && (data.chatbot_deepquery ?? false);

        if (deepQ) {
          const thP = canonicalProviderForSelect(thinkingDefaults.provider || "", validProviders);
          setAISDKThinkingLLM(
            toFormLLM({
              provider: thP,
              model: thinkingDefaults.model || "",
              temperature: thinkingDefaults.temperature ?? "",
              max_tokens: thinkingDefaults.max_tokens || "",
            }),
          );
          
          const defExec = data.use_base_llm_for_execution_default;
          setUseBaseLLMForExecution(
            defExec !== null && defExec !== undefined
              ? defExec
              : sdkInfo.deepquery_execution_model === "base",
          );
        }

        const defAmb = data.check_ambiguity_default;
        setCheckAmbiguity(defAmb !== null && defAmb !== undefined ? defAmb : true);
        const defAutoFixing = data.auto_fixing_default;
        setAutoFixing(defAutoFixing !== null && defAutoFixing !== undefined ? defAutoFixing : true);
        const defAttempts = data.auto_fixing_attempts_default;
        setAutoFixingAttempts(defAttempts !== null && defAttempts !== undefined ? defAttempts : 2);

        const defs = data.default_custom_instructions || {};
        const aiSdkDef = defs.ai_sdk !== undefined ? defs.ai_sdk : defaultCustomInstructions.ai_sdk;
        setDefaultCustomInstructions((prev) => ({ ...prev, ai_sdk: aiSdkDef || "" }));
        setAiSdkUserInstructions(aiSdkDef || "");
      }

      showToast(
        activeTab === "ai_sdk"
          ? "AI SDK options, and related settings restored to server defaults. Save to apply."
          : "General settings restored to server defaults. Save to apply.",
        "info",
        "Defaults restored",
      );
    } catch (error) {
      console.error("Error loading defaults:", error);
      showToast(
        error.response?.data?.error || "Could not load default settings to restore the form.",
        "danger",
        "Reset Error",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetGeneralDefaults = () => {
    if (canEditLLM) {
      handleResetToDefaults();
      return;
    }
    setChatbotInstructions(defaultCustomInstructions.chatbot);
    showToast(
      "General (agent) instructions reset to server defaults. Save to apply.",
      "info",
      "Defaults restored",
    );
  };

  const tooltipAiSdkInstructionsContent =
    "Only the data query path (e.g. data_search tool) uses this text as request custom_instructions. The AI SDK server appends it after CUSTOM_INSTRUCTIONS from sdk_config.env. The metadata search path does not use an LLM the same way.";

  const resetOnLeft =
    (activeTab === "info" && (canEditInstructions || canEditLLM)) ||
    (activeTab === "ai_sdk" && canEditLLM) ||
    activeTab === "skills_kb";

  const footer = (
    <>
      {activeTab === "info" && (canEditInstructions || canEditLLM) && (
        <button
          type="button"
          className="rcc-light-btn me-auto"
          onClick={handleResetGeneralDefaults}
          disabled={isLoading || isFetching || !!settingsError}
          title="Reset General settings to server defaults."
        >
          Reset General defaults
        </button>
      )}
      {activeTab === "ai_sdk" && canEditLLM && (
        <button
          type="button"
          className="rcc-light-btn me-auto"
          onClick={handleResetToDefaults}
          disabled={isLoading || isFetching || !!settingsError}
          title="Reset AI SDK settings to server defaults"
        >
          Reset AI SDK defaults
        </button>
      )}
      {activeTab === "skills_kb" && (
        <button
          type="button"
          className="rcc-light-btn me-auto"
          onClick={handleResetResources}
          disabled={isLoading || isFetching || togglesLoading}
          title="Turn user-toggleable skills on and turn off user-toggleable knowledge bases. Agent-managed items stay as configured."
        >
          Reset to defaults
        </button>
      )}
      {!resetOnLeft && <div className="me-auto" />}

      <button type="button" className="rcc-ghost-btn" onClick={handleClose} disabled={isLoading}>
        Cancel
      </button>
      <button
        type="submit"
        className="rcc-primary-btn"
        form="combined-settings-form"
        disabled={isLoading || isFetching || !!settingsError}
      >
        {isLoading ? (
          <>
            <Spinner as="span" animation="border" size="sm" role="status" aria-hidden="true" />
            <span className="ms-2">Saving...</span>
          </>
        ) : (
          "Save"
        )}
      </button>
    </>
  );

  const renderInfoBanner = () =>
    showInfoBanner ? (
      <div className="settings-banner settings-banner-info">
        <i className="bi bi-info-circle-fill" />
        <div>
          <strong>Note:</strong> Fields are pre-filled with the current
          configurations for this agent. Changing the LLM settings mid-conversation 
          is supported, but starting a new chat is recommended for best results.
        </div>
        <button
          type="button"
          className="settings-banner-close"
          onClick={() => setShowInfoBanner(false)}
          aria-label="Dismiss note"
        >
          <i className="bi bi-x" />
        </button>
      </div>
    ) : null;

  return (
    <>
      <BaseModal
        show={show}
        onHide={handleClose}
        onExited={handleOnExited}
        title={title}
        size="lg"
        fixedHeight
        backdrop="static"
        className="settings-modal"
        footer={footer}
      >
            {isFetching ? (
              <div className="modal-scroll-container text-center py-5">
                <Spinner animation="border" variant="secondary" />
                <div className="mt-2 text-muted small">Loading current settings...</div>
              </div>
            ) : settingsError ? (
              <div className="modal-scroll-container py-5 px-4">
                <Alert variant="danger" className="mb-0">
                  {settingsError}
                </Alert>
              </div>
            ) : (
              <Form id="combined-settings-form" onSubmit={handleSubmit} className="settings-form">
                <Tabs activeKey={activeTab} onSelect={(k) => setActiveTab(k)}>
                  <Tab eventKey="info" title="General">
                    {renderInfoBanner()}
                    <div className="mt-2">
                      <div className="d-flex align-items-center p-3 mb-4 rounded border" style={{ backgroundColor: "#f8fafc", borderColor: "#eef1f4" }}>
                        <div
                          className="me-3 rounded-circle d-flex justify-content-center align-items-center bg-white border"
                          style={{ width: "56px", height: "56px", flexShrink: 0 }}
                        >
                          {isGlobalChat ? (
                            <img
                              src={`${assetBaseUrl}denodo_chat_transparent.png`}
                              alt="General Chat"
                              style={{ height: "32px", width: "32px", objectFit: "contain" }}
                              onError={(e) => {
                                e.target.style.display = "none";
                                e.target.nextSibling.style.display = "inline-block";
                              }}
                            />
                          ) : selectedChatbot?.icon ? (
                            <img
                              src={selectedChatbot.icon}
                              alt={selectedChatbot.name}
                              style={{ height: "32px", width: "32px", objectFit: "contain" }}
                              onError={(e) => {
                                e.target.style.display = "none";
                                e.target.nextSibling.style.display = "inline-block";
                              }}
                            />
                          ) : null}
                          <i
                            className={isGlobalChat ? "bi bi-chat-left-text" : "bi bi-robot"}
                            style={{
                              fontSize: "1.35rem",
                              color: "#475569",
                              display: isGlobalChat || selectedChatbot?.icon ? "none" : "inline-block",
                            }}
                          ></i>
                        </div>
                        <div>
                          <h6 className="mb-1 fw-bold text-dark">{selectedChatbot?.name || "General Chat"}</h6>
                          <div className="text-secondary small">
                            {selectedChatbot?.description || "No description provided for this agent."}
                          </div>
                        </div>
                      </div>

                      {canEditInstructions && (
                        <Form.Group controlId="formChatbotInstructions" className="mb-4">
                          <Form.Label className="small fw-semibold mb-1">How should the agent behave?</Form.Label>
                          <Form.Control
                            as="textarea"
                            rows={6}
                            placeholder="For example: always answer in Spanish, or always reference a specific view when answering."
                            value={chatbotInstructions}
                            onChange={(e) => setChatbotInstructions(e.target.value)}
                            style={{ resize: "none" }}
                          />
                        </Form.Group>
                      )}

                      {canEditLLM && (
                        <AgentSettingsLLMSection
                          sectionTitle="LLM"
                          llmState={chatbotLLM}
                          setLLMState={setChatbotLLM}
                          validProviders={validProviders}
                          validateTemperature={validateTemperature}
                          validateMaxTokens={validateMaxTokens}
                          validateContextWindow={validateContextWindow}
                          submitAttempted={submitAttempted}
                          formatNumber={formatNumber}
                          FormattedTokenInput={FormattedTokenInput}
                          options={{ showContextWindow: true }}
                        />
                      )}
                    </div>
                  </Tab>

                  <Tab eventKey="skills_kb" title="Skills, Memory & Knowledge">
                    {renderInfoBanner()}
                    <div className="mt-2">
                      {togglesError && (
                        <Alert variant="danger" onClose={() => setTogglesError(null)} dismissible className="py-2">
                          <small>{togglesError}</small>
                        </Alert>
                      )}
                      {togglesLoading ? (
                        <div className="text-center py-4">
                          <Spinner animation="border" size="sm" />
                          <span className="ms-2">Loading skills, memory, and knowledge...</span>
                        </div>
                      ) : (
                        <>
                          <div className="mb-4">
                            <h6 className="rcc-modal-subtitle mb-2">Skills</h6>
                            {agentSkills.length === 0 ? (
                              <p className="text-muted"><small>No skills available for this agent.</small></p>
                            ) : (
                              <div className="border rounded bg-white px-3 py-1">
                                {["system", "personal"].map((scope) => {
                                  const skills = agentSkills
                                    .filter((s) => s.scope === scope)
                                    .sort((a, b) => (a.valid === false ? 1 : 0) - (b.valid === false ? 1 : 0));
                                  if (skills.length === 0) return null;
                                  return (
                                    <div key={scope} className="mb-2">
                                      <div className="text-uppercase text-secondary mb-1 mt-2" style={{ fontSize: "0.7rem", fontWeight: "600" }}>
                                        {scope === "system" ? "System" : "Personal"}
                                      </div>
                                      {skills.map((skill) => (
                                        <div key={skill.skill_name} className="settings-list-item">
                                          <Form.Check
                                            type="switch"
                                            id={`settings-skill-${agentKey}-${skill.skill_name}`}
                                            checked={skill.valid === false ? false : skill.active}
                                            disabled={skill.agent_managed || skill.valid === false}
                                            onChange={() => handleToggleSkill(skill.skill_name, skill.active)}
                                            className="m-0"
                                          />
                                          <code className="ms-2 skm-code-badge settings-item-name">{skill.skill_name}</code>
                                          {skill.valid === false && (
                                            <span className="text-danger ms-2 small" title={skill.error || "Invalid skill"}>(Error)</span>
                                          )}
                                          {skill.agent_managed && skill.valid !== false && (
                                            <span className="text-muted ms-2 small">
                                              {skill.active ? "(managed by agent — always active)" : "(managed by agent)"}
                                            </span>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                            <p className="text-muted mt-2 mb-0 small">
                              To manage skills, use <strong>Tools &gt; Skills Manager</strong>.
                            </p>
                          </div>

                          <div className="mb-4">
                            <h6 className="rcc-modal-subtitle mb-2">Memory</h6>
                            <div className="border rounded bg-white px-3 py-1">
                              <div className="settings-list-item">
                                <Form.Check
                                  type="switch"
                                  id={`settings-memory-${agentKey}`}
                                  checked={memoryEnabled}
                                  disabled={memorySaving}
                                  onChange={handleToggleMemory}
                                  className="m-0"
                                />
                                <span className="ms-2 small">Memory formation</span>
                              </div>
                            </div>
                            <p className="text-muted mt-2 mb-0 small">
                              When this is on, this agent can save facts and use them on later questions.
                              When it is off, the memory tools and memory instructions are left out of this agent.
                              Review the memories stored for you from the user menu, under Memories.
                            </p>
                          </div>

                          <div>
                            <h6 className="rcc-modal-subtitle mb-2">Knowledge Bases</h6>
                            {agentKBs.length === 0 ? (
                              <p className="text-muted"><small>No knowledge base collections available.</small></p>
                            ) : (
                              <div className="border rounded bg-white px-3 py-1">
                                {[
                                  { key: "agent", label: "Agent", match: (kb) => kb.agent_managed },
                                  { key: "public", label: "Public", match: (kb) => !kb.agent_managed && !kb.private },
                                  { key: "personal", label: "Personal", match: (kb) => !kb.agent_managed && kb.private },
                                ].map(({ key, label, match }) => {
                                  const kbs = agentKBs.filter(match);
                                  if (kbs.length === 0) return null;
                                  return (
                                    <div key={key} className="mb-2">
                                      <div className="text-uppercase text-secondary mb-1 mt-2" style={{ fontSize: "0.7rem", fontWeight: "600" }}>
                                        {label}
                                      </div>
                                      {kbs.map((kb) => (
                                        <div key={kb.source_name} className="settings-list-item">
                                          <Form.Check
                                            type="switch"
                                            id={`settings-kb-${agentKey}-${kb.source_name}`}
                                            checked={kb.active}
                                            disabled={kb.agent_managed || !kb.can_toggle}
                                            onChange={() => handleToggleKB(kb.source_name, kb.active)}
                                            className="m-0"
                                          />
                                          <code className="ms-2 skm-code-badge settings-item-name">{kb.source_name}</code>
                                          {kb.agent_managed && (
                                            <span className="text-muted ms-2 small">(managed by agent — always active)</span>
                                          )}
                                          {!kb.agent_managed && !kb.private && !kb.can_toggle && (
                                            <span className="text-muted ms-2 small">(active only when declared by agent)</span>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                            <p className="text-muted mt-2 mb-0 small">
                              To upload or manage collections, use <strong>Tools &gt; Knowledge Base Manager</strong>.
                            </p>
                          </div>
                        </>
                      )}
                    </div>
                  </Tab>

                  {canEditLLM && (
                    <Tab eventKey="ai_sdk" title="AI SDK">
                      {renderInfoBanner()}
                      <div className="mt-2">
                        <div className="settings-card-form p-3 border mb-4 rounded" style={{ background: "#f8fafc" }}>
                          <div className="text-uppercase text-secondary mb-2 small fw-semibold" style={{ fontSize: "0.75rem" }}>
                            Agent and AI SDK Collaboration
                          </div>
                          <p className="small text-secondary mb-2">
                            The agent collaborates with tools exposed in the AI SDK to satisfy queries.
                          </p>
                          <ul className="small text-secondary mb-0 ps-3">
                            <li className="mb-1">
                              <code>generate_vql</code> and <code>execute_vql</code>: Creates/executes queries on data models.
                            </li>
                            <li className="mb-1">
                              <code>metadata_search</code>: Explore categorized vector views.
                            </li>
                            <li className="mb-0">
                              <code>deep_query</code>: Subagent focused on complex, long-running workflows.
                            </li>
                          </ul>
                        </div>

                        {canEditInstructions && (
                          <Form.Group controlId="formAiSdkInstructions" className="mb-4">
                            <Form.Label className="small fw-semibold d-flex align-items-center">
                              How should the AI SDK behave?
                              <CustomTooltip id="tooltip-ai-sdk-instructions" content={tooltipAiSdkInstructionsContent}>
                                <i className="bi bi-info-circle info-icon ms-2"></i>
                              </CustomTooltip>
                            </Form.Label>
                            <Form.Control
                              as="textarea"
                              rows={4}
                              placeholder="For example: always use a descriptive alias for columns when generating VQL"
                              value={aiSdkUserInstructions}
                              onChange={(e) => setAiSdkUserInstructions(e.target.value)}
                              style={{ resize: "none" }}
                            />
                          </Form.Group>
                        )}

                        <div className="row g-3">
                          <div className={deepQueryActive ? "col-lg-6" : "col-12"}>
                            <AgentSettingsLLMSection
                              sectionTitle="Base LLM"
                              llmState={aiSDKBaseLLM}
                              setLLMState={setAISDKBaseLLM}
                              validProviders={validProviders}
                              validateTemperature={validateTemperature}
                              validateMaxTokens={validateMaxTokens}
                              validateContextWindow={validateContextWindow}
                              submitAttempted={submitAttempted}
                              formatNumber={formatNumber}
                              FormattedTokenInput={FormattedTokenInput}
                            />
                          </div>
                          {deepQueryActive && (
                            <div className="col-lg-6">
                              <AgentSettingsLLMSection
                                sectionTitle="Thinking LLM"
                                llmState={aiSDKThinkingLLM}
                                setLLMState={setAISDKThinkingLLM}
                                validProviders={validProviders}
                                validateTemperature={validateTemperature}
                                validateMaxTokens={validateMaxTokens}
                                validateContextWindow={validateContextWindow}
                                submitAttempted={submitAttempted}
                                formatNumber={formatNumber}
                                FormattedTokenInput={FormattedTokenInput}
                              />
                            </div>
                          )}
                        </div>

                        {!sdkDeepQueryEnabled ? (
                          <div className="settings-banner settings-banner-warning mt-2 small">
                            <i className="bi bi-exclamation-triangle-fill" />
                            <div>
                              <strong>DeepQuery disabled:</strong> No thinking model is configured in the AI SDK. 
                              Enable <code>THINKING_LLM_PROVIDER</code> in <code>sdk_config.env</code> to activate.
                            </div>
                          </div>
                        ) : !chatbotDeepQueryEnabled ? (
                          <div className="settings-banner settings-banner-info mt-2 small">
                            <i className="bi bi-info-circle-fill" />
                            <div>
                              <strong>DeepQuery disabled at chatbot level:</strong> Enable <code>CHATBOT_DEEPQUERY=1</code> to configure Thinking LLM properties.
                            </div>
                          </div>
                        ) : null}

                        <div className="mt-3 pt-3 border-top">
                          <h6 className="rcc-modal-subtitle mb-3">
                            Other AI SDK Options
                          </h6>
                          {deepQueryActive && (
                            <Form.Group className="mb-2">
                              <Form.Check
                                type="checkbox"
                                className="small"
                                id="use-base-llm-exec"
                                checked={useBaseLLMForExecution}
                                onChange={(e) => setUseBaseLLMForExecution(e.target.checked)}
                                label={
                                  <span className="d-inline-flex align-items-center">
                                    Use Base LLM for execution in DeepQuery
                                    <CustomTooltip id="tooltip-use-base-llm-exec" content="Thinking model will generate the plan and the base model will execute each step.">
                                      <i className="bi bi-info-circle info-icon ms-1"></i>
                                    </CustomTooltip>
                                  </span>
                                }
                              />
                            </Form.Group>
                          )}
                          <Form.Group className="mb-2">
                            <Form.Check
                              type="checkbox"
                              className="small"
                              label="Enable ambiguity detection (ask for clarification on vague queries)"
                              checked={checkAmbiguity}
                              onChange={(e) => setCheckAmbiguity(e.target.checked)}
                            />
                          </Form.Group>
                          <Form.Group className="mb-3">
                            <Form.Check
                              type="checkbox"
                              className="small"
                              label="Enable automatic VQL fixing when the first generated query fails"
                              checked={autoFixing}
                              onChange={(e) => setAutoFixing(e.target.checked)}
                            />
                          </Form.Group>
                          <Form.Group className="mb-1">
                            <Form.Label className="small fw-semibold mb-1">
                              Automatic VQL fixing attempts (1-5)
                            </Form.Label>
                            <Form.Control
                              type="number"
                              size="sm"
                              min={1}
                              max={5}
                              value={autoFixingAttempts}
                              disabled={!autoFixing}
                              isInvalid={
                                (isNaN(parseInt(autoFixingAttempts, 10)) ||
                                  parseInt(autoFixingAttempts, 10) < 1 ||
                                  parseInt(autoFixingAttempts, 10) > 5) &&
                                (autoFixingAttempts !== "" || submitAttempted)
                              }
                              onChange={(e) => setAutoFixingAttempts(e.target.value)}
                              style={{ maxWidth: "120px" }}
                            />
                            <Form.Control.Feedback type="invalid">
                              Automatic VQL fixing attempts must be between 1 and 5
                            </Form.Control.Feedback>
                          </Form.Group>
                        </div>
                      </div>
                    </Tab>
                  )}
                </Tabs>
              </Form>
            )}
      </BaseModal>

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

AgentSettingsModal.propTypes = {
  show: PropTypes.bool.isRequired,
  handleClose: PropTypes.func.isRequired,
  selectedChatbot: PropTypes.object,
  onSettingsApplied: PropTypes.func,
  onSkillsChanged: PropTypes.func,
  title: PropTypes.string,
  isCurrentAgent: PropTypes.bool,
};

export default AgentSettingsModal;
