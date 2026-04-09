import React, { useState, useEffect } from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Spinner from 'react-bootstrap/Spinner';
import api from '../../api/client';
import CustomTooltip from '../CustomTooltip/CustomTooltip';
import NotificationToast from '../NotificationToast/NotificationToast';

const ProfileModal = ({ 
  show, 
  handleClose,
  selectedChatbot 
}) => {
  const [userDetails, setUserDetails] = useState('');
  const [username, setUsername] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: '',
    variant: 'info',
    title: ''
  });

  const currentAgentKey = selectedChatbot ? (selectedChatbot.isGlobal ? 'global' : selectedChatbot.id) : 'global';

  useEffect(() => {
    if (show) {
      const currentUser = localStorage.getItem('current_user');
      if (!currentUser) return;
      
      setUsername(currentUser);

      const savedUserDetails = localStorage.getItem(`${currentUser}_user_details`) || '';
      setUserDetails(savedUserDetails);
    }
  }, [show]);

  const handleOnExited = () => {
    setIsLoading(false);
  };

  const showToast = (message, variant, title) => {
    setToastConfig({ show: true, message, variant, title, duration: 4000 });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      const dictString = localStorage.getItem(`${username}_custom_instructions_dict`);
      let currentInstructions = '';
      if (dictString) {
        try {
          const instructionsDict = JSON.parse(dictString);
          currentInstructions = instructionsDict[currentAgentKey] || '';
        } catch (e) {}
      }

      const response = await api.post("update_custom_instructions", {
        custom_instructions: currentInstructions,
        user_details: userDetails
      });
      
      if (response.status === 200) {
        localStorage.setItem(`${username}_user_details`, userDetails);
        showToast('Your user profile has been successfully updated.', 'success', 'Profile Saved');
        handleClose();
      }
    } catch (error) {
      console.error('Error updating profile:', error);
      showToast(error.response?.data?.error || 'An error occurred while updating your profile.', 'danger', 'Update Error');
      setIsLoading(false);
    }
  };

  return (
    <>
      <Modal show={show} onHide={handleClose} onExited={handleOnExited} centered>
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
              <Form.Label className="d-flex align-items-center">
                User Details
                <CustomTooltip 
                  id="tooltip-user-details" 
                  content="This information is sent to the chatbot LLM to personalize the conversation based on your user profile."
                >
                  <i 
                    className="bi bi-info-circle ms-2" 
                    style={{ cursor: 'help', fontSize: '0.85rem', color: '#adb5bd', transition: 'color 0.2s' }}
                    onMouseEnter={(e) => e.target.style.color = '#112533'}
                    onMouseLeave={(e) => e.target.style.color = '#adb5bd'}
                  ></i>
                </CustomTooltip>
              </Form.Label>
              <Form.Control
                as="textarea"
                rows={3}
                placeholder="Example: My name is Matthew Richardson, I'm a loan officer and my email is matthew.richardson@example.com"
                value={userDetails}
                onChange={(e) => setUserDetails(e.target.value)}
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

      <NotificationToast
        show={toastConfig.show}
        message={toastConfig.message}
        variant={toastConfig.variant}
        title={toastConfig.title}
        duration={toastConfig.duration}
        onClose={() => setToastConfig(prev => ({...prev, show: false}))}
      />
    </>
  );
};

export default ProfileModal;
