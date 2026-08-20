import { useState, useMemo } from "react";
import api from "../api/client";

export const useAgentManager = (updateConfig) => {
  const [chatbots, setChatbots] = useState([]);
  const [selectedChatbot, setSelectedChatbot] = useState(null);
  const [globalEnabled, setGlobalEnabled] = useState(false);
  const [isSwitchingAgent, setIsSwitchingAgent] = useState(false);
  const [syncedResources, setSyncedResources] = useState({});
  const [partialResources, setPartialResources] = useState({});
  const [userSyncPermissions, setUserSyncPermissions] = useState(true);

  const activeChatbot = useMemo(() => {
    if (selectedChatbot) return selectedChatbot;
    const globalBot = chatbots.find((bot) => bot.isGlobal);
    return globalBot || { id: "global", isGlobal: true, name: "General Chat" };
  }, [selectedChatbot, chatbots]);

  const switchAgentInBackend = async (bot) => {
    const currentUser = localStorage.getItem("current_user") || "";
    const savedUserDetails =
      localStorage.getItem(`${currentUser}_user_details`) || "";
    const agentKey = bot.isGlobal ? "global" : bot.id;

    let savedCustomInstructions = null;
    try {
      savedCustomInstructions = JSON.parse(
        localStorage.getItem(`${currentUser}_custom_instructions_dict`),
      )[agentKey];
    } catch (e) {}

    let chatbotLlmSettings = null;
    try {
      chatbotLlmSettings = JSON.parse(
        localStorage.getItem(`${currentUser}_chatbot_llm_settings_dict`),
      )[agentKey];
    } catch (e) {}

    let aiSdkSettings = null;
    try {
      aiSdkSettings = JSON.parse(
        localStorage.getItem(`${currentUser}_ai_sdk_llm_settings_dict`),
      )[agentKey];
    } catch (e) {}

    const payload = {
      id: bot.id,
      user_details: savedUserDetails,
      custom_instructions: savedCustomInstructions,
      llm_settings: {},
    };

    if (chatbotLlmSettings)
      payload.llm_settings.chatbot_llm = chatbotLlmSettings;
    if (aiSdkSettings) {
      payload.llm_settings.ai_sdk_base_llm = aiSdkSettings.ai_sdk_base_llm;
      payload.llm_settings.ai_sdk_thinking_llm =
        aiSdkSettings.ai_sdk_thinking_llm;
      payload.llm_settings.use_base_llm_for_execution =
        aiSdkSettings.use_base_llm_for_execution;
      payload.llm_settings.check_ambiguity = aiSdkSettings.check_ambiguity;
    }

    const response = await api.post("change_agent", payload);
    if (response.data.success) {
      if (response.data.syncedResources)
        setSyncedResources(response.data.syncedResources);
      if (response.data.partialResources)
        setPartialResources(response.data.partialResources);
      if (response.data.config) updateConfig(response.data.config);
    }
  };

  return {
    chatbots,
    setChatbots,
    selectedChatbot,
    setSelectedChatbot,
    globalEnabled,
    setGlobalEnabled,
    isSwitchingAgent,
    setIsSwitchingAgent,
    syncedResources,
    setSyncedResources,
    partialResources,
    setPartialResources,
    userSyncPermissions,
    setUserSyncPermissions,
    activeChatbot,
    switchAgentInBackend,
  };
};
