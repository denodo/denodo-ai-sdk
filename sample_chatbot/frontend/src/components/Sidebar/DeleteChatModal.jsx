import React from "react";
import { ConfirmationModal } from "../Common/Modal";

const DeleteChatModal = ({ show, onHide, onConfirm }) => (
  <ConfirmationModal
    show={show}
    onHide={onHide}
    onConfirm={onConfirm}
    title="Delete conversation"
    message={
      <>
        Are you sure you want to delete this chat? This action is{" "}
        <strong>irreversible</strong>.
      </>
    }
    confirmLabel="Yes, delete"
  />
);

export default DeleteChatModal;
