import React, { useState, useEffect } from "react";
import Container from "react-bootstrap/Container";
import Navbar from "react-bootstrap/Navbar";
import Button from "react-bootstrap/Button";
import axios from "axios";
import VectorDBSyncModal from '../VectorDBSyncModal';
import CustomInstructionsModal from '../CustomInstructionsModal';

const Header = ({ isAuthenticated, setIsAuthenticated, handleClearResults, showClearButton, onLoadCSV }) => {
  const [customLogoFailed, setCustomLogoFailed] = useState(false);
  const [showVectorDBSync, setShowVectorDBSync] = useState(false);
  const [showCustomInstructions, setShowCustomInstructions] = useState(false);
  const [config, setConfig] = useState({ hasAISDKCredentials: false, unstructuredMode: false });

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

  const handleLogoError = () => {
    setCustomLogoFailed(true);
  };

  const handleLogout = async () => {
    try {
      await axios.post("logout");
      setIsAuthenticated(false);
    } catch (error) {
      console.error("Logout error:", error);
      alert("An error occurred during logout. Please try again.");
    }
  };

  const renderLogo = () => {
    const denodoLogo = (
      <img
        alt="Denodo company logo"
        src={`${process.env.PUBLIC_URL}/denodo.png`}
        height="22.5"
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
            height="22.5"
            className="d-inline-block align-top"
            onError={handleLogoError}
          />
        </React.Fragment>
      );
    } else {
      return denodoLogo;
    }
  };

  return (
    <>
      <Navbar className="bg-body-tertiary" data-bs-theme="dark" fixed="top">
        <Container fluid className="d-flex justify-content-between align-items-center">
          <Navbar.Brand href="#home" className="flex-grow-1">
            Ask a question
            {" | "}
            {renderLogo()}
          </Navbar.Brand>
          <div className="position-absolute start-50 translate-middle-x">
            {showClearButton && (
              <Button
                variant="light"
                bsPrefix="btn"
                size="sm"
                onClick={handleClearResults}
              >
                Clear results
              </Button>
            )}
          </div>
          <div>
            {isAuthenticated && (
              <>
                <Button 
                  variant="secondary" 
                  bsPrefix="btn"
                  size="sm" 
                  onClick={() => setShowCustomInstructions(true)} 
                  className="me-2"
                >
                  Profile
                </Button>
                {config.unstructuredMode && (
                  <Button 
                    variant="secondary"
                    size="sm"
                    onClick={onLoadCSV}
                    bsPrefix="btn"
                    className="me-2">
                    Load Unstructured CSV
                  </Button>
                )}
                {config.hasAISDKCredentials && (
                  <Button 
                    variant="secondary" 
                    bsPrefix="btn"
                    size="sm" 
                    onClick={() => setShowVectorDBSync(true)} 
                    className="me-2"
                  >
                    Sync VectorDB
                  </Button>
                )}
                <Button
                  variant="danger"
                  size="sm"
                  onClick={handleLogout}
                  bsPrefix="btn"
                >
                  Logout
                </Button>
              </>
            )}
          </div>
        </Container>
      </Navbar>
      <VectorDBSyncModal
        show={showVectorDBSync}
        syncTimeout={config.syncTimeout}
        handleClose={() => setShowVectorDBSync(false)}
      />
      <CustomInstructionsModal
        show={showCustomInstructions}
        handleClose={() => setShowCustomInstructions(false)}
      />
    </>
  );
};

export default Header;