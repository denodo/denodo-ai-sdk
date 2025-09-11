import React, { useState } from 'react';
import Modal from 'react-bootstrap/Modal';
import Form from 'react-bootstrap/Form';
import Button from 'react-bootstrap/Button';
import Spinner from 'react-bootstrap/Spinner';

const SignInModal = ({ show, handleClose, onSignIn }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);

    const savedUserDetails = localStorage.getItem(`${username}_userDetails`) || '';
    const savedCustomInstructions = localStorage.getItem(`${username}_customInstructions`) || '';
    try {
      await onSignIn({ username, password, authType: 'Basic', user_details: savedUserDetails, custom_instructions: savedCustomInstructions });
      localStorage.setItem('currentLoggedInUser', username);
    } finally {
      setIsLoading(false);
      handleClose();
    }
  };

  return (
    <Modal show={show} onHide={handleClose} style={{ '--bs-modal-bg': '#112533' }} contentClassName="text-white border border-white">
      <Modal.Header closeButton className="custom-header-modal">
        <Modal.Title>Sign In</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <Form onSubmit={handleSubmit}>
          <Form.Group className="mb-3">
            <Form.Label>Username</Form.Label>
            <Form.Control 
              type="text" 
              placeholder="Enter username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </Form.Group>
          <Form.Group className="mb-3">
            <Form.Label>Password</Form.Label>
            <Form.Control 
              type="password" 
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Form.Group>
          <Button variant="primary" type="submit" disabled={isLoading} style={{ backgroundColor: '#2D3E4B', borderColor: '#2D3E4B' }}>
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
              'Sign In'
            )}
          </Button>
        </Form>
      </Modal.Body>
    </Modal>
  );
};

export default SignInModal;