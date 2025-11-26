import React from "react";
import Toast from "react-bootstrap/Toast";
import ToastContainer from "react-bootstrap/ToastContainer";
import "./NotificationToast.css"; 

const NotificationToast = ({ show, message, variant = 'info', title = 'Notification', onClose, duration = 5000 }) => {

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
    <ToastContainer position="bottom-end" className="p-3" style={{ zIndex: 1060 }}>
      <Toast
        show={show}
        onClose={onClose}
        delay={duration} 
        autohide
        className="custom-report-toast" 
      >
        <Toast.Header closeButton>
          {renderIcon()}
          <strong className="me-auto">{title}</strong>
        </Toast.Header>
        <Toast.Body>
          {message}
        </Toast.Body>
      </Toast>
    </ToastContainer>
  );
};

export default NotificationToast;