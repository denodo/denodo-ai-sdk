import React from "react";
import { Form } from "react-bootstrap";
import { BaseModal } from "../Common/Modal";

const RenameChatModal = ({
  show,
  onHide,
  newChatName,
  setNewChatName,
  onConfirm,
}) => (
  <BaseModal
    show={show}
    onHide={onHide}
    title="Rename Chat"
    size="sm"
    scrollableBody
    footer={
      <>
        <button type="button" className="rcc-ghost-btn" onClick={onHide}>
          Cancel
        </button>
        <button type="button" className="rcc-primary-btn" onClick={onConfirm}>
          Save
        </button>
      </>
    }
  >
    <Form.Group>
      <Form.Label className="small fw-semibold">Chat Title</Form.Label>
      <Form.Control
        type="text"
        value={newChatName}
        onChange={(e) => setNewChatName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onConfirm();
        }}
        autoFocus
      />
    </Form.Group>
  </BaseModal>
);

export default RenameChatModal;
