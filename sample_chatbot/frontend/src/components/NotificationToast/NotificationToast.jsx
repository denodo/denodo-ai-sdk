import React from "react";
import PropTypes from "prop-types";
import Toast from "react-bootstrap/Toast";
import ToastContainer from "react-bootstrap/ToastContainer";
import CopyButton from "../CopyButton/CopyButton";
import "./NotificationToast.css"; 

const NotificationToast = ({ 
  show, 
  message, 
  variant = 'info', 
  title = 'Notification', 
  onClose,
  duration = 5000,
  autoHide = true,
  showCopyButton = true,
  onError = null,
}) => {
  const renderIcon = () => {
    switch (variant) {
      case 'success':
        return (
          <div className="toast-icon-container rounded-circle bg-success me-2">
            <i className="bi bi-check-lg text-white" style={{ fontSize: '1.2em' }}></i>
          </div>
        );
      case 'danger':
        return (
          <div className="toast-icon-container rounded-circle bg-danger me-2">
            <i className="bi bi-x-lg text-white" style={{ fontSize: '1em' }}></i>
          </div>
        );
      case 'warning':
        return (
          <div className="toast-icon-container me-2">
            <i className="bi bi-exclamation-triangle-fill text-warning" style={{ fontSize: '1.4em' }}></i>
          </div>
        );
      case 'info':
      default:
        return (
          <div className="toast-icon-container me-2">
            <i className="bi bi-info-circle-fill" style={{ color: '#006699', fontSize: '1.4em' }}></i>
          </div>
        );
    }
  };

  return (
    <ToastContainer position="bottom-end" className="p-3" style={{ zIndex: 1130 }}>
      <Toast
        show={show}
        onClose={onClose}
        delay={duration} 
        autohide={autoHide}
        className="custom-report-toast" 
      >
        <Toast.Header closeButton>
          {renderIcon()}
          <strong className="me-auto">{title}</strong>
        </Toast.Header>
        <Toast.Body>
          <div className="d-flex justify-content-between align-items-start gap-3">
            <div 
              style={{ 
                flex: 1, 
                maxHeight: '250px',
                overflowY: 'auto',
                paddingRight: '10px',
                wordBreak: 'break-word',
                whiteSpace: 'pre-wrap'
              }}
              className="toast-scroll-area"
            >
              {message}
            </div>
            {message && showCopyButton && (
              <CopyButton
                text={message}
                tooltipText="Copy to clipboard"
                placement="top"
                className="ms-2 flex-shrink-0"
                onError={onError}
              />
            )}
          </div>
        </Toast.Body>
      </Toast>
    </ToastContainer>
  );
};

NotificationToast.propTypes = {
  show: PropTypes.bool,
  message: PropTypes.string,
  variant: PropTypes.string,
  title: PropTypes.string,
  onClose: PropTypes.func,
  duration: PropTypes.number,
  autoHide: PropTypes.bool,
  showCopyButton: PropTypes.bool,
  onError: PropTypes.func,
};

export default NotificationToast;
