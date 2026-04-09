export const actionTypes = {
  ADD_CHAT_ITEM: "ADD_CHAT_ITEM",
  UPDATE_CHAT_ITEM_TEXT: "UPDATE_CHAT_ITEM_TEXT",
  TOOL_CALL_START: "TOOL_CALL_START",
  TOOL_CALL_END: "TOOL_CALL_END",
  COMPLETE_CHAT_ITEM: "COMPLETE_CHAT_ITEM",
  ERROR_CHAT_ITEM: "ERROR_CHAT_ITEM",
  CLEAR_CHAT: "CLEAR_CHAT",
  DELETE_CHAT_ITEM: "DELETE_CHAT_ITEM",
  PURGE_EXITING_ITEMS: "PURGE_EXITING_ITEMS",
  SET_CHAT_ITEM_FEEDBACK: "SET_CHAT_ITEM_FEEDBACK",
};

export const chatReducer = (state, action) => {
  switch (action.type) {
    case actionTypes.ADD_CHAT_ITEM:
      return [...state, action.payload];

    case actionTypes.CLEAR_CHAT:
      return [];

    case actionTypes.DELETE_CHAT_ITEM: {
      const { resultIndex } = action.payload;
      return state.map((r, i) => i === resultIndex ? { ...r, isExiting: true } : r);
    }

    case actionTypes.PURGE_EXITING_ITEMS: {
      return state.filter((r) => !r.isExiting);
    }

    case actionTypes.SET_CHAT_ITEM_FEEDBACK: {
      const { resultIndex, feedback, feedbackDetails } = action.payload;
      return state.map((r, i) =>
        i === resultIndex ? { ...r, feedback, feedbackDetails } : r
      );
    }

    case actionTypes.UPDATE_CHAT_ITEM_TEXT: {
      const { resultIndex, text } = action.payload;
      return state.map((r, i) => {
        if (i !== resultIndex) return r;
        const blocks = Array.isArray(r.blocks) ? [...r.blocks] : [];
        const last = blocks[blocks.length - 1];
        if (last && last.type === 'message') {
          last.content = (last.content || '') + text;
        } else {
          blocks.push({ type: 'message', content: text });
        }
        return { ...r, result: (r.result || '') + text, blocks };
      });
    }

    case actionTypes.TOOL_CALL_START: {
      const { resultIndex, toolCall } = action.payload;
      return state.map((r, i) => {
        if (i !== resultIndex) return r;
        const blocks = Array.isArray(r.blocks)
          ? [...r.blocks, { type: 'tool', ...toolCall }]
          : [{ type: 'tool', ...toolCall }];
        return {
          ...r,
          toolCalls: [...(r.toolCalls || []), toolCall],
          blocks,
        };
      });
    }

    case actionTypes.TOOL_CALL_END: {
      const { resultIndex, toolName, toolCallId, content, artifact } = action.payload;
      return state.map((r, i) => {
        if (i !== resultIndex) return r;
        const hasError = artifact && artifact.error;

        const updatedCalls = (r.toolCalls || []).map((c) =>
          c.toolCallId === toolCallId
            ? { ...c, status: hasError ? 'error' : 'finished', contentToLLM: content, artifact: artifact || {} }
            : c
        );

        const blocks = Array.isArray(r.blocks)
          ? r.blocks.map((b) =>
              b.type === 'tool' && b.toolCallId === toolCallId
                ? { ...b, status: hasError ? 'error' : 'finished', contentToLLM: content, artifact: artifact || {} }
                : b
            )
          : [];

        let combined = new Set(r.combinedTablesUsed || []);
        if (toolName === 'data_query' && artifact && artifact.tables_used) {
          for (const t of artifact.tables_used) combined.add(t);
        }

        let combinedVqls = Array.isArray(r.combinedVqls) ? [...r.combinedVqls] : [];
        if (toolName === 'data_query' && artifact && artifact.vql) {
          combinedVqls.push(String(artifact.vql));
        }

        return {
          ...r,
          toolCalls: updatedCalls,
          blocks,
          combinedTablesUsed: Array.from(combined),
          combinedVqls,
        };
      });
    }

    case actionTypes.COMPLETE_CHAT_ITEM: {
      const { resultIndex, payload } = action.payload;
      return state.map((r, i) => {
        if (i !== resultIndex) return r;
        const rel = payload.related_questions || [];
        const relDeepQuery = payload.related_questions_deepquery || [];
        return {
          ...r,
          isLoading: false,
          uuid: payload.uuid || r.uuid,
          relatedQuestions: rel,
          relatedQuestionsDeepQuery: relDeepQuery,
          chatbot_llm: payload.chatbot_llm || r.chatbot_llm,
        };
      });
    }

    case actionTypes.ERROR_CHAT_ITEM: {
      const { resultIndex, message, errorDetails } = action.payload;
      return state.map((r, i) =>
        i === resultIndex
          ? {
              ...r,
              isLoading: false,
              result: message,
              isError: true,
              errorMessage: message,
              errorDetails: errorDetails || message,
            }
          : r
      );
    }

    default:
      return state;
  }
};
