import React, { useState, useEffect } from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Spinner from 'react-bootstrap/Spinner';
import axios from 'axios';

const CustomInstructionsModal = ({ show, handleClose }) => {
  const [customInstructions, setCustomInstructions] = useState('');
  const [userDetails, setUserDetails] = useState('');
  const [username, setUsername] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (show) {
      const currentUser = localStorage.getItem('currentLoggedInUser');
      if (!currentUser) return;
      const savedUserDetails = localStorage.getItem(`${currentUser}_userDetails`) || '';
      const savedCustomInstructions = localStorage.getItem(`${currentUser}_customInstructions`) || '';
      
      setUsername(currentUser);
      setUserDetails(savedUserDetails);
      setCustomInstructions(savedCustomInstructions);
    }
  }, [show]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      localStorage.setItem(`${username}_userDetails`, userDetails);
      localStorage.setItem(`${username}_customInstructions`, customInstructions);
      const response = await axios.post('update_custom_instructions', {
        custom_instructions: customInstructions,
        user_details: userDetails
      });
      
      if (response.status === 200) {
        alert('Profile updated successfully!');
        handleClose();
      }
    } catch (error) {
      console.error('Error updating profile:', error);
      alert(error.response?.data?.error || 'An error occurred while updating your profile.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal show={show} onHide={handleClose} style={{ '--bs-modal-bg': '#112533' }} contentClassName="text-white border border-white">
      <Modal.Header closeButton className="custom-header-modal">
        <Modal.Title>User Profile</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <Form onSubmit={handleSubmit}>
          <Form.Group controlId="formUsername" className="mb-3">
            <Form.Label>Username</Form.Label>
            <Form.Control
              type="text"
              readOnly
              value={username}
              placeholder="Loading username..."
            />
          </Form.Group>
          
          <Form.Group controlId="formUserDetails" className="mb-3">
            <Form.Label>User Details</Form.Label>
            <Form.Control
              as="textarea"
              rows={3}
              placeholder="Example: My name is Matthew Richardson, I'm a loan officer and my email is matthew.richardson@example.com"
              value={userDetails}
              onChange={(e) => setUserDetails(e.target.value)}
            />
          </Form.Group>
          
          <Form.Group controlId="formCustomInstructions" className="mb-3">
            <Form.Label>Custom Instructions</Form.Label>
            <Form.Control
              as="textarea"
              rows={5}
              placeholder="Example: When I ask for information about a specific loan, always return the associated loan officer."
              value={customInstructions}
              onChange={(e) => setCustomInstructions(e.target.value)}
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
                <span className="ms-2">Updating...</span>
              </>
            ) : (
              'Save Profile'
            )}
          </Button>
        </Form>
      </Modal.Body>
    </Modal>
  );
};

export default CustomInstructionsModal; 