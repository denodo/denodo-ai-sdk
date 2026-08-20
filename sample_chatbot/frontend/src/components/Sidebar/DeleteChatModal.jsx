import React from "react";
import { Modal, Button } from "react-bootstrap";

const DeleteChatModal = ({ show, onHide, onConfirm }) => (
  <Modal show={show} onHide={onHide} centered backdrop="static">
    <Modal.Header closeButton data-bs-theme="light">
      <Modal.Title>Delete conversation</Modal.Title>
    </Modal.Header>
    <Modal.Body style={{ color: "#495057", fontSize: "1.05rem" }}>
      Are you sure you want to delete this chat? This action is{" "}
      <strong>irreversible</strong>.
    </Modal.Body>
    <Modal.Footer className="border-0 pt-0">
      <Button variant="light" onClick={onHide}>
        Cancel
      </Button>
      <Button variant="danger" onClick={onConfirm}>
        Accept
      </Button>
    </Modal.Footer>
  </Modal>
);

export default DeleteChatModal;
