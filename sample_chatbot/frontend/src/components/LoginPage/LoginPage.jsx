import React, { useState } from "react";
import Form from "react-bootstrap/Form";
import Button from "react-bootstrap/Button";
import Spinner from "react-bootstrap/Spinner";
import Navbar from "react-bootstrap/Navbar";
import "./LoginPage.css";

const LoginPage = ({ onSignIn, renderLogo }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);

    const savedUserDetails =
      localStorage.getItem(`${username}_userDetails`) || "";
    const savedCustomInstructions =
      localStorage.getItem(`${username}_customInstructions`) || "";

    try {
      await onSignIn({
        username,
        password,
        authType: "Basic",
        user_details: savedUserDetails,
        custom_instructions: savedCustomInstructions,
      });
      localStorage.setItem("currentLoggedInUser", username);
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
        backgroundImage: `url(${process.env.PUBLIC_URL}/header_background.png)`,
      }}
    >
      <div className="login-box p-4 rounded">
        <Navbar.Brand
          href="#home"
          className="flex-grow-1 text-nowrap d-flex align-items-baseline justify-content-center"
        >
          {renderLogo()}
          <span className="brand-ask ms-2">ASK A QUESTION</span>
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

export default LoginPage;
