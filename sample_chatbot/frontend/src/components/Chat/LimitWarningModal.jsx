import React from "react";
import { Modal, Button } from "react-bootstrap";

const LimitWarningModal = ({ modalState, onClose, onAccept }) => {
  if (!modalState.show) return null;

  const isMessages = modalState.type === "messages";
  const targetCount = modalState.targetsToDelete?.length || 0;

  const itemText = isMessages
    ? targetCount === 1
      ? "message"
      : "messages"
    : targetCount === 1
      ? "conversation"
      : "conversations";

  const deletionTargetText =
    targetCount === 1
      ? `the oldest ${itemText}`
      : `the oldest ${targetCount} ${itemText}`;

  return (
    <Modal show={modalState.show} onHide={onClose} centered backdrop="static">
      <Modal.Header closeButton className="border-0">
        <Modal.Title>
          <i className="bi bi-exclamation-triangle-fill text-warning me-2"></i>
          {isMessages ? "Message Limit Reached" : "Conversation Limit Reached"}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body className="text-muted">
        {isMessages ? (
          <>
            <p>
              Cannot save the new message because the storage limit (
              <strong>{modalState.limit}</strong>) has been reached.
            </p>
            <p>
              If you accept, <strong>{deletionTargetText}</strong> will be
              permanently deleted from the database:
            </p>
            <div className="limit-list-container mb-3">
              <ul className="list-group list-group-flush text-start mb-0">
                {modalState.targetsToDelete.map((target, idx) => (
                  <li
                    key={idx}
                    className="list-group-item list-group-item-danger text-truncate"
                  >
                    "{target}"
                  </li>
                ))}
              </ul>
            </div>
            <p className="mb-0 fw-bold text-dark">
              Note: If you accept, from this point forward, the oldest messages
              will be automatically deleted in the background as you continue
              chatting in this conversation.
            </p>
          </>
        ) : (
          <>
            <p>
              Cannot create a new conversation because the limit of{" "}
              <strong>{modalState.limit}</strong> has been reached.
            </p>
            <p>
              If you accept, <strong>{deletionTargetText}</strong> will be
              permanently deleted:
            </p>
            <div className="limit-list-container mb-3">
              <ul className="list-group list-group-flush text-start mb-0">
                {modalState.targetsToDelete.map((target, idx) => (
                  <li
                    key={idx}
                    className="list-group-item list-group-item-danger text-truncate"
                  >
                    {target}
                  </li>
                ))}
              </ul>
            </div>
            <p className="mb-0">
              You can also cancel and manually delete previous conversations
              from the sidebar.
            </p>
          </>
        )}
      </Modal.Body>
      <Modal.Footer className="border-0 pb-4 pe-4">
        <Button variant="light" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" onClick={onAccept}>
          Accept
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default LimitWarningModal;
