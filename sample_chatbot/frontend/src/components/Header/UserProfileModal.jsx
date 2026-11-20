import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { BaseModal } from '../Common/Modal';
import Spinner from 'react-bootstrap/Spinner';
import Form from 'react-bootstrap/Form';
import api from '../../api/client';
import CustomTooltip from '../CustomTooltip/CustomTooltip';
import NotificationToast from '../NotificationToast/NotificationToast';
import { useConfig } from '../../contexts/ConfigContext';
import { NUMBER_FORMATS, DEFAULT_NUMBER_FORMAT } from '../../utils/numberFormat';

const UserProfileModal = ({ show, handleClose }) => {
  const { profile, updateProfile } = useConfig();
  const [userDetails, setUserDetails] = useState('');
  const [username, setUsername] = useState('');
  const [inputMethod, setInputMethod] = useState('enter');
  const [numberFormat, setNumberFormat] = useState(DEFAULT_NUMBER_FORMAT);
  const [isLoading, setIsLoading] = useState(false);

  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: '',
    variant: 'info',
    title: ''
  });

  useEffect(() => {
    if (show) {
      const currentUser = localStorage.getItem('current_user');
      if (!currentUser) return;
      setUsername(currentUser);

      setUserDetails(profile.user_details || '');
      setInputMethod(profile.input_method || 'enter');
      setNumberFormat(profile.number_format || DEFAULT_NUMBER_FORMAT);
    }
  }, [show, profile.input_method, profile.number_format, profile.user_details]);

  const handleOnExited = () => {
    setIsLoading(false);
  };

  const showToast = (message, variant, title) => {
    setToastConfig({ show: true, message, variant, title, duration: 4000 });
  };

  const handleToastClose = () => {
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      const response = await api.post("update_custom_instructions", {
        user_details: userDetails,
        input_method: inputMethod,
        number_format: numberFormat,
      });

      if (response.status === 200) {
        updateProfile({
          user_details: userDetails,
          input_method: inputMethod,
          number_format: numberFormat,
        });
        showToast('Your user profile has been successfully updated.', 'success', 'Profile Saved');
        handleClose();
      }
    } catch (error) {
      console.error('Error updating profile:', error);
      showToast(error.response?.data?.error || 'An error occurred while updating your profile.', 'danger', 'Update Error');
    } finally {
      setIsLoading(false);
    }
  };

  const footer = (
    <>
      <button type="button" className="rcc-ghost-btn" onClick={handleClose} disabled={isLoading}>
        Cancel
      </button>
      <button type="submit" className="rcc-primary-btn" form="profile-form" disabled={isLoading}>
        {isLoading ? (
          <>
            <Spinner as="span" animation="border" size="sm" role="status" aria-hidden="true" />
            <span className="ms-2">Updating...</span>
          </>
        ) : (
          'Save Profile'
        )}
      </button>
    </>
  );

  return (
    <>
      <BaseModal
        show={show}
        onHide={handleClose}
        onExited={handleOnExited}
        title="User Profile"
        size="md"
        backdrop="static"
        className="profile-modal"
        scrollableBody
        footer={footer}
      >
            <Form id="profile-form" onSubmit={handleSubmit}>
              <Form.Group controlId="formUsername" className="mb-3">
                <Form.Label className="small fw-semibold">Username</Form.Label>
                <Form.Control
                  type="text"
                  readOnly
                  value={username}
                  placeholder="Loading username..."
                />
              </Form.Group>
              
              <Form.Group controlId="formUserDetails" className="mb-3">
                <Form.Label className="small fw-semibold d-flex align-items-center">
                  What should the agents know about you?
                  <CustomTooltip 
                    id="tooltip-user-details" 
                    content="This information is sent to the agent to personalize the conversation. For example, your name or preferences."
                  >
                    <i className="bi bi-info-circle info-icon ms-2"></i>
                  </CustomTooltip>
                </Form.Label>
                <Form.Control
                  as="textarea"
                  rows={3}
                  placeholder="Example: My name is Matthew, I'm a loan officer..."
                  value={userDetails}
                  onChange={(e) => setUserDetails(e.target.value)}
                  style={{ resize: 'none' }}
                />
              </Form.Group>

              <Form.Group controlId="formInputMethod" className="mb-3">
                <Form.Label className="small fw-semibold d-flex align-items-center">
                  Input method
                  <CustomTooltip
                    id="tooltip-input-method"
                    content="Key combination used to send messages. Ctrl+Enter is recommended for IME languages."
                  >
                    <i className="bi bi-info-circle info-icon ms-2"></i>
                  </CustomTooltip>
                </Form.Label>
                <Form.Select
                  value={inputMethod}
                  onChange={(e) => setInputMethod(e.target.value)}
                >
                  <option value="enter">Enter to send</option>
                  <option value="ctrl_enter">Ctrl+Enter to send</option>
                </Form.Select>
              </Form.Group>

              <Form.Group controlId="formNumberFormat" className="mb-1">
                <Form.Label className="small fw-semibold d-flex align-items-center">
                  Number format
                  <CustomTooltip
                    id="tooltip-number-format"
                    content="Thousands and decimal separators used when displaying big numbers and token counters."
                  >
                    <i className="bi bi-info-circle info-icon ms-2"></i>
                  </CustomTooltip>
                </Form.Label>
                <Form.Select
                  value={numberFormat}
                  onChange={(e) => setNumberFormat(e.target.value)}
                >
                  {Object.keys(NUMBER_FORMATS).map((format) => (
                    <option key={format} value={format}>{format}</option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Form>
      </BaseModal>

      <NotificationToast
        show={toastConfig.show}
        message={toastConfig.message}
        variant={toastConfig.variant}
        title={toastConfig.title}
        duration={toastConfig.duration}
        onClose={handleToastClose}
      />
    </>
  );
};

UserProfileModal.propTypes = {
  show: PropTypes.bool.isRequired,
  handleClose: PropTypes.func.isRequired
};

export default UserProfileModal;
