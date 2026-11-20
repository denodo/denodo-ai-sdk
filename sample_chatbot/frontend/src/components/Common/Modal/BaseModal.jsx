import React from 'react';
import PropTypes from 'prop-types';
import Modal from 'react-bootstrap/Modal';
import './Modal.css';

const BaseModal = ({
  show,
  onHide,
  onExited,
  title,
  headerBadges = null,
  size = 'md',
  fixedHeight = false,
  scrollableBody = false,
  backdrop = true,
  nested = false,
  className = '',
  dialogClassName = '',
  footer = null,
  footerClassName = '',
  children,
}) => {
  const modalClass = ['rcc-modal', nested ? 'rcc-modal-nested' : '', className].filter(Boolean).join(' ');
  const dialogClass = ['rcc-dialog', `rcc-dialog-${size}`, fixedHeight ? 'rcc-dialog-fixed' : '', dialogClassName]
    .filter(Boolean)
    .join(' ');
  const bootstrapSize = size === 'md' ? undefined : size;

  return (
    <Modal
      show={show}
      onHide={onHide}
      onExited={onExited}
      backdrop={backdrop}
      size={bootstrapSize}
      centered
      className={modalClass}
      dialogClassName={dialogClass}
      backdropClassName={nested ? 'rcc-backdrop-nested' : 'rcc-backdrop'}
    >
      <Modal.Header closeButton>
        <Modal.Title as="div" className="rcc-modal-title">
          {title}
          {headerBadges}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body className="rcc-body">
        {scrollableBody ? <div className="modal-scroll-container">{children}</div> : children}
      </Modal.Body>
      {footer ? <Modal.Footer className={footerClassName}>{footer}</Modal.Footer> : null}
    </Modal>
  );
};

BaseModal.propTypes = {
  show: PropTypes.bool.isRequired,
  onHide: PropTypes.func.isRequired,
  onExited: PropTypes.func,
  title: PropTypes.node.isRequired,
  headerBadges: PropTypes.node,
  size: PropTypes.oneOf(['sm', 'md', 'lg', 'xl']),
  fixedHeight: PropTypes.bool,
  scrollableBody: PropTypes.bool,
  backdrop: PropTypes.oneOf([true, false, 'static']),
  nested: PropTypes.bool,
  className: PropTypes.string,
  dialogClassName: PropTypes.string,
  footer: PropTypes.node,
  footerClassName: PropTypes.string,
  children: PropTypes.node,
};

export default BaseModal;
