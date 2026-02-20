import React, { useState, useEffect } from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Spinner from 'react-bootstrap/Spinner';
import axios from 'axios';
import HelpTooltip from '../HelpTooltip'; 

const CustomInstructionsModal = ({ show, handleClose }) => {
  const [customInstructions, setCustomInstructions] = useState('');
  const [userDetails, setUserDetails] = useState('');
  const [username, setUsername] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (show) {
      const currentUser = localStorage.getItem('current_user');
      if (!currentUser) return;
      const savedUserDetails = localStorage.getItem(`${currentUser}_user_details`) || '';
      const savedCustomInstructions = localStorage.getItem(`${currentUser}_custom_instructions`) || '';
      
      setUsername(currentUser);
      setUserDetails(savedUserDetails);
      setCustomInstructions(savedCustomInstructions);
    }
  }, [show]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      localStorage.setItem(`${username}_user_details`, userDetails);
      localStorage.setItem(`${username}_custom_instructions`, customInstructions);
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
    <Modal show={show} onHide={handleClose} centered>
      <Modal.Header closeButton data-bs-theme="light">
        <Modal.Title>User Profile</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <Form id="profile-form" onSubmit={handleSubmit}>
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
            <Form.Label className="d-flex align-items-center gap-2">
              User Details
              <HelpTooltip text="This information is sent to the chatbot LLM to personalize the conversation based on your user profile." />
            </Form.Label>
            <Form.Control
              as="textarea"
              rows={3}
              placeholder="Example: My name is Matthew Richardson, I'm a loan officer and my email is matthew.richardson@example.com"
              value={userDetails}
              onChange={(e) => setUserDetails(e.target.value)}
            />
          </Form.Group>
          
          <Form.Group controlId="formCustomInstructions" className="mb-3">
            <Form.Label className="d-flex align-items-center gap-2">
              Custom Instructions
              <HelpTooltip text="Passed to the AI SDK's answerQuestion endpoint for view search and VQL generation. These instructions are appended to any existing ones already defined in the AI SDK." />
            </Form.Label>
            <Form.Control
              as="textarea"
              rows={5}
              placeholder="Example: When I ask for information about a specific loan, always return the associated loan officer."
              value={customInstructions}
              onChange={(e) => setCustomInstructions(e.target.value)}
            />
          </Form.Group>
         </Form>
      </Modal.Body>

      <Modal.Footer>
        <Button variant="light" onClick={handleClose} disabled={isLoading}>
          Cancel
        </Button>
        <Button 
          variant="dark" 
          type="submit" 
          form="profile-form"
          disabled={isLoading}
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
                <span className="ms-2">Updating...</span>
              </>
            ) : (
              'Save Profile'
            )}
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default CustomInstructionsModal;
