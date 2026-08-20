import { useState, useRef, useEffect } from "react";
import { useConfig } from "../contexts/ConfigContext";
import { actionTypes } from "../reducers/chatReducer";
import useToolSelector from "./useToolSelector";

const useQuestionForm = (currentQuestion, setCurrentQuestion, results, dispatch, sdk, isAuthenticated, selectedChatbot) => {
  const { config } = useConfig();
  const { isLoading, processQuestion, cancelQuery, runningRequests } = sdk;

  const [showFilterModal, setShowFilterModal] = useState(false);
  const [searchFilters, setSearchFilters] = useState({
    databases: [],
    tags: [],
  });
  const [allowExternalAssociations, setAllowExternalAssociations] = useState(true);
  const [lastToolRequest, setLastToolRequest] = useState(null);

  const textInputRef = useRef(null);

  useEffect(() => {
    setSearchFilters({
      databases: [],
      tags: [],
    });
    setAllowExternalAssociations(true);
  }, [selectedChatbot]);

  const activeRequestId = runningRequests.length > 0 ? runningRequests[runningRequests.length - 1] : null;
  const isQueryRunning = activeRequestId !== null;
  const isAnyQueryRunning = isLoading || results.some((r) => r.isLoading);
  const filterCount = searchFilters.databases.length + searchFilters.tags.length;

  const {
    prepareSubmission,
  } = useToolSelector(config);

  const handleQuestionChange = (event) => {
    setCurrentQuestion(event.target.value);
  };

  const handleFilterSave = ({ databases, tags, allowExternalAssociations }) => {
    setSearchFilters({ databases, tags });
    setAllowExternalAssociations(allowExternalAssociations);
  };

  const submitQuestion = async (questionText, forceType = null) => {
    if (!isAuthenticated || !questionText.trim() || isAnyQueryRunning) return;

    const { finalQuestion, toolName, toolPrettyName } = prepareSubmission(questionText, forceType);
    if (!finalQuestion) return;

    if (toolName) {
      setLastToolRequest({
        name: toolName,
        prettyName: toolPrettyName || toolName,
      });
    }

    const resultIndex = results.length;
    
    dispatch({
      type: actionTypes.ADD_CHAT_ITEM,
      payload: { 
        question: finalQuestion, 
        isLoading: true, 
        result: "", 
        toolCalls: [],
        blocks: [],
        combinedTablesUsed: []
      }
    });

    const options = {
      databases: searchFilters.databases.join(','),
      tags: searchFilters.tags.join(','),
      allow_external_associations: allowExternalAssociations
    };

    await processQuestion(finalQuestion, toolName, resultIndex, options);

    setCurrentQuestion("");
  };

  const handleSubmit = (event, forceType = null) => {
    if (event && event.preventDefault) event.preventDefault();
    submitQuestion(currentQuestion, forceType);
  };

  const handleSendClick = (event, forceType = null) => {
    if (!isAuthenticated || isAnyQueryRunning) return;
    
    if (!currentQuestion.trim()) {
      textInputRef.current?.focus();
      return;
    }
    
    handleSubmit(event, forceType);
  };

  const handleCancelQuery = () => {
    if (activeRequestId) {
      cancelQuery(activeRequestId);
    }
  };

  return {
    currentQuestion,
    setCurrentQuestion,
    showFilterModal,
    setShowFilterModal,
    searchFilters,
    allowExternalAssociations,
    isQueryRunning,
    isAnyQueryRunning,
    filterCount,
    textInputRef,
    handleQuestionChange,
    handleFilterSave,
    handleSubmit,
    handleSendClick,
    handleCancelQuery,
    lastToolRequest,
    config
  };
};

export default useQuestionForm;
