import React from "react";
import { ConfirmationModal } from "../../Common/Modal";

const LimitReachedModal = ({ modalState, onClose, onAccept }) => {
  const isMessages = modalState.type === "messages";
  const targets = modalState.targetsToDelete || [];
  const targetCount = targets.length;

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

  const message = isMessages ? (
    <>
      Cannot save the new message because the storage limit (
      <strong>{modalState.limit}</strong>) has been reached. If you accept,{" "}
      <strong>{deletionTargetText}</strong> will be permanently deleted from
      the database:
    </>
  ) : (
    <>
      Cannot create a new conversation because the limit of{" "}
      <strong>{modalState.limit}</strong> has been reached. If you accept,{" "}
      <strong>{deletionTargetText}</strong> will be permanently deleted:
    </>
  );

  return (
    <ConfirmationModal
      show={modalState.show}
      onHide={onClose}
      onConfirm={onAccept}
      title={isMessages ? "Message Limit Reached" : "Conversation Limit Reached"}
      message={message}
      iconClass="bi-exclamation-triangle-fill text-warning"
      confirmLabel="Accept"
      confirmVariant="primary"
      size="md"
    >
      <div className="limit-list-container mb-3">
        <ul className="list-group list-group-flush text-start mb-0">
          {targets.map((target, idx) => (
            <li
              key={idx}
              className="list-group-item list-group-item-danger text-truncate"
            >
              {isMessages ? `"${target}"` : target}
            </li>
          ))}
        </ul>
      </div>
      <p className="mb-0 small text-muted">
        {isMessages
          ? "Note: If you accept, from this point forward, the oldest messages will be automatically deleted in the background as you continue chatting in this conversation."
          : "You can also cancel and manually delete previous conversations from the sidebar."}
      </p>
    </ConfirmationModal>
  );
};

export default LimitReachedModal;
