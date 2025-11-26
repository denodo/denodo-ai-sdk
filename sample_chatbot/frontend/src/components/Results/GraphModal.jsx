import React from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";

const GraphModal = ({ show, graph, onClose }) => {
  return (
    <Modal show={show} onHide={onClose} size="lg" centered>
      <Modal.Header closeButton data-bs-theme="light">
        <Modal.Title>Graph View</Modal.Title>
      </Modal.Header>
      <Modal.Body className="text-center">
        {graph && <img src={graph} alt="Graph" className="img-fluid" />}
      </Modal.Body>
      <Modal.Footer>
        <Button variant="light" onClick={onClose}>
          Close
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default GraphModal;


