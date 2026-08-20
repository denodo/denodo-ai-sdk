import React from "react";
import { Modal, Button, Form } from "react-bootstrap";

const RenameChatModal = ({
  show,
  onHide,
  newChatName,
  setNewChatName,
  onConfirm,
}) => (
  <Modal show={show} onHide={onHide} centered>
    <Modal.Header closeButton data-bs-theme="light">
      <Modal.Title>Rename Chat</Modal.Title>
    </Modal.Header>
    <Modal.Body>
      <Form.Group>
        <Form.Label>Chat Title</Form.Label>
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
    </Modal.Body>
    <Modal.Footer className="border-0 pt-0">
      <Button variant="light" onClick={onHide}>
        Cancel
      </Button>
      <Button variant="primary" onClick={onConfirm}>
        Save
      </Button>
    </Modal.Footer>
  </Modal>
);

export default RenameChatModal;
