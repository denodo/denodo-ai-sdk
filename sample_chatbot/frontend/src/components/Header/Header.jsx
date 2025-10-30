import React, { useState, useEffect, useRef } from "react";
import Container from "react-bootstrap/Container";
import Navbar from "react-bootstrap/Navbar";
import Button from "react-bootstrap/Button";
import Badge from "react-bootstrap/Badge";
import Nav from 'react-bootstrap/Nav';
import NavDropdown from 'react-bootstrap/NavDropdown';
import axios from "axios";
import VectorDBSyncModal from '../VectorDBSyncModal';
import ChatbotSettingsModal from '../ChatbotSettingsModal';
import AISDKSettingsModal from '../AISDKSettingsModal';
import CustomInstructionsModal from '../CustomInstructionsModal';
import { usePDF } from '../../contexts/PDFContext';
import './Header.css';

const Header = ({ isAuthenticated, setIsAuthenticated, handleClearResults, showClearButton, onLoadCSV, renderLogo }) => {
  const [showVectorDBSync, setShowVectorDBSync] = useState(false);
  const [showChatbotSettings, setShowChatbotSettings] = useState(false);
  const [showAISDKSettings, setShowAISDKSettings] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [showToolsDropdown, setShowToolsDropdown] = useState(false);
  const [showAdminDropdown, setShowAdminDropdown] = useState(false);
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  const [config, setConfig] = useState({ hasAISDKCredentials: false, unstructuredMode: false, userEditLLM: false, syncTimeout: undefined });
  const { pdfs, setIsModalOpen } = usePDF();

  // Hover-delay timers for dropdowns
  const toolsTimerRef = useRef(null);
  const adminTimerRef = useRef(null);
  const userTimerRef = useRef(null);
  const HOVER_DELAY_MS = 100;

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
    // Cancel all timers and immediately show the hovered dropdown, closing others
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
    // Start a short timer to close only the hovered dropdown
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
    // Click toggles should replace the open dropdown immediately
    closeAllNow();
    if (!isOpen) return; // if clicking to close, we already closed
    if (which === 'tools') setShowToolsDropdown(true);
    else if (which === 'admin') setShowAdminDropdown(true);
    else setShowUserDropdown(true);
  };


  useEffect(() => {
    // Fetch configuration when component mounts
    const fetchConfig = async () => {
      try {
        const response = await axios.get('api/config');
        setConfig(response.data);
      } catch (error) {
        console.error('Error fetching config:', error);
      }
    };

    if (isAuthenticated) {
      fetchConfig();
    }
  }, [isAuthenticated]);

  const handleLogout = async () => {
    try {
      await axios.post("logout");
      handleClearResults();
      setIsAuthenticated(false);
    } catch (error) {
      console.error("Logout error:", error);
      alert("An error occurred during logout. Please try again.");
    }
  };

  return (
    <>
      <div
        className="background-header background-header--default"
        style={{ backgroundImage: `url(${process.env.PUBLIC_URL}/header_background.png)` }}
      />
      <Navbar className="navbar-transparent" data-bs-theme="dark" fixed="top">
        <Container fluid className="d-flex justify-content-between align-items-center">
          <Navbar.Brand href="#home" className="flex-grow-1 text-nowrap d-flex align-items-baseline brand-spacing">
            {renderLogo()}
            <span className="brand-ask ms-2">ASK A QUESTION</span>
          </Navbar.Brand>
          {isAuthenticated && (
            <div className="position-absolute start-50 translate-middle-x">
              <Button
                variant="light"
                bsPrefix="btn"
                size="sm"
                onClick={handleClearResults}
                style={{ backgroundColor: '#2D3E4B', borderColor: '#2D3E4B', color: 'white' }}
              >
                Clear results
              </Button>
            </div>
          )}
          <div>
            {isAuthenticated && (
                <Nav className="align-items-center">
                  <NavDropdown
                    title="Tools"
                    id="tools-nav-dropdown"
                    align={config.userEditLLM ? 'start' : 'end'} 
                    className="custom-nav-dropdown"
                    show={showToolsDropdown}
                    onMouseEnter={() => handleEnterWhich('tools')}
                    onMouseLeave={() => handleLeaveWhich('tools')}
                    onToggle={(isOpen) => handleToggleWhich('tools', isOpen)}
                  >
                    <NavDropdown.Item onClick={() => setIsModalOpen(true)}>
                      DeepQuery Reports
                      {pdfs.length > 0 && (
                        <Badge bg="warning" text="dark" className="ms-2">
                          {pdfs.length}
                        </Badge>
                      )}
                    </NavDropdown.Item>
                    {config.unstructuredMode && (
                      <NavDropdown.Item onClick={onLoadCSV}>Load Unstructured CSV</NavDropdown.Item>
                    )}
                    {config.hasAISDKCredentials && (
                      <NavDropdown.Item onClick={() => setShowVectorDBSync(true)}>VectorDB Management</NavDropdown.Item>
                    )}
                  </NavDropdown>

                  {config.userEditLLM && (
                    <NavDropdown
                      title="Administration"
                      id="admin-nav-dropdown"
                      align="end"
                      className="custom-nav-dropdown"
                      show={showAdminDropdown}
                      onMouseEnter={() => handleEnterWhich('admin')}
                      onMouseLeave={() => handleLeaveWhich('admin')}
                      onToggle={(isOpen) => handleToggleWhich('admin', isOpen)}
                    >
                      <NavDropdown.Item onClick={() => setShowChatbotSettings(true)}>Chatbot Settings</NavDropdown.Item>
                      <NavDropdown.Item onClick={() => setShowAISDKSettings(true)}>AI SDK Settings</NavDropdown.Item>
                    </NavDropdown>
                  )}

                  <NavDropdown
                    id="user-nav-dropdown"
                    align="end"
                    className="user-nav-dropdown"
                    title={(<span className="user-dropdown-toggle"><img alt="User" src={`${process.env.PUBLIC_URL}/user.png`} className="user-avatar" /></span>)}
                    show={showUserDropdown}
                    onMouseEnter={() => handleEnterWhich('user')}
                    onMouseLeave={() => handleLeaveWhich('user')}
                    onToggle={(isOpen) => handleToggleWhich('user', isOpen)}
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
      <VectorDBSyncModal
        show={showVectorDBSync}
        syncTimeout={config.syncTimeout}
        handleClose={() => setShowVectorDBSync(false)}
      />
      <ChatbotSettingsModal
        show={showChatbotSettings}
        handleClose={() => setShowChatbotSettings(false)}
        handleClearResults={handleClearResults}
      />
      <AISDKSettingsModal
        show={showAISDKSettings}
        handleClose={() => setShowAISDKSettings(false)}
        handleClearResults={handleClearResults}
      />
      <CustomInstructionsModal
        show={showProfile}
        handleClose={() => setShowProfile(false)}
      />
    </>
  );
};

export default Header;