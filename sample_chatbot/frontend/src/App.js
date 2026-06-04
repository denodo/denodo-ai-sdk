import React, { useState, useReducer, useCallback, useEffect, useMemo } from "react";
import "./App.css"; 
import "./Modal.css";
import Header from "./components/Header/Header";
import Chat from "./components/Chat/Chat";
import QuestionForm from "./components/QuestionForm/QuestionForm";
import ReportManagementModal from "./components/Header/ReportManagementModal";
import Sidebar from "./components/Sidebar/Sidebar";
import useSDK from "./hooks/useSDK";
import LoginPage from "./components/LoginPage/LoginPage";
import { chatReducer, actionTypes } from "./reducers/chatReducer";
import { Modal, Button, Spinner } from "react-bootstrap";
import { useConfig } from "./contexts/ConfigContext";
import api from "./api/client";

const assetBaseUrl = import.meta.env.BASE_URL;

const App = () => {
  const [results, dispatch] = useReducer(chatReducer, []);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [showCSVManager, setShowCSVManager] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [completedRequestId, setCompletedRequestId] = useState(null);
  const [customLogoState, setCustomLogoState] = useState("checking");
  const [syncedResources, setSyncedResources] = useState({});
  const [partialResources, setPartialResources] = useState({});
  const [userSyncPermissions, setUserSyncPermissions] = useState(true);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [chatbots, setChatbots] = useState([]);
  const [globalEnabled, setGlobalEnabled] = useState(false);
  const [selectedChatbot, setSelectedChatbot] = useState(null);
  const [showSwitchModal, setShowSwitchModal] = useState(false);
  const [pendingChatbot, setPendingChatbot] = useState(null);
  const [isSwitchingAgent, setIsSwitchingAgent] = useState(false);
  const [username, setUsername] = useState("");

  const handleRequestCompletion = (requestId) => {
    setCompletedRequestId(requestId);
  };

  const sdk = useSDK(dispatch, handleRequestCompletion);
  const { updateConfig } = useConfig();

  const handleCustomLogoLoad = () => {
    setCustomLogoState("present");
  };

  const handleCustomLogoError = () => {
    setCustomLogoState("absent");
  };

  const handleResourcesUpdate = (data) => {
    if (data.syncedResources) {
      setSyncedResources(data.syncedResources);
    }
    if (data.partialResources) {
      setPartialResources(data.partialResources);
    }
  };

  const activeChatbot = useMemo(() => {
    if (selectedChatbot) return selectedChatbot;
    const globalBot = chatbots.find(bot => bot.isGlobal);
    return globalBot || { id: 'global', isGlobal: true, name: 'General Chat' };
  }, [selectedChatbot, chatbots]);

  useEffect(() => {
    if (!selectedChatbot && results.length > 0) {
      setSelectedChatbot(activeChatbot);
    }
  }, [results.length, selectedChatbot, activeChatbot]);

  useEffect(() => {
    if (isAuthenticated) {
      const storedUser = localStorage.getItem("current_user");
      if (storedUser) {
        setUsername(storedUser);
      }
    }
  }, [isAuthenticated]);

  const renderLogo = () => {
    const denodoLogo = (
      <img
        alt="Denodo company logo"
        src={`${assetBaseUrl}denodo_logo.png`}
        height="30"
        className="d-inline-block align-top"
      />
    );

    const customLogo = (
      <img
        alt="Company logo"
        src={`${assetBaseUrl}logo.png`}
        height="30"
        className="d-inline-block align-top"
        onLoad={handleCustomLogoLoad}
        onError={handleCustomLogoError}
      />
    );

    if (customLogoState === "present") {
      return (
        <img
          alt="Company logo"
          src={`${assetBaseUrl}logo.png`}
          height="30"
          className="d-inline-block align-top"
        />
      );
    }

    if (customLogoState === "absent") {
      return denodoLogo;
    }

    return customLogo;
  };

  const handleSignIn = async (userInformation) => {
    try {
      const response = await api.post("login", userInformation);
      if (response.data.success) {
        setIsAuthenticated(true);
        setSyncedResources(response.data.syncedResources || {});
        setPartialResources(response.data.partialResources || {});
        setGlobalEnabled(response.data.globalEnabled || false);
        setChatbots(response.data.agents || []);
        setSelectedChatbot(null);
        setUserSyncPermissions(response.data.userSyncPermissions !== false);

        if (response.data.config) {
          updateConfig(response.data.config);
        }

        const dictString = localStorage.getItem(`${userInformation.username}_custom_instructions_dict`);
        if (dictString) {
          try {
            const dict = JSON.parse(dictString);
            const validKeys = response.data.agents ? response.data.agents.map(agent => agent.id) : [];
            if (response.data.globalEnabled) validKeys.push('global');
            
            const cleanDict = {};
            for (const key of Object.keys(dict)) {
              if (validKeys.includes(key)) {
                cleanDict[key] = dict[key];
              }
            }
            localStorage.setItem(`${userInformation.username}_custom_instructions_dict`, JSON.stringify(cleanDict));
          } catch (e) {
            console.error("Error cleaning up custom instructions dictionary", e);
          }
        }

      } else {
        const errorMessage = response.data.message || 'Invalid credentials. Please try again.';
        alert(errorMessage);
      }
    } catch (error) {
      const errorMessage = error.response?.data?.message || 'An error occurred during sign-in. Please try again.';
      alert(errorMessage);
    }
  };

  const handleClearResults = async () => {
    try {
      dispatch({ type: actionTypes.CLEAR_CHAT });
      await api.post("clear_history");
    } catch (error) {
      console.error("There was an error clearing the memory!", error);
    }
  };

  const handleSelectChatbotClick = (bot) => {
    if (selectedChatbot?.id === bot.id) return;

    if (results.length > 0) {
      setPendingChatbot(bot);
      setShowSwitchModal(true);
    } else {
      executeSwitchChatbot(bot);
    }
  };

  const executeSwitchChatbot = async (bot) => {
    setIsSwitchingAgent(true);
    try {
      const currentUser = localStorage.getItem('current_user') || '';
      const savedUserDetails = localStorage.getItem(`${currentUser}_user_details`) || '';
      const agentKey = bot.isGlobal ? 'global' : bot.id;
      
      let savedCustomInstructions = null;
      const instDictString = localStorage.getItem(`${currentUser}_custom_instructions_dict`);
      if (instDictString) {
        try {
          const d = JSON.parse(instDictString);
          const raw = d[agentKey];
          if (typeof raw === 'string') {
            savedCustomInstructions = raw;
          } else if (raw && typeof raw === 'object') {
            savedCustomInstructions = raw;
          }
        } catch(e) {}
      }

      let chatbotLlmSettings = null;
      const cbDictString = localStorage.getItem(`${currentUser}_chatbot_llm_settings_dict`);
      if (cbDictString) {
        try { chatbotLlmSettings = JSON.parse(cbDictString)[agentKey] || null; } catch(e) {}
      }

      let aiSdkSettings = null;
      const sdkDictString = localStorage.getItem(`${currentUser}_ai_sdk_llm_settings_dict`);
      if (sdkDictString) {
        try { aiSdkSettings = JSON.parse(sdkDictString)[agentKey] || null; } catch(e) {}
      }

      const payload = {
        id: bot.id,
        user_details: savedUserDetails,
        custom_instructions: savedCustomInstructions,
        llm_settings: {}
      };

      if (chatbotLlmSettings) {
        payload.llm_settings.chatbot_llm = chatbotLlmSettings;
      }
      if (aiSdkSettings) {
        payload.llm_settings.ai_sdk_base_llm = aiSdkSettings.ai_sdk_base_llm;
        payload.llm_settings.ai_sdk_thinking_llm = aiSdkSettings.ai_sdk_thinking_llm;
        payload.llm_settings.use_base_llm_for_execution = aiSdkSettings.use_base_llm_for_execution;
        payload.llm_settings.check_ambiguity = aiSdkSettings.check_ambiguity;
      }

      const response = await api.post("change_agent", payload);
      
      if (response.data.success) {
        setSelectedChatbot(bot);
        dispatch({ type: actionTypes.CLEAR_CHAT });        
        if (response.data.syncedResources) {
          setSyncedResources(response.data.syncedResources);
        }
        if (response.data.partialResources) {
          setPartialResources(response.data.partialResources);
        }
        if (response.data.config) {
          updateConfig(response.data.config);
        }
      }
    } catch (error) {
      console.error('Error selecting chatbot', error);
      alert('Error connecting to the selected chatbot.');
    } finally {
      setIsSwitchingAgent(false);
    }
  };

  const confirmSwitch = () => {
    if (pendingChatbot) {
      executeSwitchChatbot(pendingChatbot);
    }
    setShowSwitchModal(false);
    setPendingChatbot(null);
  };

  const cancelSwitch = () => {
    setShowSwitchModal(false);
    setPendingChatbot(null);
  };

  if (!isAuthenticated) {
    return (
      <LoginPage
        onSignIn={handleSignIn}
        renderLogo={renderLogo}
        showBrandAsk={customLogoState === "absent"}
      />
    );
  }

  return (
    <div className="app-layout-container">
      <Sidebar 
        isOpen={isSidebarOpen} 
        toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        chatbots={chatbots}
        selectedChatbot={selectedChatbot}
        onSelectChatbot={handleSelectChatbotClick}
        showDenodoSidebarHeaderIcon={customLogoState === "absent"}
      />

      <div className="main-content-area">
        <Header
          isAuthenticated={isAuthenticated}
          setIsAuthenticated={setIsAuthenticated}
          handleClearResults={handleClearResults}
          showClearButton={results.length > 0}
          onOpenCSVManager={() => setShowCSVManager(true)}
          showCSVManager={showCSVManager}
          setShowCSVManager={setShowCSVManager}
          renderLogo={renderLogo}
          showBrandAsk={customLogoState === "absent"}
          syncedResources={syncedResources}
          partialResources={partialResources}
          userSyncPermissions={userSyncPermissions}
          onResourcesUpdate={handleResourcesUpdate}
          hasActiveConversation={results.length > 0}
          toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          isSidebarOpen={isSidebarOpen}
          selectedChatbot={selectedChatbot}
          globalEnabled={globalEnabled}
          onSettingsApplied={executeSwitchChatbot}
          isSwitchingAgent={isSwitchingAgent}
        />
        {isSwitchingAgent ? (
          <div className="dm-bg-container flex-grow-1 d-flex flex-column align-items-center justify-content-center">
            <Spinner animation="border" style={{ color: '#143142', width: '3.5rem', height: '3.5rem', borderWidth: '0.25em' }} />
            <h5 className="mt-4 text-secondary" style={{ fontWeight: 500, letterSpacing: '0.5px' }}>
              Setting up your chat...
            </h5>
          </div>
        ) : (
          <div className="dm-bg-container flex-grow-1">
            <div className="dm-content d-flex flex-column h-100">
              
              <div 
                style={{ 
                  flexGrow: results.length === 0 ? 1 : 0, 
                  transition: 'flex-grow 0.6s cubic-bezier(0.25, 1, 0.5, 1)',
                  minHeight: 0
                }} 
              />
              
              <div 
                className="chat-scroll-area d-flex flex-column" 
                style={{ 
                  flexGrow: results.length > 0 ? 1 : 0, 
                  overflowY: 'auto',
                  flexShrink: 1,
                  minHeight: 0
                }}
              >
                {results.length === 0 ? (
                  <div className="w-100 pb-2">
                    {!selectedChatbot ? (
                      <div className="d-flex flex-column align-items-center w-100">
                        {customLogoState === "absent" && (
                          <>
                            <h1 className="animate-fade-in-up delay-1 display-6 fw-normal text-dark mb-3 text-center">
                              Hi {username ? username : "user"}, welcome to
                            </h1>

                            <div className="animate-fade-in-up delay-2">
                              <h2
                                className="text-shine px-3 py-2 display-4 m-0 text-center"
                                style={{
                                  fontWeight: 600,
                                  letterSpacing: "-1.5px",
                                }}
                              >
                                Denodo Ask A Question
                              </h2>
                            </div>
                          </>
                        )}

                        {globalEnabled ? (
                          <p
                            className="animate-fade-in-up delay-3 lead text-muted mt-4 mb-3 mx-auto text-center"
                            style={{ maxWidth: "650px" }}
                          >
                            Select a specialized chatbot from the sidebar, or start typing below to use the general chat immediately.
                          </p>
                        ) : (
                          <p
                            className="animate-fade-in-up delay-3 lead text-muted mt-4 mb-3 mx-auto text-center"
                            style={{ maxWidth: "550px" }}
                          >
                            To get started, please select one of the available chatbots from the sidebar.
                          </p>
                        )}
                      </div>
                    ) : (
                      <div 
                        key={selectedChatbot.id} 
                        className="fade-in-smooth d-flex flex-column align-items-center text-center px-4" 
                      >
                        {selectedChatbot.isGlobal ? (
                          <img 
                            src={`${assetBaseUrl}denodo_chat_transparent.png`} 
                            alt="Chat"
                            style={{ width: '80px', height: '80px', objectFit: 'contain', marginBottom: '20px' }}
                            onError={(e) => {
                              e.target.style.display = 'none';
                              e.target.nextSibling.style.display = 'flex';
                            }}
                          />
                        ) : selectedChatbot.icon ? (
                          <img
                            src={selectedChatbot.icon}
                            alt={selectedChatbot.name}
                            style={{ width: '80px', height: '80px', objectFit: 'contain', marginBottom: '20px' }}
                            onError={(e) => {
                              e.target.style.display = 'none';
                              e.target.nextSibling.style.display = 'flex';
                            }}
                          />
                        ) : null}

                        <div 
                          className="align-items-center justify-content-center" 
                          style={{ 
                            display: (selectedChatbot.icon || selectedChatbot.isGlobal) ? 'none' : 'flex', 
                            width: '80px', height: '80px', backgroundColor: '#f1f3f5', borderRadius: '50%', marginBottom: '20px' 
                          }}
                        >
                          <i className={`bi ${selectedChatbot.isGlobal ? 'bi-chat-left-text' : 'bi-robot'}`} style={{ fontSize: '2.5rem', color: '#143142' }}></i>
                        </div>
                        
                        {!selectedChatbot.isGlobal && (
                          <h2 style={{ color: '#112533', fontWeight: 600, marginBottom: '15px' }}>
                            {selectedChatbot.name}
                          </h2>
                        )}
                        
                        <p style={{ 
                          color: '#6c757d', 
                          maxWidth: '600px', 
                          fontSize: '1.1rem', 
                          lineHeight: '1.6', 
                          marginTop: selectedChatbot.isGlobal ? '15px' : '0', 
                          marginBottom: 0,
                          maxHeight: '100px',
                          overflowY: 'auto',
                          paddingRight: '10px'
                        }}>
                          {selectedChatbot.description || "I'm ready to help you. Ask me anything!"}
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <Chat
                    results={results}
                    dispatch={dispatch}
                    setCurrentQuestion={setCurrentQuestion}
                  />
                )}
              </div>

              <div 
                className={`pb-3 pt-2 position-relative ${
                  !selectedChatbot && results.length === 0 
                    ? 'animate-fade-in-up delay-4' 
                    : (results.length === 0 ? 'fade-in-smooth' : '')
                }`}
                style={{ 
                  zIndex: 10, 
                  flexShrink: 0
                }}
              >
                <QuestionForm
                  results={results}
                  dispatch={dispatch}
                  isAuthenticated={isAuthenticated}
                  currentQuestion={currentQuestion}
                  setCurrentQuestion={setCurrentQuestion}
                  sdk={sdk}
                  completedRequestId={completedRequestId}
                  syncedResources={syncedResources}
                  partialResources={partialResources}
                  handleClearResults={handleClearResults}
                  selectedChatbot={activeChatbot}
                />
              </div>

              <div 
                style={{ 
                  flexGrow: results.length === 0 ? 1 : 0, 
                  transition: 'flex-grow 0.6s cubic-bezier(0.25, 1, 0.5, 1)',
                  minHeight: 0
                }} 
              />

            </div>
          </div>
        )}
      </div>

      <ReportManagementModal />

      <Modal 
        show={showSwitchModal} 
        onHide={cancelSwitch}
        centered
        backdrop="static"
      >
        <Modal.Header closeButton data-bs-theme="light">
          <Modal.Title>New chat selected</Modal.Title>
        </Modal.Header>
        <Modal.Body style={{ color: '#495057', fontSize: '1.05rem' }}>
          Are you sure you want to switch to <strong>{pendingChatbot?.name}</strong>? 
          <br/><br/>
          Your current conversation will be cleared and cannot be recovered.
        </Modal.Body>
        <Modal.Footer className="border-0 pt-0">
          <Button 
            variant="light" 
            onClick={cancelSwitch}
            style={{ fontWeight: 500 }}
          >
            Cancel
          </Button>
          <Button 
            variant="primary" 
            onClick={confirmSwitch}
            style={{ fontWeight: 500, backgroundColor: '#143142', borderColor: '#143142' }}
          >
            Yes, switch
          </Button>
        </Modal.Footer>
      </Modal>

    </div>
  );
};

export default App;
