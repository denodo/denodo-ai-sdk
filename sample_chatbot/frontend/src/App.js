import React, { useState, useReducer, useEffect } from "react";
import "./App.css";
import "./Modal.css";

import Header from "./components/Header/Header";
import Chat from "./components/Chat/Chat";
import QuestionForm from "./components/QuestionForm/QuestionForm";
import ReportManagementModal from "./components/Header/ReportManagementModal";
import Sidebar from "./components/Sidebar/Sidebar";
import LoginPage from "./components/LoginPage/LoginPage";
import { Spinner } from "react-bootstrap";
import NotificationToast from "./components/NotificationToast/NotificationToast";

import { chatReducer, actionTypes } from "./reducers/chatReducer";
import { useConfig, getSavedInputMethod } from "./contexts/ConfigContext";
import api from "./api/client";
import useSDK from "./hooks/useSDK";

// Abstracted Hooks & Feature-based Components
import { useAgentManager } from "./hooks/useAgentManager";
import { useChatHistory } from "./hooks/useChatHistory";
import { useChatLimits } from "./hooks/useChatLimits";
import DeleteChatModal from "./components/Sidebar/DeleteChatModal";
import RenameChatModal from "./components/Sidebar/RenameChatModal";
import LimitWarningModal from "./components/Chat/LimitWarningModal";
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

  const { updateConfig } = useConfig();

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
  );

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

        if (response.data.config) updateConfig(response.data.config);

        // Re-apply the input method saved by this user in the User Profile modal
        const savedInputMethod = getSavedInputMethod(userInformation.username);
        if (savedInputMethod) updateConfig({ input_method: savedInputMethod });

        const dictString = localStorage.getItem(
          `${userInformation.username}_custom_instructions_dict`,
        );
        if (dictString) {
          try {
            const dict = JSON.parse(dictString);
            const validKeys = response.data.agents
              ? response.data.agents.map((a) => a.id)
              : [];
            if (response.data.globalEnabled) validKeys.push("global");

            const cleanDict = {};
            for (const key of Object.keys(dict)) {
              if (validKeys.includes(key)) cleanDict[key] = dict[key];
            }
            localStorage.setItem(
              `${userInformation.username}_custom_instructions_dict`,
              JSON.stringify(cleanDict),
            );
          } catch (e) {}
        }
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
    limits.setLimitModal({
      show: false,
      type: null,
      pendingData: null,
      limit: 0,
      current: 0,
      targetsToDelete: [],
    });

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
          partialResources={agentManager.partialResources}
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
          globalEnabled={agentManager.globalEnabled}
          onSettingsApplied={handleSettingsApplied}
          isSwitchingAgent={agentManager.isSwitchingAgent}
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

      <ReportManagementModal />
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
      <LimitWarningModal
        modalState={limits.limitModal}
        onClose={limits.closeLimitModal}
        onAccept={handleAcceptLimit}
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
