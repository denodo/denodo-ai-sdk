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
    const payload = { id: bot.id };

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
