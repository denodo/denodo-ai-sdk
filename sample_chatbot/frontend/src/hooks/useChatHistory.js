import { useState } from "react";
import api from "../api/client";
import { actionTypes } from "../reducers/chatReducer";

const CHAT_PAGE_LIMIT = 20;

export const useChatHistory = (
  dispatch,
  chatbots,
  switchAgentInBackend,
  setSelectedChatbot,
  setAutoOverwriteAccepted,
  handleLimitReached
) => {
  const [currentThreadId, setCurrentThreadId] = useState(null);
  const [chatHistoryList, setChatHistoryList] = useState([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [chatToDelete, setChatToDelete] = useState(null);
  const [chatToRename, setChatToRename] = useState(null);
  const [newChatName, setNewChatName] = useState("");
  const [chatOffset, setChatOffset] = useState(0);
  const [hasMoreChats, setHasMoreChats] = useState(true);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: "",
    variant: "info",
    title: "",
  });

  const showToast = (message, variant = "info", title = "Notification") => {
    setToastConfig({ show: true, message, variant, title });
  };

  const closeToast = () => {
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  const fetchChatHistoryList = async (
    isLoadMore = false,
    query = searchQuery,
  ) => {
    try {
      if (!isLoadMore) setIsLoadingList(true);
      const currentOffset = isLoadMore ? chatOffset + CHAT_PAGE_LIMIT : 0;
      const response = await api.get(
        `history?limit=${CHAT_PAGE_LIMIT}&offset=${currentOffset}&q=${encodeURIComponent(query)}`,
      );

      if (response.data && response.data.chats) {
        const newChats = response.data.chats;
        if (isLoadMore) {
          setChatHistoryList((prev) => [...prev, ...newChats]);
          setChatOffset(currentOffset);
        } else {
          setChatHistoryList(newChats);
          setChatOffset(0);
        }
        setHasMoreChats(newChats.length >= CHAT_PAGE_LIMIT);
      }
    } catch (error) {
      console.error("Error fetching chat history list", error);
    } finally {
      setIsLoadingList(false);
    }
  };

  const handleRequestCompletion = (requestId) => {
    fetchChatHistoryList(false);
  };

  const handleLoadOldChat = async (chat) => {
    try {
      setAutoOverwriteAccepted(false);
      setIsLoadingHistory(true);

      let targetBot = chatbots.find((b) => b.isGlobal);
      if (chat.agent_id) {
        targetBot = chatbots.find((b) => b.id === chat.agent_id) || targetBot;
      }
      await switchAgentInBackend(targetBot);

      setCurrentThreadId(chat.thread_id);
      setSelectedChatbot(targetBot);
      dispatch({ type: actionTypes.CLEAR_CHAT });

      const response = await api.get(`history/${chat.thread_id}/export`);
      const rawMessages = response.data.messages || [];
      const formattedResults = [];
      let currentInteraction = null;

      for (let i = 0; i < rawMessages.length; i++) {
        const msg = rawMessages[i];

        if (msg.role === "human" || msg.role === "user") {
          // Push previous interaction if exists
          if (currentInteraction) formattedResults.push(currentInteraction);

          let cleanQuestion = msg.content || "";
          if (cleanQuestion.includes("<user_query>")) {
            const match = cleanQuestion.match(
              /<user_query>([\s\S]*?)<\/user_query>/,
            );
            if (match && match[1]) cleanQuestion = match[1].trim();
          }

          // Start a new interaction
          currentInteraction = {
            question: cleanQuestion,
            result: "",
            blocks: [],
            uuid: msg.uuid || `hist-${chat.thread_id}-${formattedResults.length}`,
            isLoading: false,
            isError: false,
            toolCalls: [],
            chatbot_llm: null,
            relatedQuestions: [],
            relatedQuestionsDeepQuery: [],
            combinedTablesUsed: [],
            combinedVqls: "",
            disableFeedback: false,
          };
        } else if (currentInteraction) {
          // --- AI/ASSISTANT MESSAGES ---
          if (msg.role === "ai" || msg.role === "assistant") {
            
            if (msg.is_imported) {
              currentInteraction.disableFeedback = true;
            }

            if (msg.chatbot_llm) {
              currentInteraction.chatbot_llm = msg.chatbot_llm;
            } else if (!currentInteraction.chatbot_llm) {
              currentInteraction.chatbot_llm = "History Record";
            }

            // 1. Process Text Block sequentially
            if (msg.content && typeof msg.content === "string") {
              let text = msg.content;

              // Extract related questions
              const rqRegex =
                /<related_question[^>]*>([\s\S]*?)<\/related_question>/gi;
              let match;
              while ((match = rqRegex.exec(text)) !== null)
                currentInteraction.relatedQuestions.push(match[1].trim());

              const rqdqRegex =
                /<related_question_deepquery[^>]*>([\s\S]*?)<\/related_question_deepquery>/gi;
              while ((match = rqdqRegex.exec(text)) !== null)
                currentInteraction.relatedQuestionsDeepQuery.push(
                  match[1].trim(),
                );

              const rqaRegex =
                /<related_question_analysis[^>]*>([\s\S]*?)<\/related_question_analysis>/gi;
              while ((match = rqaRegex.exec(text)) !== null)
                currentInteraction.relatedQuestionsDeepQuery.push(
                  match[1].trim(),
                );

              // Clean text from tags
              text = text
                .replace(
                  /<related_question[^>]*>[\s\S]*?<\/related_question>/gi,
                  "",
                )
                .replace(
                  /<related_question_deepquery[^>]*>[\s\S]*?<\/related_question_deepquery>/gi,
                  "",
                )
                .replace(
                  /<related_question_analysis[^>]*>[\s\S]*?<\/related_question_analysis>/gi,
                  "",
                );

              const cleanText = text.trim();

              // Push text directly to blocks to maintain sequential order
              if (cleanText) {
                currentInteraction.blocks.push({
                  type: "message",
                  content: cleanText,
                });
                currentInteraction.result +=
                  (currentInteraction.result ? "\n" : "") + cleanText;
              }
            }

            // 2. Process Tool Calls sequentially
            if (msg.tool_calls && Array.isArray(msg.tool_calls)) {
              msg.tool_calls.forEach((tc) => {
                const toolBlock = {
                  type: "tool",
                  toolName: tc.name,
                  name: tc.name,
                  toolCallId: tc.id,
                  args: tc.args || {},
                  status: "running",
                };
                // Push reference to both arrays
                currentInteraction.toolCalls.push(toolBlock);
                currentInteraction.blocks.push(toolBlock);
              });
            }
          }

          // --- TOOL MESSAGES ---
          else if (msg.role === "tool") {
            let parsedResult = msg.content;
            try {
              if (msg.content && typeof msg.content === "string")
                parsedResult = JSON.parse(msg.content);
            } catch (e) {}

            const artifact = msg.artifact || {};
            if (artifact.tables_used && Array.isArray(artifact.tables_used)) {
              artifact.tables_used.forEach((table) => {
                if (!currentInteraction.combinedTablesUsed.includes(table))
                  currentInteraction.combinedTablesUsed.push(table);
              });
            }

            if (artifact.vql) {
              currentInteraction.combinedVqls +=
                (currentInteraction.combinedVqls ? "\n\n" : "") + artifact.vql;
            }

            // Find the sequential block and update it
            const blockIndex = currentInteraction.blocks.findIndex(
              (b) => b.type === "tool" && b.toolCallId === msg.tool_call_id,
            );

            // Mirror the live-stream behavior: a result whose artifact carries
            // an error (e.g. an interrupted tool call) renders as errored.
            const resultStatus = artifact && artifact.error ? "error" : "finished";

            if (blockIndex !== -1) {
              currentInteraction.blocks[blockIndex].status = resultStatus;
              currentInteraction.blocks[blockIndex].result = parsedResult;
              currentInteraction.blocks[blockIndex].output = parsedResult;
              currentInteraction.blocks[blockIndex].contentToLLM = msg.content;
              currentInteraction.blocks[blockIndex].artifact = artifact;
            } else {
              // Edge case: Tool answer without previous Tool call registered
              const newToolBlock = {
                type: "tool",
                toolName: msg.tool_name || "tool",
                name: msg.tool_name || "tool",
                toolCallId: msg.tool_call_id,
                status: resultStatus,
                result: parsedResult,
                output: parsedResult,
                contentToLLM: msg.content,
                artifact: artifact,
                args: {},
              };
              currentInteraction.toolCalls.push(newToolBlock);
              currentInteraction.blocks.push(newToolBlock);
            }
          }
        }
      }

      if (currentInteraction) formattedResults.push(currentInteraction);

      dispatch({
        type: actionTypes.SET_CHAT_HISTORY,
        payload: formattedResults,
      });
    } catch (error) {
      console.error(error);
      alert("Error loading this conversation.");
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const confirmDeleteChat = async (handleNewChat) => {
    if (!chatToDelete) return;
    try {
      await api.delete(`history/${chatToDelete}`);
      if (currentThreadId === chatToDelete) handleNewChat();
      fetchChatHistoryList(false);
    } catch (error) {
      alert("Error deleting the chat history.");
    } finally {
      setChatToDelete(null);
    }
  };

  const handleRenameSubmit = async () => {
    if (!chatToRename || !newChatName.trim()) return;
    try {
      await api.put(`history/${chatToRename.thread_id}`, {
        title: newChatName,
      });
      fetchChatHistoryList(false);
    } catch (e) {
      alert("Error renaming chat.");
    } finally {
      setChatToRename(null);
      setNewChatName("");
    }
  };

  const handlePinChat = async (threadId, isPinned) => {
    try {
      await api.put(`history/${threadId}/pin`, { is_pinned: isPinned });
      fetchChatHistoryList(false);
    } catch (e) {
      alert("Error pin status.");
    }
  };

  const handleExportChat = async (chat) => {
    try {
      const response = await api.get(`history/${chat.thread_id}/export`);
      const exportPayload = { ...response.data, title: chat.title };
      const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `denodo_chat_${chat.title.replace(/[^a-z0-9]/gi, "_").toLowerCase()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert("Error exporting chat.");
    }
  };

  const handleImportChat = async (file, forceOverwrite = false) => {
    if (!file) return;

    setIsLoadingHistory(true);
    
    const formData = new FormData();
    formData.append("file", file);
    if (forceOverwrite) formData.append("force_overwrite", "true");

    try {
      const response = await api.post("history/import", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      
      if (response.data.success) {
        await fetchChatHistoryList(false);
        await handleLoadOldChat({
          thread_id: response.data.thread_id,
          agent_id: response.data.agent_id,
          title: response.data.title
        });

        if (response.data.was_truncated) {
          showToast(
            `The imported chat exceeded the maximum length. Only the last ${response.data.max_messages} messages were kept to ensure optimal performance.`,
            'warning',
            'Chat Truncated'
          );
        } else {
          showToast("Chat imported successfully!", "success", "Import Successful");
        }
      }
    } catch (error) {
      if (
        error.response &&
        error.response.status === 409 &&
        error.response.data.error === "limit_reached"
      ) {
        if (handleLimitReached) {
          handleLimitReached(error.response.data, {
            type: "import",
            file: file,
          });
        }
      } else if (error.response && error.response.status === 413) {
        showToast(error.response.data.error || "File is too large.", 'danger', 'File Too Large');
      } else if (error.response && error.response.status === 400) {
         showToast(error.response.data.error || "Invalid JSON format.", 'danger', 'Import Error');
      } else {
        showToast("Error importing chat. Make sure it's a valid JSON export file.", "danger", "Import Failed");
      }
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const resetHistoryState = () => {
    setChatHistoryList([]);
    setChatOffset(0);
    setSearchQuery("");
    setHasMoreChats(true);
  };

  return {
    currentThreadId,
    setCurrentThreadId,
    chatHistoryList,
    isLoadingHistory,
    chatToDelete,
    setChatToDelete,
    chatToRename,
    setChatToRename,
    newChatName,
    setNewChatName,
    hasMoreChats,
    isLoadingList,
    searchQuery,
    setSearchQuery,
    fetchChatHistoryList,
    handleLoadOldChat,
    confirmDeleteChat,
    handleRenameSubmit,
    handlePinChat,
    handleExportChat,
    handleImportChat,
    handleRequestCompletion,
    resetHistoryState,
    toastConfig,
    closeToast,
  };
};
