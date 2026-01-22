import { useState, useRef } from "react";
import { useConfig } from "../contexts/ConfigContext";
import { actionTypes } from "../reducers/chatReducer";
import useToolSelector from "./useToolSelector";

const useQuestionForm = (currentQuestion, setCurrentQuestion, results, dispatch, sdk, isAuthenticated) => {
  const { config } = useConfig();
  const { isLoading, processQuestion, cancelDeepQuery, runningDeepQueries } = sdk;

  const [lastRequestId, setLastRequestId] = useState(null);
  const [showFilterModal, setShowFilterModal] = useState(false);
  const [searchFilters, setSearchFilters] = useState({
    databases: [],
    tags: [],
  });
  const [allowExternalAssociations, setAllowExternalAssociations] = useState(true);
  const [lastToolRequest, setLastToolRequest] = useState(null);

  const textInputRef = useRef(null);

  const isDeepQueryRunning =
    config.enableDeepQuery && lastRequestId !== null && runningDeepQueries.includes(lastRequestId);
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

    const requestId = await processQuestion(finalQuestion, toolName, resultIndex, options);
    
    if (requestId) {
      setLastRequestId(requestId);
    }
    
    setCurrentQuestion("");
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    submitQuestion(currentQuestion);
  };

  const handleDeepQuerySubmit = (event) => {
    event.preventDefault();
    submitQuestion(currentQuestion, "deep_query");
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      if (!isAnyQueryRunning) {
        event.preventDefault();
        handleSubmit(event);
      }
    }
  };

  const handleSendClick = (event) => {
    if (!isAuthenticated || isAnyQueryRunning) return;
    
    if (!currentQuestion.trim()) {
      textInputRef.current?.focus();
      return;
    }
    
    handleSubmit(event);
  };

  const handleDeepQueryClick = (event) => {
    if (!isAuthenticated || isAnyQueryRunning) return;
    
    if (!currentQuestion.trim()) {
      textInputRef.current?.focus();
      return;
    }
    
    handleDeepQuerySubmit(event);
  };

  const handleCancelDeepQuery = () => {
    if (lastRequestId && runningDeepQueries.includes(lastRequestId)) {
      cancelDeepQuery(lastRequestId);
    }
  };

  return {
    currentQuestion,
    setCurrentQuestion,
    showFilterModal,
    setShowFilterModal,
    searchFilters,
    allowExternalAssociations,
    isDeepQueryRunning,
    isAnyQueryRunning,
    filterCount,
    textInputRef,
    handleQuestionChange,
    handleFilterSave,
    handleSubmit,
    handleDeepQuerySubmit,
    handleKeyDown,
    handleSendClick,
    handleDeepQueryClick,
    handleCancelDeepQuery,
    lastToolRequest,
    config
  };
};

export default useQuestionForm;