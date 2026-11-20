import React, { useEffect, useMemo, useRef } from "react";
import "./Chat.css";
import ChatItem from "./ChatItem";
import { actionTypes } from "../../reducers/chatReducer";

const Chat = ({
  results,
  dispatch,
  setCurrentQuestion,
  setQuestionType,
  contextUsage,
}) => {
  const resultsEndRef = useRef(null);
  const resultsContainerRef = useRef(null);

  const receivedToolOutputs = useMemo(() => {
    const map = {};
    for (const item of contextUsage?.received_tool_outputs || []) {
      if (item?.tool_call_id) map[item.tool_call_id] = item.content;
    }
    return map;
  }, [contextUsage]);

  const scrollToBottom = () => {
    resultsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (results.length > 0) {
      scrollToBottom();
    }
  }, [results]);

  useEffect(() => {
    if (results.some(r => r.isExiting)) {
      const timer = setTimeout(() => {
        dispatch({ type: actionTypes.PURGE_EXITING_ITEMS });
      }, 400);
      return () => clearTimeout(timer);
    }
  }, [results, dispatch]);

  if (results.length === 0) {
    return null;
  }

  return (
    <div
      className="d-flex flex-column align-items-center w-100 text-light"
      ref={resultsContainerRef}
    >
      {results.map((result, index) => (
        <div
          key={result.id || result._key || `msg-${index}`}
          className={`w-100 ${result.isExiting ? 'chat-item-exit' : ''}`}
        >
          <ChatItem
            result={result}
            index={index}
            dispatch={dispatch}
            setCurrentQuestion={setCurrentQuestion}
            setQuestionType={setQuestionType}
            resultsContainerRef={resultsContainerRef}
            receivedToolOutputs={receivedToolOutputs}
            contextViews={contextUsage?.views || []}
          />
        </div>
      ))}
      <div ref={resultsEndRef} />
    </div>
  );
};

export default Chat;
