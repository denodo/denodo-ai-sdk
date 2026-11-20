import React from 'react';
import PropTypes from 'prop-types';
import BaseModal from './BaseModal';

const ConfirmationModal = ({
  show,
  onHide,
  onConfirm,
  title,
  message = null,
  iconClass = 'bi-exclamation-circle text-danger',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmVariant = 'danger',
  nested = false,
  size = 'sm',
  children = null,
}) => (
  <BaseModal
    show={show}
    onHide={onHide}
    title={title}
    headerBadges={
      iconClass ? (
        <i className={`bi ${iconClass} rcc-confirm-icon`} aria-hidden="true" />
      ) : null
    }
    size={size}
    nested={nested}
    className="rcc-confirm"
    footer={
      <>
        <button type="button" className="rcc-ghost-btn" onClick={onHide}>
          {cancelLabel}
        </button>
        <button
          type="button"
          className={confirmVariant === 'primary' ? 'rcc-primary-btn' : 'rcc-danger-btn'}
          onClick={onConfirm}
        >
          {confirmLabel}
        </button>
      </>
    }
  >
    <div className="rcc-confirm-content">
      {message && <div className="rcc-confirm-message">{message}</div>}
      {children && <div className="rcc-confirm-extra">{children}</div>}
    </div>
  </BaseModal>
);

ConfirmationModal.propTypes = {
  show: PropTypes.bool.isRequired,
  onHide: PropTypes.func.isRequired,
  onConfirm: PropTypes.func.isRequired,
  title: PropTypes.node.isRequired,
  message: PropTypes.node,
  iconClass: PropTypes.string,
  confirmLabel: PropTypes.node,
  cancelLabel: PropTypes.node,
  confirmVariant: PropTypes.oneOf(['danger', 'primary']),
  nested: PropTypes.bool,
  size: PropTypes.oneOf(['sm', 'md']),
  children: PropTypes.node,
};

export default ConfirmationModal;
