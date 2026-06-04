import React, { useState, useRef } from "react";
import PropTypes from 'prop-types';
import Container from "react-bootstrap/Container";
import Navbar from "react-bootstrap/Navbar";
import Button from "react-bootstrap/Button";
import Badge from "react-bootstrap/Badge";
import Nav from 'react-bootstrap/Nav';
import NavDropdown from 'react-bootstrap/NavDropdown';
import VectorDBSyncModal from './VectorDBSyncModal';
import SettingsModal from './SettingsModal';
import ProfileModal from './ProfileModal';
import CSVManagerModal from './CSVManagerModal/CSVManagerModal';
import { useReport } from '../../contexts/ReportContext';
import { useConfig } from '../../contexts/ConfigContext';
import api from "../../api/client";
import './Header.css';

const assetBaseUrl = import.meta.env.BASE_URL;

const Header = ({ 
  isAuthenticated, 
  setIsAuthenticated, 
  handleClearResults, 
  onOpenCSVManager,
  showCSVManager,
  setShowCSVManager,
  renderLogo,
  showBrandAsk = true,
  syncedResources,
  userSyncPermissions,
  onResourcesUpdate,
  hasActiveConversation = false,
  toggleSidebar,
  isSidebarOpen,
  selectedChatbot,
  globalEnabled = false,
  onSettingsApplied,
  isSwitchingAgent
}) => {
  const [showVectorDBSync, setShowVectorDBSync] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [showToolsDropdown, setShowToolsDropdown] = useState(false);
  const [showAdminDropdown, setShowAdminDropdown] = useState(false);
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  const { config } = useConfig();
  const { reports, setIsModalOpen } = useReport();

  // Hover-delay timers for dropdowns
  const toolsTimerRef = useRef(null);
  const adminTimerRef = useRef(null);
  const userTimerRef = useRef(null);
  const HOVER_DELAY_MS = 100;

  const isWelcomeScreen = !selectedChatbot;
  const isGlobalChat = selectedChatbot && selectedChatbot.isGlobal;
  const isSpecializedChat = selectedChatbot && !selectedChatbot.isGlobal;

  const canShowAdvancedOptions = (globalEnabled && (isWelcomeScreen || isGlobalChat)) || isSpecializedChat;

  const showDeepQuery = canShowAdvancedOptions && config.enable_deep_query;
  const showKnowledgeBase = canShowAdvancedOptions && config.unstructured_mode; 

  const showVectorDBManager = config.allow_sync && (globalEnabled && (isWelcomeScreen || isGlobalChat)) && (config.has_ai_sdk_credentials || userSyncPermissions);

  const hasToolsItems = showDeepQuery || showKnowledgeBase || showVectorDBManager;
  const showToolsMenu = hasToolsItems;

  const canEditLLM = canShowAdvancedOptions && config.user_edit_llm;
  const canEditInstructions = canShowAdvancedOptions && config.can_edit_instructions;
  const showAdminMenu = !isWelcomeScreen && (canEditLLM || canEditInstructions);

  const clearTimer = (ref) => {
    if (ref.current) {
      clearTimeout(ref.current);
      ref.current = null;
    }
  };

  const closeAllNow = () => {
    clearTimer(toolsTimerRef);
    clearTimer(adminTimerRef);
    clearTimer(userTimerRef);
    setShowToolsDropdown(false);
    setShowAdminDropdown(false);
    setShowUserDropdown(false);
  };

  const handleEnterWhich = (which) => {
    if (isSwitchingAgent) return;
    clearTimer(toolsTimerRef);
    clearTimer(adminTimerRef);
    clearTimer(userTimerRef);
    if (which === 'tools') {
      setShowToolsDropdown(true);
      setShowAdminDropdown(false);
      setShowUserDropdown(false);
    } else if (which === 'admin') {
      setShowAdminDropdown(true);
      setShowToolsDropdown(false);
      setShowUserDropdown(false);
    } else {
      setShowUserDropdown(true);
      setShowToolsDropdown(false);
      setShowAdminDropdown(false);
    }
  };

  const handleLeaveWhich = (which) => {
    if (isSwitchingAgent) return;
    if (which === 'tools') {
      clearTimer(toolsTimerRef);
      toolsTimerRef.current = setTimeout(() => setShowToolsDropdown(false), HOVER_DELAY_MS);
    } else if (which === 'admin') {
      clearTimer(adminTimerRef);
      adminTimerRef.current = setTimeout(() => setShowAdminDropdown(false), HOVER_DELAY_MS);
    } else {
      clearTimer(userTimerRef);
      userTimerRef.current = setTimeout(() => setShowUserDropdown(false), HOVER_DELAY_MS);
    }
  };

  const handleToggleWhich = (which, isOpen) => {
    if (isSwitchingAgent) return;
    closeAllNow();
    if (!isOpen) return;
    if (which === 'tools') setShowToolsDropdown(true);
    else if (which === 'admin') setShowAdminDropdown(true);
    else setShowUserDropdown(true);
  };

  const handleLogout = async () => {
    try {
      await api.post("logout");
      handleClearResults();
      setIsAuthenticated(false);
    } catch (error) {
      console.error("Logout error:", error);
      alert("An error occurred during logout. Please try again.");
    }
  };

  const getBadgeProps = () => {
    // Default if no reports exist
    if (!reports || reports.length === 0) {
      return { bg: 'warning', text: 'dark' };
    }
    
    // Check the LAST report in the array
    const lastReport = reports[reports.length - 1];
    const status = lastReport?.status;

    if (status === 'completed') {
      return { bg: 'success', text: 'white' };
    } else if (status === 'failed') {
      return { bg: 'danger', text: 'white' }; 
    } else {
      return { bg: 'warning', text: 'dark' };
    }
  };

  const badgeProps = getBadgeProps();

  const agentName = selectedChatbot ? (selectedChatbot.isGlobal ? 'General Chat' : selectedChatbot.name) : 'General Chat';
  const settingsTitle = agentName.length > 20 ? 'Custom Agent Settings' : `${agentName} Settings`;

  return (
    <>
      <div 
        style={{
          backgroundImage: `url(${assetBaseUrl}header/header_background.png)`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
          width: '100%',
          boxShadow: '0 2px 4px rgba(0,0,0,0.08)'
        }}
      >
        <Navbar className="navbar-transparent position-relative" data-bs-theme="dark" style={{ height: '76px' }}>
          <Container fluid className="d-flex justify-content-between align-items-center">
            <div className="d-flex align-items-center flex-grow-1">
              {isAuthenticated && (
                <Button
                  variant="link"
                  onClick={toggleSidebar}
                  className="text-light p-0 me-3 d-flex align-items-center justify-content-center"
                  style={{
                    textDecoration: 'none',
                    border: 'none',
                    visibility: isSidebarOpen ? 'hidden' : 'visible',
                    pointerEvents: isSidebarOpen ? 'none' : 'auto',
                    opacity: isSwitchingAgent ? 0.5 : 1
                  }}
                  disabled={isSwitchingAgent}
                  title="Open sidebar"
                >
                  <i className="bi bi-list" style={{ fontSize: '1.5rem', lineHeight: 1 }}></i>
                </Button>
              )}

              <Navbar.Brand className="text-nowrap d-flex align-items-baseline brand-spacing m-0 px-0" style={{ paddingBottom: '5px' }}>
                {renderLogo()}
                {showBrandAsk && (
                  <span className="brand-ask ms-2">ASK A QUESTION</span>
                )}
              </Navbar.Brand>
            </div>

            {isAuthenticated && selectedChatbot && !selectedChatbot.isGlobal && (
              <div className="position-absolute top-50 start-50 translate-middle d-none d-md-flex align-items-center justify-content-center" style={{ pointerEvents: 'none' }}>
                <span className="brand-ask text-light m-0 p-0" style={{ letterSpacing: '0.5px', lineHeight: 1 }}>
                  {selectedChatbot.name.toUpperCase()}
                </span>
              </div>
            )}

            <div>
              {isAuthenticated && (
                  <Nav className="align-items-center">

                    {showToolsMenu && (
                      <NavDropdown
                        title="Tools"
                        id="tools-nav-dropdown"
                        align="end"
                        className="custom-nav-dropdown"
                        show={showToolsDropdown}
                        onMouseEnter={() => handleEnterWhich('tools')}
                        onMouseLeave={() => handleLeaveWhich('tools')}
                        onToggle={(isOpen) => handleToggleWhich('tools', isOpen)}
                        disabled={isSwitchingAgent}
                        style={{ opacity: isSwitchingAgent ? 0.5 : 1, pointerEvents: isSwitchingAgent ? 'none' : 'auto' }} // <--- ESTILO VISUAL
                      >
                        {showDeepQuery && (
                          <NavDropdown.Item onClick={() => setIsModalOpen(true)}>
                            DeepQuery Reports
                            {reports.length > 0 && (
                              <Badge bg={badgeProps.bg} text={badgeProps.text} className="ms-2">
                                {reports.length}
                              </Badge>
                            )}
                          </NavDropdown.Item>
                        )}

                        {showKnowledgeBase && (
                          <NavDropdown.Item onClick={onOpenCSVManager}>Knowledge Base Manager</NavDropdown.Item>
                        )}
                        
                        {showVectorDBManager && (
                          <NavDropdown.Item onClick={() => setShowVectorDBSync(true)}>Vector DB Manager</NavDropdown.Item>
                        )}
                      </NavDropdown>
                    )}

                  {showAdminMenu && (
                    <NavDropdown
                      title="Administration"
                      id="admin-nav-dropdown"
                      align="end"
                      className="custom-nav-dropdown"
                      show={showAdminDropdown}
                      onMouseEnter={() => handleEnterWhich('admin')}
                      onMouseLeave={() => handleLeaveWhich('admin')}
                      onToggle={(isOpen) => handleToggleWhich('admin', isOpen)}
                      disabled={isSwitchingAgent}
                      style={{ opacity: isSwitchingAgent ? 0.5 : 1, pointerEvents: isSwitchingAgent ? 'none' : 'auto' }} // <--- ESTILO VISUAL
                    >
                      <NavDropdown.Item onClick={() => setShowSettings(true)}>
                        {settingsTitle}
                      </NavDropdown.Item>
                    </NavDropdown>
                  )}

                    <NavDropdown
                      id="user-nav-dropdown"
                      align="end"
                      className="user-nav-dropdown"
                      title={(<span className="user-dropdown-toggle"><img alt="User" src={`${assetBaseUrl}header/user.png`} className="user-avatar" /></span>)}
                      show={showUserDropdown}
                      onMouseEnter={() => handleEnterWhich('user')}
                      onMouseLeave={() => handleLeaveWhich('user')}
                      onToggle={(isOpen) => handleToggleWhich('user', isOpen)}
                      disabled={isSwitchingAgent}
                      style={{ opacity: isSwitchingAgent ? 0.5 : 1, pointerEvents: isSwitchingAgent ? 'none' : 'auto' }} // <--- ESTILO VISUAL
                    >
                      <NavDropdown.Item onClick={() => setShowProfile(true)}>Profile</NavDropdown.Item>
                      <NavDropdown.Divider />
                      <NavDropdown.Item onClick={handleLogout} className="text-danger">Logout</NavDropdown.Item>
                    </NavDropdown>
                  </Nav>
              )}
            </div>
          </Container>
        </Navbar>
      </div>

      <VectorDBSyncModal
        show={showVectorDBSync}
        handleClose={() => setShowVectorDBSync(false)}
        syncedResources={syncedResources} 
        onResourcesUpdate={onResourcesUpdate}
      />
      <SettingsModal
        show={showSettings}
        handleClose={() => setShowSettings(false)}
        handleClearResults={handleClearResults}
        selectedChatbot={selectedChatbot}
        onSettingsApplied={onSettingsApplied}
        title={settingsTitle} 
      />
      <ProfileModal
        show={showProfile}
        handleClose={() => setShowProfile(false)}
        selectedChatbot={selectedChatbot}
      />
      {showCSVManager !== undefined && (
        <CSVManagerModal
          show={showCSVManager}
          handleClose={() => setShowCSVManager(false)}
          hasActiveConversation={hasActiveConversation}
          selectedChatbot={selectedChatbot}
        />
      )}
    </>
  );
};

Header.propTypes = {
  isAuthenticated: PropTypes.bool.isRequired,
  setIsAuthenticated: PropTypes.func.isRequired,
  handleClearResults: PropTypes.func.isRequired,
  showClearButton: PropTypes.bool,
  onOpenCSVManager: PropTypes.func,
  showCSVManager: PropTypes.bool,
  setShowCSVManager: PropTypes.func,
  renderLogo: PropTypes.func.isRequired,
  showBrandAsk: PropTypes.bool,
  syncedResources: PropTypes.object,
  userSyncPermissions: PropTypes.bool,
  onResourcesUpdate: PropTypes.func,
  hasActiveConversation: PropTypes.bool,
  toggleSidebar: PropTypes.func,
  isSidebarOpen: PropTypes.bool,
  selectedChatbot: PropTypes.object,
  globalEnabled: PropTypes.bool,
  onSettingsApplied: PropTypes.func,
  isSwitchingAgent: PropTypes.bool
};

export default Header;
