import { useState, useRef } from "react";
import { actionTypes } from "../reducers/chatReducer";
import { buildApiUrl } from "../api/client";

const useSDK = (dispatch, onRequestComplete, currentThreadId, onThreadIdUpdate, onLimitReached, autoOverwriteAccepted) => {
  const [isLoading, setLoading] = useState(false);
  const [runningRequests, setRunningRequests] = useState(new Set());
  const activeControllers = useRef(new Map()); // Map of requestId -> { controller, resultIndex }
  const requestIdCounter = useRef(0);

  const handleStream = async (url, body, resultIndex, requestId, onMessage, options) => {
    const controller = new AbortController();
    const signal = controller.signal;
    
    activeControllers.current.set(requestId, { controller, resultIndex });

    try {
      
      const isQuestion = url.includes('question');
      const fetchUrl = isQuestion ? buildApiUrl("question") : buildApiUrl(url);
      const method = isQuestion ? 'POST' : 'GET';
      
      const fetchOptions = {
        method,
        headers: isQuestion ? { 'Content-Type': 'application/json' } : undefined,
        body: isQuestion ? JSON.stringify(body) : undefined,
        signal
      };

      const response = await fetch(fetchUrl, fetchOptions);

      if (response.status === 409 && isQuestion) {
        const errorData = await response.json();
        
        if (onLimitReached) {
          onLimitReached(errorData, {
            query: body.query,
            toolName: body.tool,
            resultIndex,
            options
          });
        }
        
        return; 
      }

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const returnedThreadId = response.headers.get('X-Thread-ID');
      if (returnedThreadId && onThreadIdUpdate) {
        onThreadIdUpdate(returnedThreadId);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        // Process complete lines (SSE format usually ends with \n\n)
        const lines = buffer.split('\n\n');
        buffer = lines.pop(); // Keep the incomplete part

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data.trim() === '[DONE]') continue; // OpenAI style, just in case
            
            // Check for special markers from backend if any (e.g. <STREAMOFF>)
            if (data.includes('<STREAMOFF>')) continue;

            try {
               // Check if it is a JSON object
               if (data.startsWith('{')) {
                   const payload = JSON.parse(data);
                   onMessage(payload);
               } else {

                   onMessage({ type: 'message', content: data });
               }
            } catch (e) {
               // Fallback for plain text
               onMessage({ type: 'message', content: data });
            }
          }
        }
      }

    } catch (error) {
      if (error.name === 'AbortError') {
        return;
      }
      console.error("Stream error:", error);
      const backendMessage = error.message || 'Unknown error';
      dispatch({
        type: actionTypes.ERROR_CHAT_ITEM,
        payload: {
          resultIndex,
          message: `Fatal error when connecting to chatbot backend: ${backendMessage}`,
          errorDetails: backendMessage
        }
      });
    } finally {
      activeControllers.current.delete(requestId);
      setRunningRequests(prev => {
        const next = new Set(prev);
        next.delete(requestId);
        return next;
      });
      onRequestComplete(requestId);
      setLoading(false);
    }
  };

  const processQuestion = async (question, _type, resultIndex, options = {}) => {
    setLoading(true);
    const requestId = `agent_${Date.now()}_${++requestIdCounter.current}`;
    setRunningRequests(prev => new Set([...prev, requestId]));

    const body = {
      query: question,
      cancellation_id: requestId,
      tool: _type,
      databases: options.databases,
      tags: options.tags,
      allow_external_associations: options.allow_external_associations,
      thread_id: currentThreadId,
      force_overwrite: options.force_overwrite !== undefined ? options.force_overwrite : autoOverwriteAccepted
    };
    
    handleStream('question', body, resultIndex, requestId, (payload) => {
      const type = payload.type;

      if (type === 'message') {
        const text = (payload.content || '').replace(/<NEWLINE>/g, '\n');
        dispatch({
          type: actionTypes.UPDATE_CHAT_ITEM_TEXT,
          payload: { resultIndex, text }
        });
      } else if (type === 'tool_start') {
        const { tool_name, tool_call_id, args } = payload;
        dispatch({
          type: actionTypes.TOOL_CALL_START,
          payload: {
             resultIndex,
             toolCall: { toolName: tool_name, toolCallId: tool_call_id, args: args || {}, status: 'running' }
          }
        });
      } else if (type === 'tool_end') {
        const { tool_name, tool_call_id, content, artifact } = payload;
        dispatch({
            type: actionTypes.TOOL_CALL_END,
            payload: { resultIndex, toolName: tool_name, toolCallId: tool_call_id, content, artifact }
        });
      } else if (type === 'done') {
        dispatch({
            type: actionTypes.COMPLETE_CHAT_ITEM,
            payload: { resultIndex, payload }
        });
      } else if (type === 'error') {
        const rawMessage = payload.message || 'Error';
        const message = `Fatal error when connecting to chatbot backend: ${rawMessage}`;
        dispatch({
          type: actionTypes.ERROR_CHAT_ITEM,
          payload: {
            resultIndex,
            message,
            errorDetails: payload.traceback || rawMessage
          }
        });
      }
    }, options);

    return requestId;
  };

  const cancelQuery = async (requestId) => {
    const connection = activeControllers.current.get(requestId);
    if (connection) {
      const { controller, resultIndex } = connection;

      controller.abort();
      activeControllers.current.delete(requestId);

      dispatch({
        type: actionTypes.DELETE_CHAT_ITEM,
        payload: { resultIndex }
      });

      setRunningRequests(prev => {
        const newSet = new Set(prev);
        newSet.delete(requestId);
        return newSet;
      });
      setLoading(false);

      // Tell the backend to abort the query, including any in-flight AI SDK
      // request. The endpoint responds once the rollback and empty-chat
      // cleanup have finished, so the sidebar refresh below always sees the
      // final state.
      try {
        await fetch(buildApiUrl('question/cancel'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cancellation_id: requestId })
        });
      } catch {
        // Ignore: the request may already be finished; refresh regardless.
      }
      onRequestComplete(requestId);
    }
  };

  return {
    isLoading,
    processQuestion,
    cancelQuery,
    runningRequests: Array.from(runningRequests)
  };
};

export default useSDK;
