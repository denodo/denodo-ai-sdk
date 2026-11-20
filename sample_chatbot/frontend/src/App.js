import React, { useState, useReducer, useEffect, useRef, useCallback } from "react";
import "./App.css";
import "./components/Common/Modal/Modal.css";

import Header from "./components/Header/Header";
import Chat from "./components/Chat/Chat";
import QuestionForm from "./components/QuestionForm/QuestionForm";
import ReportsManagerModal from "./components/Reports/ReportsManagerModal";
import Sidebar from "./components/Sidebar/Sidebar";
import LoginPage from "./components/LoginPage/LoginPage";
import { Spinner } from "react-bootstrap";
import NotificationToast from "./components/NotificationToast/NotificationToast";
import AgentSettingsModal from "./components/Header/AgentSettingsModal/AgentSettingsModal";

import { chatReducer, actionTypes } from "./reducers/chatReducer";
import { useConfig } from "./contexts/ConfigContext";
import { useReport } from "./contexts/ReportContext";
import { getNumberFormat } from "./utils/numberFormat";
import api, { AUTH_EXPIRED_EVENT } from "./api/client";
import useSDK from "./hooks/useSDK";

// Abstracted Hooks & Feature-based Components
import { useAgentManager } from "./hooks/useAgentManager";
import { useChatHistory } from "./hooks/useChatHistory";
import { useChatLimits } from "./hooks/useChatLimits";
import DeleteChatModal from "./components/Sidebar/DeleteChatModal";
import RenameChatModal from "./components/Sidebar/RenameChatModal";
import LimitReachedModal from "./components/Chat/Modals/LimitReachedModal";
import WelcomeScreen from "./components/WelcomeScreen/WelcomeScreen";

const assetBaseUrl = import.meta.env.BASE_URL;

const App = () => {
  const [results, dispatch] = useReducer(chatReducer, []);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [showCSVManager, setShowCSVManager] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [questionType, setQuestionType] = useState("auto");
  const [completedRequestId, setCompletedRequestId] = useState(null);
  const [customLogoState, setCustomLogoState] = useState("checking");
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [username, setUsername] = useState("");
  const [settingsAgent, setSettingsAgent] = useState(null);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [contextUsage, setContextUsage] = useState(null);
  const contextUsageRequest = useRef(0);

  const handleContextUsage = (usage) => {
    if (!usage) return;
    contextUsageRequest.current += 1;
    setContextUsage(usage);
  };

  const { updateConfig, updateProfile, clearProfile } = useConfig();
  const { setPollingEnabled } = useReport();

  // Business logic Custom Hooks
  const agentManager = useAgentManager(updateConfig);
  const limits = useChatLimits(dispatch);
  const history = useChatHistory(
    dispatch,
    agentManager.chatbots,
    agentManager.switchAgentInBackend,
    agentManager.setSelectedChatbot,
    limits.setAutoOverwriteAccepted,
    limits.handleLimitReached 
  );

  // SDK Initialization
  const sdk = useSDK(
    dispatch,
    (id) => {
      setCompletedRequestId(id);
      history.handleRequestCompletion(id);
    },
    history.currentThreadId,
    history.setCurrentThreadId,
    limits.handleLimitReached,
    limits.autoOverwriteAccepted,
    handleContextUsage,
  );

  const contextAgentKey = agentManager.selectedChatbot
    ? agentManager.selectedChatbot.isGlobal
      ? "global"
      : agentManager.selectedChatbot.id
    : null;

  const refreshContextUsage = useCallback(() => {
    if (!isAuthenticated) {
      setContextUsage(null);
      return;
    }
    const requestId = ++contextUsageRequest.current;
    const params = history.currentThreadId ? { thread_id: history.currentThreadId } : {};
    api.get("context_usage", { params })
      .then((response) => {
        if (contextUsageRequest.current === requestId) {
          setContextUsage(response.data);
        }
      })
      .catch(() => {});
  }, [isAuthenticated, history.currentThreadId]);

  useEffect(() => {
    refreshContextUsage();
  }, [refreshContextUsage, contextAgentKey]);

  useEffect(() => {
    const img = new Image();
    img.onload = () => setCustomLogoState("present");
    img.onerror = () => setCustomLogoState("absent");
    img.src = `${assetBaseUrl}logo.png`;
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    const delayDebounceFn = setTimeout(() => {
      history.fetchChatHistoryList(false, history.searchQuery);
    }, 400);
    return () => clearTimeout(delayDebounceFn);
  }, [history.searchQuery, isAuthenticated]);

  useEffect(() => {
    if (!agentManager.selectedChatbot && results.length > 0) {
      agentManager.setSelectedChatbot(agentManager.activeChatbot);
    }
  }, [
    results.length,
    agentManager.selectedChatbot,
    agentManager.activeChatbot,
  ]);

  // Any 401 from the API means the session is gone: go back to the login screen
  useEffect(() => {
    const handleAuthExpired = () => {
      clearProfile();
      setIsAuthenticated(false);
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
  }, []);

  // DeepQuery reports are polled only while a user is logged in
  useEffect(() => {
    setPollingEnabled(isAuthenticated);
  }, [isAuthenticated, setPollingEnabled]);

  useEffect(() => {
    if (isAuthenticated) {
      const storedUser = localStorage.getItem("current_user");
      if (storedUser) setUsername(storedUser);
    }
  }, [isAuthenticated]);

  const renderLogo = () => {
    if (customLogoState === "present")
      return (
        <img
          alt="Company logo"
          src={`${assetBaseUrl}logo.png`}
          height="30"
          className="d-inline-block align-top"
        />
      );
    return (
      <img
        alt="Denodo company logo"
        src={`${assetBaseUrl}denodo_logo.png`}
        height="30"
        className="d-inline-block align-top"
      />
    );
  };

  const handleSignIn = async (userInformation) => {
    try {
      const response = await api.post("login", userInformation);
      if (response.data.success) {
        setIsAuthenticated(true);
        agentManager.setSyncedResources(response.data.syncedResources || {});
        agentManager.setPartialResources(response.data.partialResources || {});
        agentManager.setGlobalEnabled(response.data.globalEnabled || false);
        agentManager.setChatbots(response.data.agents || []);
        agentManager.setSelectedChatbot(null);
        agentManager.setUserSyncPermissions(
          response.data.userSyncPermissions !== false,
        );

        updateConfig(response.data.config || {});
        const savedProfile = response.data.profile || {};
        updateProfile({
          user_details: savedProfile.user_details || "",
          input_method: savedProfile.input_method || "enter",
          number_format: savedProfile.number_format || getNumberFormat(),
        });
      } else {
        alert(response.data.message || "Invalid credentials.");
      }
    } catch (error) {
      alert(
        error.response?.data?.message || "An error occurred during sign-in.",
      );
    }
  };

  const executeSwitchChatbot = async (bot) => {
    agentManager.setIsSwitchingAgent(true);
    try {
      limits.setAutoOverwriteAccepted(false);
      await agentManager.switchAgentInBackend(bot);
      agentManager.setSelectedChatbot(bot);
      history.setCurrentThreadId(null);
      dispatch({ type: actionTypes.CLEAR_CHAT });
      setQuestionType("auto");
    } catch (error) {
      alert(error.response?.data?.message || "Error connecting to the selected chatbot.");
    } finally {
      agentManager.setIsSwitchingAgent(false);
    }
  };

  const handleSettingsApplied = async (bot) => {
    try {
      await agentManager.switchAgentInBackend(bot);
    } catch (error) {
      console.error("Error applying new settings to backend:", error);
    }
    refreshContextUsage();
  };

  const handleNewChat = () => {
    limits.setAutoOverwriteAccepted(false);
    history.setCurrentThreadId(null);
    dispatch({ type: actionTypes.CLEAR_CHAT });
    setQuestionType("auto");
    const globalBot = agentManager.chatbots.find((bot) => bot.isGlobal);
    if (globalBot && agentManager.selectedChatbot?.id !== globalBot.id) {
      executeSwitchChatbot(globalBot);
    }
  };

  const handleResetWorkspace = () => {
    limits.setAutoOverwriteAccepted(false);
    history.setCurrentThreadId(null);
    dispatch({ type: actionTypes.CLEAR_CHAT });
    history.resetHistoryState();
    setQuestionType("auto");
  };

  const handleAcceptLimit = () => {
    const { pendingData, type } = limits.limitModal;
    limits.setLimitModal((prev) => ({
      ...prev,
      show: false,
      pendingData: null,
    }));

    if (pendingData) {
      if (pendingData.type === "import") {
        history.handleImportChat(pendingData.file, true);
      } else if (typeof sdk.processQuestion === "function") {
        let newResultIndex = pendingData.resultIndex;

        if (type === "messages") {
          limits.setAutoOverwriteAccepted(true);
        } else if (type === "chats") {
          history.fetchChatHistoryList(false);
        }

        sdk.processQuestion(
          pendingData.query,
          pendingData.toolName,
          newResultIndex,
          { ...pendingData.options, force_overwrite: true },
        );
      }
    }
  };

  const currentAgentKey = agentManager.selectedChatbot
    ? agentManager.selectedChatbot.isGlobal
      ? "global"
      : agentManager.selectedChatbot.id
    : "global";

  const agentKeyOf = (agent) => (agent?.isGlobal ? "global" : agent?.id);

  if (!isAuthenticated) {
    return (
      <LoginPage
        onSignIn={handleSignIn}
        renderLogo={renderLogo}
        showBrandAsk={customLogoState === "absent"}
        isCheckingLogo={customLogoState === "checking"} 
      />
    );
  }

  return (
    <div className="app-layout-container">
      <Sidebar
        isOpen={isSidebarOpen}
        toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        chatbots={agentManager.chatbots}
        selectedChatbot={agentManager.selectedChatbot}
        onSelectChatbot={(bot) => {
          if (agentManager.selectedChatbot?.id !== bot.id)
            executeSwitchChatbot(bot);
        }}
        showDenodoSidebarHeaderIcon={customLogoState === "absent"}
        onNewChat={handleNewChat}
        chatHistoryList={history.chatHistoryList}
        currentThreadId={history.currentThreadId}
        onLoadOldChat={history.handleLoadOldChat}
        onDeleteChat={(id) => history.setChatToDelete(id)}
        onRenameChat={(chat) => {
          history.setChatToRename(chat);
          history.setNewChatName(chat.title);
        }}
        onExportChat={history.handleExportChat}
        onImportChat={history.handleImportChat}
        onLoadMoreChats={() => history.fetchChatHistoryList(true)}
        hasMoreChats={history.hasMoreChats}
        isLoadingList={history.isLoadingList}
        isLoadingHistory={history.isLoadingHistory}
        onPinChat={history.handlePinChat}
        searchQuery={history.searchQuery}
        onSearchChange={history.setSearchQuery}
        onOpenSettings={(bot) => {
          setSettingsAgent(bot);
          setShowSettingsModal(true);
        }}
      />

      <div className="main-content-area">
        <Header
          isAuthenticated={isAuthenticated}
          setIsAuthenticated={setIsAuthenticated}
          handleClearResults={handleResetWorkspace}
          showClearButton={results.length > 0}
          onOpenCSVManager={() => setShowCSVManager(true)}
          showCSVManager={showCSVManager}
          setShowCSVManager={setShowCSVManager}
          renderLogo={renderLogo}
          showBrandAsk={customLogoState === "absent"}
          syncedResources={agentManager.syncedResources}
          userSyncPermissions={agentManager.userSyncPermissions}
          onResourcesUpdate={(data) => {
            if (data.syncedResources)
              agentManager.setSyncedResources(data.syncedResources);
            if (data.partialResources)
              agentManager.setPartialResources(data.partialResources);
          }}
          hasActiveConversation={results.length > 0}
          toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          isSidebarOpen={isSidebarOpen}
          selectedChatbot={agentManager.selectedChatbot}
          chatbots={agentManager.chatbots}
          isSwitchingAgent={agentManager.isSwitchingAgent}
          onOpenGeneralSettings={() => {
            const globalBot = agentManager.chatbots.find((bot) => bot.isGlobal || bot.id === "global");
            if (globalBot) {
              setSettingsAgent(globalBot);
              setShowSettingsModal(true);
            }
          }}
        />

        {agentManager.isSwitchingAgent || history.isLoadingHistory ? (
          <div className="dm-bg-container flex-grow-1 d-flex flex-column align-items-center justify-content-center">
            <Spinner
              animation="border"
              style={{
                color: "#143142",
                width: "3.5rem",
                height: "3.5rem",
                borderWidth: "0.25em",
              }}
            />
            <h5
              className="mt-4 text-secondary"
              style={{ fontWeight: 500, letterSpacing: "0.5px" }}
            >
              {history.isLoadingHistory
                ? "Loading conversation..."
                : "Setting up your chat..."}
            </h5>
          </div>
        ) : (
          <div className="dm-bg-container flex-grow-1">
            <div className="dm-content d-flex flex-column h-100">
              <div
                style={{
                  flexGrow: results.length === 0 ? 1 : 0,
                  transition: "flex-grow 0.6s cubic-bezier(0.25, 1, 0.5, 1)",
                  minHeight: 0,
                }}
              />

              <div
                className="chat-scroll-area d-flex flex-column"
                style={{
                  flexGrow: results.length > 0 ? 1 : 0,
                  overflowY: "auto",
                  flexShrink: 1,
                  minHeight: 0,
                }}
              >
                {results.length === 0 ? (
                  <div className="w-100 pb-2">
                    <WelcomeScreen
                      selectedChatbot={agentManager.selectedChatbot}
                      customLogoState={customLogoState}
                      username={username}
                      globalEnabled={agentManager.globalEnabled}
                    />
                  </div>
                ) : (
                  <Chat
                    results={results}
                    dispatch={dispatch}
                    setCurrentQuestion={setCurrentQuestion}
                    setQuestionType={setQuestionType}
                    contextUsage={contextUsage}
                  />
                )}
              </div>

              <div
                className={`pb-3 pt-2 position-relative ${!agentManager.selectedChatbot && results.length === 0 ? "animate-fade-in-up delay-4" : results.length === 0 ? "fade-in-smooth" : ""}`}
                style={{ zIndex: 10, flexShrink: 0 }}
              >
                <QuestionForm
                  results={results}
                  dispatch={dispatch}
                  isAuthenticated={isAuthenticated}
                  currentQuestion={currentQuestion}
                  setCurrentQuestion={setCurrentQuestion}
                  questionType={questionType}
                  setQuestionType={setQuestionType}
                  sdk={sdk}
                  completedRequestId={completedRequestId}
                  syncedResources={agentManager.syncedResources}
                  partialResources={agentManager.partialResources}
                  selectedChatbot={agentManager.activeChatbot}
                  contextUsage={contextUsage}
                  showContextUsage={Boolean(agentManager.selectedChatbot) || results.length > 0}
                />
              </div>
              <div
                style={{
                  flexGrow: results.length === 0 ? 1 : 0,
                  transition: "flex-grow 0.6s cubic-bezier(0.25, 1, 0.5, 1)",
                  minHeight: 0,
                }}
              />
            </div>
          </div>
        )}
      </div>

      <ReportsManagerModal />
      <DeleteChatModal
        show={!!history.chatToDelete}
        onHide={() => history.setChatToDelete(null)}
        onConfirm={() => history.confirmDeleteChat(handleNewChat)}
      />
      <RenameChatModal
        show={!!history.chatToRename}
        onHide={() => history.setChatToRename(null)}
        newChatName={history.newChatName}
        setNewChatName={history.setNewChatName}
        onConfirm={history.handleRenameSubmit}
      />
      <LimitReachedModal
        modalState={limits.limitModal}
        onClose={limits.closeLimitModal}
        onAccept={handleAcceptLimit}
      />
      <AgentSettingsModal
        show={showSettingsModal}
        handleClose={() => setShowSettingsModal(false)}
        selectedChatbot={settingsAgent}
        onSettingsApplied={handleSettingsApplied}
        onSkillsChanged={refreshContextUsage}
        title={
          settingsAgent
            ? (settingsAgent.isGlobal ? "General chat settings" : `${settingsAgent.name} settings`)
            : ""
        }
        isCurrentAgent={
          settingsAgent ? agentKeyOf(settingsAgent) === currentAgentKey : true
        }
      />
      <NotificationToast 
        show={history.toastConfig.show}
        message={history.toastConfig.message}
        variant={history.toastConfig.variant}
        title={history.toastConfig.title}
        onClose={history.closeToast}
      />
    </div>
  );
};

export default App;
