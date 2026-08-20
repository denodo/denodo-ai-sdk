import React, { useState } from "react";
import PropTypes from "prop-types";
import Form from "react-bootstrap/Form";
import Button from "react-bootstrap/Button";
import Spinner from "react-bootstrap/Spinner";
import Navbar from "react-bootstrap/Navbar";
import "./LoginPage.css";

const assetBaseUrl = import.meta.env.BASE_URL;

const LoginPage = ({ onSignIn, renderLogo, showBrandAsk = true, isCheckingLogo = false }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);

    const savedUserDetails =
      localStorage.getItem(`${username}_user_details`) || "";
    let savedCustomInstructions = null;
    const ciDictStr = localStorage.getItem(
      `${username}_custom_instructions_dict`,
    );
    if (ciDictStr) {
      try {
        savedCustomInstructions = JSON.parse(ciDictStr);
      } catch (e) {
        savedCustomInstructions = null;
      }
    }
    if (savedCustomInstructions == null) {
      const legacy = localStorage.getItem(`${username}_custom_instructions`);
      if (legacy) {
        savedCustomInstructions = { global: legacy };
      }
    }

    try {
      await onSignIn({
        username,
        password,
        authType: "Basic",
        user_details: savedUserDetails,
        custom_instructions: savedCustomInstructions,
      });
      localStorage.setItem("current_user", username);
    } catch (error) {
      console.error("Login failed:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      className="login-container d-flex justify-content-center align-items-center vh-100"
      style={{
        backgroundImage: `url(${assetBaseUrl}header/header_background.png)`,
        backgroundColor: "#143142",
        backgroundSize: "cover",
        backgroundPosition: "center"
      }}
    >
      <div 
        className="login-box p-4 rounded"
        style={{ 
          opacity: isCheckingLogo ? 0 : 1, 
          transition: "opacity 0.5s ease-in-out" 
        }}
      >
        <Navbar.Brand
          href="#home"
          className="flex-grow-1 text-nowrap d-flex align-items-baseline justify-content-center"
        >
          {renderLogo()}
          {showBrandAsk && (
            <span className="brand-ask ms-2">ASK A QUESTION</span>
          )}
        </Navbar.Brand>
        <Form onSubmit={handleSubmit}>
          <Form.Group className="mb-3">
            <Form.Label className="text-white">User</Form.Label>
            <Form.Control
              type="text"
              placeholder="Enter username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </Form.Group>
          <Form.Group className="mb-3">
            <Form.Label className="text-white">Password</Form.Label>
            <Form.Control
              type="password"
              placeholder="Enter password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Form.Group>
          <div className="d-grid submit-button-wrapper">
            <Button
              variant="primary"
              type="submit"
              disabled={isLoading || !username || !password}
              style={{ backgroundColor: "#2D3E4B", borderColor: "#2D3E4B" }}
            >
              {isLoading ? (
                <>
                  <Spinner
                    as="span"
                    animation="border"
                    size="sm"
                    role="status"
                    aria-hidden="true"
                  />
                  <span className="ms-2">Signing In...</span>
                </>
              ) : (
                "Sign In"
              )}
            </Button>
          </div>
        </Form>
      </div>
    </div>
  );
};

LoginPage.propTypes = {
  onSignIn: PropTypes.func.isRequired,
  renderLogo: PropTypes.func.isRequired,
  showBrandAsk: PropTypes.bool,
  isCheckingLogo: PropTypes.bool,
};

export default LoginPage;
