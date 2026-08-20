import { useState } from "react";
import { actionTypes } from "../reducers/chatReducer";

export const useChatLimits = (dispatch) => {
  const [limitModal, setLimitModal] = useState({
    show: false,
    type: null,
    pendingData: null,
    limit: 0,
    current: 0,
    targetsToDelete: [],
  });
  const [autoOverwriteAccepted, setAutoOverwriteAccepted] = useState(false);

  const handleLimitReached = (errorData, pendingRequestData) => {
    setLimitModal({
      show: true,
      type: errorData.type,
      limit: errorData.limit,
      current: errorData.current,
      targetsToDelete: errorData.targets_to_delete || [],
      pendingData: pendingRequestData,
    });
  };

  const closeLimitModal = () => {
    if (
      limitModal.pendingData &&
      limitModal.pendingData.resultIndex !== undefined
    ) {
      dispatch({
        type: actionTypes.DELETE_CHAT_ITEM,
        payload: { resultIndex: limitModal.pendingData.resultIndex },
      });
    }
    setLimitModal({
      show: false,
      type: null,
      pendingData: null,
      limit: 0,
      current: 0,
      targetsToDelete: [],
    });
  };

  return {
    limitModal,
    setLimitModal,
    autoOverwriteAccepted,
    setAutoOverwriteAccepted,
    handleLimitReached,
    closeLimitModal,
  };
};
