import React, { useState, useReducer, useCallback } from "react";
import "./Modal.css";
import Header from "./components/Header/Header";
import Chat from "./components/Chat/Chat";
import QuestionForm from "./components/QuestionForm/QuestionForm";
import ReportManagementModal from "./components/Header/ReportManagementModal";
import axios from "axios";
import useSDK from "./hooks/useSDK";
import LoginPage from "./components/LoginPage/LoginPage";
import { chatReducer, actionTypes } from "./reducers/chatReducer";
import { getStoredCSVConfigs, saveCSVConfigs } from "./components/Header/CSVManagerModal/utils";
import { getStoredSettings as getChatbotStoredSettings } from "./components/Header/ChatbotSettingsModal";
import { getStoredSettings as getAISDKStoredSettings } from "./components/Header/AISDKSettingsModal";

const App = () => {
  const [results, dispatch] = useReducer(chatReducer, []);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [showCSVManager, setShowCSVManager] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [completedRequestId, setCompletedRequestId] = useState(null);
  const [customLogoFailed, setCustomLogoFailed] = useState(false);
  const [syncedResources, setSyncedResources] = useState({});
  const [partialResources, setPartialResources] = useState({});
  const [userSyncPermissions, setUserSyncPermissions] = useState(true);

  const handleRequestCompletion = (requestId) => {
    setCompletedRequestId(requestId);
  };

  const sdk = useSDK(dispatch, handleRequestCompletion);

  const handleLogoError = () => {
    setCustomLogoFailed(true);
  };

  const handleResourcesUpdate = (data) => {
    if (data.syncedResources) {
      setSyncedResources(data.syncedResources);
    }
    if (data.partialResources) {
      setPartialResources(data.partialResources);
    }
  };

  const renderLogo = () => {
    const denodoLogo = (
      <img
        alt="Denodo company logo"
        src={`${process.env.PUBLIC_URL}/denodo.png`}
        height="30"
        className="d-inline-block align-top"
      />
    );

    if (!customLogoFailed) {
      return (
        <React.Fragment>
          {denodoLogo}
          {" + "}
          <img
            alt="Custom company logo"
            src={`${process.env.PUBLIC_URL}/logo.png`}
            height="30"
            className="d-inline-block align-top"
            onError={handleLogoError}
          />
        </React.Fragment>
      );
    } else {
      return denodoLogo;
    }
  };

  const handleSignIn = async (userInformation) => {
    try {
      const response = await axios.post('login', userInformation);
      if (response.data.success) {
        setIsAuthenticated(true);
        setSyncedResources(response.data.syncedResources || {});
        setPartialResources(response.data.partialResources || {});
        setUserSyncPermissions(response.data.userSyncPermissions !== false);
        
        // Restore LLM settings from localStorage after login
        const storedChatbotSettings = getChatbotStoredSettings(userInformation.username);
        const storedAISDKSettings = getAISDKStoredSettings(userInformation.username);
        if (storedChatbotSettings || storedAISDKSettings) {
          try {
            const payload = {
              ...(storedChatbotSettings || {}),
              ...(storedAISDKSettings || {}),
            };
            await axios.post('update_llm_settings', payload);
          } catch (error_) {
            console.error('Error restoring LLM settings:', error_);
          }
        }

        // Restore CSV sources from localStorage after login
        const storedCSVConfigs = getStoredCSVConfigs(userInformation.username);
        if (storedCSVConfigs && storedCSVConfigs.length > 0) {
          try {
            const restoreResponse = await axios.post('csv/restore', {
              csv_configs: storedCSVConfigs
            });
            if (restoreResponse.data.success) {
              // Update localStorage with only successfully restored sources
              // Remove failed sources (file not found)
              // Keep skipped sources (file exists but not vectorized - will appear as "scanned")
              if (restoreResponse.data.failed.length > 0 || restoreResponse.data.skipped.length > 0) {
                const failedNames = restoreResponse.data.failed.map(f => f.source_name);
                const skippedNames = restoreResponse.data.skipped.map(s => s.source_name);
                const validConfigs = storedCSVConfigs.filter(c => 
                  !failedNames.includes(c.source_name) && !skippedNames.includes(c.source_name)
                );
                saveCSVConfigs(userInformation.username, validConfigs);
              }
            }
          } catch (error_) {
            console.error('Error restoring CSV sources:', error_);
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
      await axios.post(`clear_history`);
    } catch (error) {
      console.error("There was an error clearing the memory!", error);
    }
  };

  const handleCSVSourcesChange = useCallback(async () => {
    // Refresh CSV sources from server
    try {
      const response = await axios.get('csv/list');
      if (response.data.success) {
        // Update localStorage
        const username = localStorage.getItem('current_user');
        if (username) {
          saveCSVConfigs(username, response.data.sources || []);
        }
      }
    } catch (err) {
      console.error('Error refreshing CSV sources:', err);
    }
    // Also clear chat to reload with new knowledge base
    handleClearResults();
  }, []);

  if (!isAuthenticated) {
    return <LoginPage onSignIn={handleSignIn} renderLogo={renderLogo} />;
  }

  return (
    <div className="d-flex flex-column vh-100" style={{ backgroundColor: "#fff" }}>
      <Header
        isAuthenticated={isAuthenticated}
        setIsAuthenticated={setIsAuthenticated}
        handleClearResults={handleClearResults}
        showClearButton={results.length > 0}
        onOpenCSVManager={() => setShowCSVManager(true)}
        showCSVManager={showCSVManager}
        setShowCSVManager={setShowCSVManager}
        renderLogo={renderLogo}
        syncedResources={syncedResources}
        partialResources={partialResources}
        userSyncPermissions={userSyncPermissions}
        onResourcesUpdate={handleResourcesUpdate}
        onCSVSourcesChange={handleCSVSourcesChange}
      />
      <div className="flex-grow-1 overflow-auto" style={{ marginTop: "76px", marginBottom: "100px", padding: "0 20px" }}>
        <Chat
          results={results}
          dispatch={dispatch}
          setCurrentQuestion={setCurrentQuestion}
        />
      </div>
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
      />
      <ReportManagementModal />
    </div>
  );
};

export default App;
